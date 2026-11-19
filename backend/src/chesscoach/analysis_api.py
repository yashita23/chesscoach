"""REST API cho phân tích ván cờ và danh sách lỗi của người chơi (Seam 4).

Cung cấp:
- GET /api/games/{id}/analysis: Chi tiết phân tích một ván cờ.
- GET /api/games/analysis/mistakes: Danh sách lỗi chiến thuật của người chơi có lọc và phân trang.

Các nguyên tắc:
- Read-only đối với CSDL, tuyệt đối không gọi EngineAdapter / GameAnalyzer trong request cycle.
- Phân quyền nghiêm ngặt: người dùng chỉ xem được dữ liệu của chính mình.
- Phân trang chuẩn với total tính sau filter, trước pagination.
- Sắp xếp có tie-breaker ổn định qua ID.
"""

from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from chesscoach.auth import CurrentPlayer, Db, player_api_router
from chesscoach.db import Game, GameMistakeRecord
from chesscoach.skills import SKILLS

VALID_SKILL_IDS: frozenset[str] = frozenset(s.id for s in SKILLS)
VALID_GAME_PHASES: frozenset[str] = frozenset({"opening", "middlegame", "endgame"})

router = player_api_router()


class MistakeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ply: int
    move_number: int
    move_san: str
    move_uci: str
    fen: str
    win_before: float
    win_after: float
    win_loss: float
    skill_id: str
    motif: str
    game_phase: str
    best_move: str | None = None
    refutation_move: str | None = None


class GameAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    game_id: int
    platform: str
    platform_game_id: str
    perf_type: str
    played_at: datetime
    analysis_status: str
    analyzed_at: datetime | None = None
    mistakes: list[MistakeOut]


class PlayerMistakeItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    game_id: int
    platform: str
    platform_game_id: str
    played_at: datetime
    ply: int
    move_number: int
    move_san: str
    move_uci: str
    fen: str
    win_before: float
    win_after: float
    win_loss: float
    skill_id: str
    motif: str
    game_phase: str
    best_move: str | None = None
    refutation_move: str | None = None


class PlayerMistakesListOut(BaseModel):
    total: int
    mistakes: list[PlayerMistakeItemOut]


@router.get("/games/{game_id}/analysis", response_model=GameAnalysisOut)
def get_game_analysis(
    game_id: int,
    player: CurrentPlayer,
    db: Db,
) -> GameAnalysisOut:
    """Xem chi tiết kết quả phân tích của một ván cờ thuộc sở hữu của người chơi."""
    game = db.scalar(
        select(Game).where(Game.id == game_id, Game.player_id == player.id)
    )
    if game is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy ván cờ",
        )

    mistakes: list[MistakeOut] = []
    if game.analysis_status == "completed":
        records = db.scalars(
            select(GameMistakeRecord)
            .where(GameMistakeRecord.game_id == game.id)
            .order_by(GameMistakeRecord.ply.asc())
        ).all()
        mistakes = [MistakeOut.model_validate(r) for r in records]

    return GameAnalysisOut(
        game_id=game.id,
        platform=game.platform,
        platform_game_id=game.platform_game_id,
        perf_type=game.perf_type,
        played_at=game.played_at,
        analysis_status=game.analysis_status,
        analyzed_at=game.analyzed_at,
        mistakes=mistakes,
    )


OrderByOption = Literal[
    "played_at_desc", "played_at_asc", "win_loss_desc", "win_loss_asc"
]


@router.get("/games/analysis/mistakes", response_model=PlayerMistakesListOut)
def list_player_mistakes(
    player: CurrentPlayer,
    db: Db,
    skill_id: str | None = None,
    game_phase: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    order_by: OrderByOption = "played_at_desc",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PlayerMistakesListOut:
    """Liệt kê các lỗi chiến thuật của người chơi có lọc theo kỹ năng, giai đoạn, thời gian và phân trang."""
    # 1. Validation query parameters
    if skill_id is not None and skill_id not in VALID_SKILL_IDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"skill_id '{skill_id}' không hợp lệ",
        )
    if game_phase is not None and game_phase not in VALID_GAME_PHASES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"game_phase '{game_phase}' không hợp lệ",
        )
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="from_date không được lớn hơn to_date",
        )

    # 2. Xây dựng điều kiện lọc
    filters = [GameMistakeRecord.player_id == player.id]
    if skill_id is not None:
        filters.append(GameMistakeRecord.skill_id == skill_id)
    if game_phase is not None:
        filters.append(GameMistakeRecord.game_phase == game_phase)
    if from_date is not None:
        from_cmp = (
            from_date.astimezone(timezone.utc).replace(tzinfo=None)
            if from_date.tzinfo
            else from_date
        )
        filters.append(Game.played_at >= from_cmp)
    if to_date is not None:
        to_cmp = (
            to_date.astimezone(timezone.utc).replace(tzinfo=None)
            if to_date.tzinfo
            else to_date
        )
        filters.append(Game.played_at <= to_cmp)

    # 3. Tính total sau filter, trước pagination
    count_stmt = (
        select(func.count(GameMistakeRecord.id))
        .join(Game, GameMistakeRecord.game_id == Game.id)
        .where(*filters)
    )
    total = db.scalar(count_stmt) or 0

    # 4. Sắp xếp với tie-breaker id ổn định
    data_query = (
        select(
            GameMistakeRecord,
            Game.platform,
            Game.platform_game_id,
            Game.played_at,
        )
        .join(Game, GameMistakeRecord.game_id == Game.id)
        .where(*filters)
    )

    if order_by == "played_at_desc":
        data_query = data_query.order_by(
            Game.played_at.desc(), GameMistakeRecord.id.desc()
        )
    elif order_by == "played_at_asc":
        data_query = data_query.order_by(
            Game.played_at.asc(), GameMistakeRecord.id.asc()
        )
    elif order_by == "win_loss_desc":
        data_query = data_query.order_by(
            GameMistakeRecord.win_loss.desc(), GameMistakeRecord.id.desc()
        )
    elif order_by == "win_loss_asc":
        data_query = data_query.order_by(
            GameMistakeRecord.win_loss.asc(), GameMistakeRecord.id.asc()
        )

    # 5. Phân trang
    paged_query = data_query.limit(limit).offset(offset)
    results = db.execute(paged_query).all()

    items: list[PlayerMistakeItemOut] = []
    for record, platform, platform_game_id, played_at in results:
        items.append(
            PlayerMistakeItemOut(
                id=record.id,
                game_id=record.game_id,
                platform=platform,
                platform_game_id=platform_game_id,
                played_at=played_at,
                ply=record.ply,
                move_number=record.move_number,
                move_san=record.move_san,
                move_uci=record.move_uci,
                fen=record.fen,
                win_before=record.win_before,
                win_after=record.win_after,
                win_loss=record.win_loss,
                skill_id=record.skill_id,
                motif=record.motif,
                game_phase=record.game_phase,
                best_move=record.best_move,
                refutation_move=record.refutation_move,
            )
        )

    return PlayerMistakesListOut(total=total, mistakes=items)
