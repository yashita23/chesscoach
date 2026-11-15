"""API buổi luyện: danh sách bài tập cho lần luyện tiếp theo, tính lại sau mỗi lần giải."""

from typing import Literal

import chess
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chesscoach.ability import ProbabilityCalibration
from chesscoach.ability_history import player_ability
from chesscoach.auth import CurrentPlayer, Db, player_api_router
from chesscoach.db import DEFAULT_DAILY_MINUTES, Attempt, Player
from chesscoach.deps import Calibration, Catalog
from chesscoach.recommend import DEFAULT_SESSION, Scored, score_candidates, select_session, session_size, target_rating
from chesscoach.puzzles import PuzzleCatalog
from chesscoach.skills import SKILLS_BY_ID
from chesscoach.solving import board_at, player_color

router = player_api_router()


class ScoreOut(BaseModel):
    total: float
    fit: float
    """−λ·|p − 0,7|: càng gần 0 càng vừa sức."""
    exploration: float
    """Thưởng cho kỹ năng mà hệ thống còn chưa chắc về người chơi."""
    quality: float


class SkillRef(BaseModel):
    id: str
    name: str


class SessionItemOut(BaseModel):
    puzzle_id: str
    fen: str
    """Thế cờ sau nước đầu của đối thủ, tới lượt người chơi."""
    player_color: Literal["white", "black"]
    rating: int
    predicted_p: float
    skills: list[SkillRef]
    score: ScoreOut


class SessionOut(BaseModel):
    daily_minutes: int
    size: int
    target_rating: float
    """Rating bài tập cho p ≈ 0,7 với năng lực chung hiện tại."""
    items: list[SessionItemOut]


def _item(s: Scored) -> SessionItemOut:
    return SessionItemOut(
        puzzle_id=s.puzzle.id,
        fen=board_at(s.puzzle, 1).fen(),
        player_color="white" if player_color(s.puzzle) == chess.WHITE else "black",
        rating=s.puzzle.rating,
        predicted_p=round(s.p, 4),
        skills=[SkillRef(id=k, name=SKILLS_BY_ID[k].name) for k in sorted(s.skills)],
        score=ScoreOut(
            total=round(s.score.total, 4),
            fit=round(s.score.fit, 4),
            exploration=round(s.score.exploration, 4),
            quality=round(s.score.quality, 4),
        ),
    )


@router.get("/session")
def get_session(player: CurrentPlayer, db: Db, catalog: Catalog, calibration: Calibration) -> SessionOut:
    """Buổi luyện tiếp theo. Giữ nguyên giữa các lần gọi; đổi sau mỗi lần giải được chốt nhãn."""
    return build_session(player, db, catalog, calibration.get(db))


def build_session(player: Player, db: Session, catalog: PuzzleCatalog, probability: ProbabilityCalibration) -> SessionOut:
    config = DEFAULT_SESSION
    minutes = player.daily_minutes or DEFAULT_DAILY_MINUTES
    size = session_size(minutes, config)
    ability = player_ability(db, player.id)
    center = target_rating(ability, probability, config)
    attempted = db.scalars(select(Attempt.puzzle_id).where(Attempt.player_id == player.id)).all()
    labeled = db.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.player_id == player.id, Attempt.correct.is_not(None))
    )
    puzzles = catalog.candidates(
        center - config.window, center + config.window, attempted, config.candidate_pool, seed=f"{player.id}:{labeled}"
    )
    chosen = select_session(score_candidates(ability, probability, puzzles, config), size, config)
    return SessionOut(daily_minutes=minutes, size=size, target_rating=round(center, 1), items=[_item(s) for s in chosen])
