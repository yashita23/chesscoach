import hashlib
import secrets
from collections.abc import Iterator
from typing import Annotated

import bcrypt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from chesscoach.db import Attempt, LoginSession, Player

SESSION_COOKIE = "chesscoach_session"
BCRYPT_MAX_BYTES = 72
# So khớp với hash giả khi email không tồn tại, để thời gian phản hồi không lộ email nào đã đăng ký.
_DUMMY_HASH = bcrypt.hashpw(b"khong-dung-de-dang-nhap", bcrypt.gensalt())


def get_db(request: Request) -> Iterator[Session]:
    from chesscoach.games_sync import get_engine_lock

    factory: sessionmaker[Session] = request.app.state.session_factory
    with get_engine_lock(factory):
        with factory() as db:
            yield db


Db = Annotated[Session, Depends(get_db)]
SessionToken = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]
# Email so sánh không phân biệt hoa thường; chuẩn hóa một chỗ duy nhất.
NormalizedEmail = Annotated[EmailStr, AfterValidator(str.lower)]


class RegisterRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("password")
    @classmethod
    def _password_fits_bcrypt(cls, password: str) -> str:
        if len(password.encode()) > BCRYPT_MAX_BYTES:
            raise ValueError(f"Mật khẩu dài tối đa {BCRYPT_MAX_BYTES} byte")
        return password


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str


class PlayerOut(BaseModel):
    email: str
    display_name: str
    daily_minutes: int
    claimed_rating: int | None

    @classmethod
    def of(cls, player: Player) -> "PlayerOut":
        return cls(
            email=player.email,
            display_name=player.display_name,
            daily_minutes=player.practice_minutes,
            claimed_rating=player.claimed_rating,
        )


class PlayerUpdate(BaseModel):
    daily_minutes: int | None = Field(default=None, ge=5, le=180)
    claimed_rating: int | None = Field(default=None, ge=400, le=3000)
    """Rating ván tự khai (Lichess hoặc Chess.com), dùng làm tiên nghiệm năng lực."""


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _find_login_session(db: Session, token: str | None) -> LoginSession | None:
    return None if token is None else db.get(LoginSession, _token_hash(token))


def _start_login_session(db: Session, response: Response, player: Player) -> None:
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=_token_hash(token), player_id=player.id))
    db.commit()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax")


def current_player(db: Db, token: SessionToken = None) -> Player:
    login_session = _find_login_session(db, token)
    player = None if login_session is None else db.get(Player, login_session.player_id)
    if player is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bạn cần đăng nhập")
    return player


CurrentPlayer = Annotated[Player, Depends(current_player)]

# Route công khai: chỉ đăng ký, đăng nhập, đăng xuất.
auth_router = APIRouter(prefix="/api/auth")


def player_api_router() -> APIRouter:
    """Router cho API của người chơi: chưa đăng nhập thì bị chặn ở mức router.

    Mọi module có API của người chơi đều tạo router bằng hàm này, để route mới không bị bỏ ngỏ.
    """
    return APIRouter(prefix="/api", dependencies=[Depends(current_player)])


player_router = player_api_router()


@auth_router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Db, response: Response) -> PlayerOut:
    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt())
    player = Player(email=body.email, display_name=body.display_name, password_hash=password_hash)
    db.add(player)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email này đã được đăng ký")
    _start_login_session(db, response, player)
    return PlayerOut.of(player)


@auth_router.post("/login")
def login(body: LoginRequest, db: Db, response: Response) -> PlayerOut:
    player = db.scalars(select(Player).where(Player.email == body.email)).one_or_none()
    stored_hash = _DUMMY_HASH if player is None else player.password_hash
    password_ok = bcrypt.checkpw(body.password.encode(), stored_hash)
    if player is None or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email hoặc mật khẩu không đúng")
    _start_login_session(db, response, player)
    return PlayerOut.of(player)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(db: Db, response: Response, token: SessionToken = None) -> None:
    login_session = _find_login_session(db, token)
    if login_session is not None:
        db.delete(login_session)
        db.commit()
    response.delete_cookie(SESSION_COOKIE)


@player_router.get("/me")
def me(player: CurrentPlayer) -> PlayerOut:
    return PlayerOut.of(player)


@player_router.patch("/me")
def update_me(body: PlayerUpdate, player: CurrentPlayer, db: Db) -> PlayerOut:
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "claimed_rating" in changes and db.scalar(select(Attempt.id).where(Attempt.player_id == player.id).limit(1)):
        # Rating ván là tiên nghiệm của năng lực: đổi sau lần giải đầu tiên sẽ viết lại cả lịch sử năng lực.
        raise HTTPException(status.HTTP_409_CONFLICT, "Rating ván chỉ khai được trước lần giải đầu tiên")
    for field, value in changes.items():
        setattr(player, field, value)
    db.commit()
    return PlayerOut.of(player)
