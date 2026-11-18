from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from chesscoach.auth import CurrentPlayer, Db, player_api_router
from chesscoach.db import Game, LinkedAccount
from chesscoach.games_source import GameSource, RateLimitError, SourceNetworkError
from chesscoach.games_sync import AlreadySyncingError, SyncEngine, SyncJob

router = player_api_router()


class LinkedAccountOut(BaseModel):
    id: int
    platform: str
    username: str
    last_synced_at: datetime | None
    last_game_at: datetime | None
    games_count: int


class SyncJobOut(BaseModel):
    status: str
    platform: str
    current: int
    total: int
    new_games_count: int
    error: str | None
    last_synced_at: datetime | None = None


class LinkLichessRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)


class LinkAccountResponse(BaseModel):
    account: LinkedAccountOut
    job: SyncJobOut


class GameOut(BaseModel):
    id: int
    platform: str
    platform_game_id: str
    perf_type: str
    played_at: datetime
    has_evals: bool


class GameListOut(BaseModel):
    total: int
    games: list[GameOut]


def _job_out(job: SyncJob, last_synced_at: datetime | None = None) -> SyncJobOut:
    return SyncJobOut(
        status=job.status,
        platform=job.platform,
        current=job.current,
        total=job.total,
        new_games_count=job.new_games_count,
        error=job.error,
        last_synced_at=last_synced_at,
    )


@router.post("/accounts/lichess", response_model=LinkAccountResponse, status_code=status.HTTP_201_CREATED)
def link_lichess(
    body: LinkLichessRequest,
    player: CurrentPlayer,
    db: Db,
    request: Request,
) -> LinkAccountResponse:
    source: GameSource = request.app.state.game_source
    sync_engine: SyncEngine = request.app.state.sync_engine

    clean_username = body.username.strip()
    if not clean_username:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username không được để trống")

    try:
        exists = source.check_user_exists(clean_username)
    except RateLimitError as e:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Lichess: Quá nhiều yêu cầu (HTTP 429). Vui lòng thử lại sau.",
        ) from e
    except SourceNetworkError as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Không thể kết nối tới Lichess: {e}",
        ) from e

    if not exists:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Tài khoản Lichess '{clean_username}' không tồn tại",
        )

    account = db.scalars(
        select(LinkedAccount).where(
            LinkedAccount.player_id == player.id,
            LinkedAccount.platform == "lichess",
        )
    ).one_or_none()

    if account is None:
        account = LinkedAccount(player_id=player.id, platform="lichess", username=clean_username)
        db.add(account)
        db.commit()
        db.refresh(account)
    else:
        if account.username.lower() != clean_username.lower():
            account.username = clean_username
            account.last_synced_at = None
            account.last_game_at = None
            db.commit()
            db.refresh(account)

    try:
        job = sync_engine.start_sync(player.id, "lichess", source)
    except AlreadySyncingError:
        job = sync_engine.get_status(player.id)

    games_count = db.scalar(
        select(func.count(Game.id)).where(Game.account_id == account.id)
    ) or 0

    acc_out = LinkedAccountOut(
        id=account.id,
        platform=account.platform,
        username=account.username,
        last_synced_at=account.last_synced_at,
        last_game_at=account.last_game_at,
        games_count=games_count,
    )
    return LinkAccountResponse(account=acc_out, job=_job_out(job, account.last_synced_at))


@router.get("/accounts", response_model=list[LinkedAccountOut])
def list_accounts(player: CurrentPlayer, db: Db) -> list[LinkedAccountOut]:
    accounts = db.scalars(
        select(LinkedAccount).where(LinkedAccount.player_id == player.id)
    ).all()

    out: list[LinkedAccountOut] = []
    for acc in accounts:
        count = db.scalar(
            select(func.count(Game.id)).where(Game.account_id == acc.id)
        ) or 0
        out.append(
            LinkedAccountOut(
                id=acc.id,
                platform=acc.platform,
                username=acc.username,
                last_synced_at=acc.last_synced_at,
                last_game_at=acc.last_game_at,
                games_count=count,
            )
        )
    return out


@router.post("/sync/lichess", response_model=SyncJobOut)
def sync_lichess(
    player: CurrentPlayer,
    db: Db,
    request: Request,
) -> SyncJobOut:
    source: GameSource = request.app.state.game_source
    sync_engine: SyncEngine = request.app.state.sync_engine

    account = db.scalars(
        select(LinkedAccount).where(
            LinkedAccount.player_id == player.id,
            LinkedAccount.platform == "lichess",
        )
    ).one_or_none()

    if account is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Chưa liên kết tài khoản Lichess",
        )

    try:
        job = sync_engine.start_sync(player.id, "lichess", source)
    except AlreadySyncingError:
        job = sync_engine.get_status(player.id)

    return _job_out(job, account.last_synced_at)


@router.get("/sync/status", response_model=SyncJobOut)
def get_sync_status(
    player: CurrentPlayer,
    db: Db,
    request: Request,
) -> SyncJobOut:
    sync_engine: SyncEngine = request.app.state.sync_engine
    job = sync_engine.get_status(player.id)

    account = db.scalars(
        select(LinkedAccount).where(
            LinkedAccount.player_id == player.id,
            LinkedAccount.platform == "lichess",
        )
    ).one_or_none()

    return _job_out(job, account.last_synced_at if account else None)


@router.get("/games", response_model=GameListOut)
def list_games(
    player: CurrentPlayer,
    db: Db,
    limit: int = 50,
    offset: int = 0,
) -> GameListOut:
    total = db.scalar(
        select(func.count(Game.id)).where(Game.player_id == player.id)
    ) or 0

    games = db.scalars(
        select(Game)
        .where(Game.player_id == player.id)
        .order_by(Game.played_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return GameListOut(
        total=total,
        games=[
            GameOut(
                id=g.id,
                platform=g.platform,
                platform_game_id=g.platform_game_id,
                perf_type=g.perf_type,
                played_at=g.played_at,
                has_evals=g.has_evals,
            )
            for g in games
        ],
    )

