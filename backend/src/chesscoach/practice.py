"""API buổi luyện: danh sách bài tập cho lần luyện tiếp theo, tính lại sau mỗi lần giải."""

from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chesscoach.ability import ProbabilityCalibration
from chesscoach.ability_history import player_ability
from chesscoach.auth import CurrentPlayer, Db, player_api_router
from chesscoach.db import Attempt, Player
from chesscoach.deps import Calibration, Catalog, Placement, Practice
from chesscoach.placement import placement_status
from chesscoach.puzzles import Puzzle, PuzzleCatalog
from chesscoach.recommend import PracticeConfig, PracticePlan, Scored, plan_practice, score_candidates
from chesscoach.skills import SKILLS_BY_ID
from chesscoach.solving import board_at, color_name

router = player_api_router()


def plan_for(
    player: Player, db: Session, catalog: PuzzleCatalog, calibration: ProbabilityCalibration, config: PracticeConfig
) -> PracticePlan:
    """Buổi luyện của người chơi.

    Thứ tự ứng viên cố định theo (người chơi, số lần giải đã có nhãn), nên buổi luyện giữ nguyên giữa các lần gọi
    và chỉ đổi khi có lần giải mới được chốt nhãn.
    """
    attempted = db.scalars(select(Attempt.puzzle_id).where(Attempt.player_id == player.id)).all()
    labeled = db.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.player_id == player.id, Attempt.correct.is_not(None))
    )
    seed = f"{player.id}:{labeled}"

    def find_candidates(low: float, high: float) -> list[Puzzle]:
        return catalog.candidates(low, high, attempted, config.candidate_pool, seed=seed)

    return plan_practice(player_ability(db, player), calibration, player.practice_minutes, find_candidates, config)


class SkillRef(BaseModel):
    id: str
    name: str


class ScoreOut(BaseModel):
    total: float
    fit: float
    """−λ·|p − 0,7|: càng gần 0 càng vừa sức."""
    exploration: float
    """Thưởng cho kỹ năng mà hệ thống còn chưa chắc về người chơi."""
    quality: float


class PracticeItemOut(BaseModel):
    puzzle_id: str
    fen: str
    """Thế cờ sau nước đầu của đối thủ, tới lượt người chơi."""
    player_color: Literal["white", "black"]
    rating: int
    predicted_p: float
    skills: list[SkillRef]
    score: ScoreOut


class PlacementOut(BaseModel):
    total: int
    completed: int
    started: bool
    """Đã mở lần giải đầu tiên của bài kiểm tra; từ đó dải không đổi nữa."""


class PracticeOut(BaseModel):
    mode: Literal["placement", "practice"]
    """placement: người chơi mới đang làm bài kiểm tra đầu vào; items là các bài tập còn lại của nó."""
    placement: PlacementOut | None
    daily_minutes: int
    size: int
    target_rating: float
    """Rating bài tập cho p ≈ 0,7 với năng lực chung hiện tại."""
    items: list[PracticeItemOut]


def _item(s: Scored) -> PracticeItemOut:
    return PracticeItemOut(
        puzzle_id=s.puzzle.id,
        fen=board_at(s.puzzle, 1).fen(),
        player_color=color_name(s.puzzle),
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


@router.get("/practice")
def get_practice(
    player: CurrentPlayer,
    db: Db,
    catalog: Catalog,
    calibration: Calibration,
    config: Practice,
    placement_sets: Placement,
) -> PracticeOut:
    """Buổi luyện tiếp theo; với người chơi mới là các bài tập còn lại của bài kiểm tra đầu vào."""
    probability = calibration.get(db)
    progress = placement_status(db, player, placement_sets)
    if progress is not None:
        puzzles = [p for pid in progress.remaining if (p := catalog.get(pid)) is not None]
        scored = score_candidates(player_ability(db, player), probability, puzzles, config)
        return PracticeOut(
            mode="placement",
            placement=PlacementOut(total=len(progress.puzzle_ids), completed=progress.completed, started=progress.started),
            daily_minutes=player.practice_minutes,
            size=len(progress.puzzle_ids),
            target_rating=progress.target_rating,
            items=[_item(s) for s in scored],
        )
    plan = plan_for(player, db, catalog, probability, config)
    return PracticeOut(
        mode="practice",
        placement=None,
        daily_minutes=player.practice_minutes,
        size=plan.size,
        target_rating=round(plan.target_rating, 1),
        items=[_item(s) for s in plan.items],
    )
