import hashlib
import secrets
from collections.abc import Iterator
from typing import Annotated

import bcrypt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from chesscoach.db import LoginSession, Player

SESSION_COOKIE = "chesscoach_session"
BCRYPT_MAX_BYTES = 72


def get_db(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as db:
        yield db


Db = Annotated[Session, Depends(get_db)]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("password")
    @classmethod
    def _vua_gioi_han_bcrypt(cls, password: str) -> str:
        if len(password.encode()) > BCRYPT_MAX_BYTES:
            raise ValueError(f"Mật khẩu dài tối đa {BCRYPT_MAX_BYTES} byte")
        return password


class PlayerOut(BaseModel):
    email: str
    display_name: str


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _start_session(db: Session, response: Response, player: Player) -> None:
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=_token_hash(token), player_id=player.id))
    db.commit()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax")


def current_player(
    db: Db, token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None
) -> Player:
    if token is not None:
        session = db.get(LoginSession, _token_hash(token))
        if session is not None:
            player = db.get(Player, session.player_id)
            if player is not None:
                return player
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bạn cần đăng nhập")


CurrentPlayer = Annotated[Player, Depends(current_player)]

router = APIRouter(prefix="/api")


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Db, response: Response) -> PlayerOut:
    email = body.email.lower()
    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt())
    player = Player(email=email, display_name=body.display_name, password_hash=password_hash)
    db.add(player)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email này đã được đăng ký")
    _start_session(db, response, player)
    return PlayerOut(email=player.email, display_name=player.display_name)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/auth/login")
def login(body: LoginRequest, db: Db, response: Response) -> PlayerOut:
    player = db.scalars(select(Player).where(Player.email == body.email.lower())).one_or_none()
    if player is None or not bcrypt.checkpw(body.password.encode(), player.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email hoặc mật khẩu không đúng")
    _start_session(db, response, player)
    return PlayerOut(email=player.email, display_name=player.display_name)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: Db, response: Response, token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None
) -> None:
    if token is not None:
        session = db.get(LoginSession, _token_hash(token))
        if session is not None:
            db.delete(session)
            db.commit()
    response.delete_cookie(SESSION_COOKIE)


@router.get("/me")
def me(player: CurrentPlayer) -> PlayerOut:
    return PlayerOut(email=player.email, display_name=player.display_name)

