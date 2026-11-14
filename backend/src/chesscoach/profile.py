"""Hồ sơ kỹ năng: năng lực của người chơi, tính lại từ các lần giải đã có nhãn."""

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from pydantic import BaseModel

from chesscoach.ability import Ability, Observation, replay
from chesscoach.auth import CurrentPlayer, Db, player_api_router
from chesscoach.db import Attempt
from chesscoach.puzzles import PuzzleCatalog
from chesscoach.skills import GROUPS, SKILLS, skills_of

router = player_api_router()

Z_95 = 1.96


def player_ability(db: Session, player_id: int) -> Ability:
    attempts = db.scalars(
        select(Attempt)
        .where(
            Attempt.player_id == player_id,
            Attempt.correct.is_not(None),
            Attempt.puzzle_rating.is_not(None),
        )
        .order_by(Attempt.started_at, Attempt.id)
    ).all()
    return replay(
        Observation(
            skills=skills_of((a.puzzle_themes or "").split()),
            rating=float(a.puzzle_rating or 0),
            correct=bool(a.correct),
        )
        for a in attempts
    )


def backfill_attempt_snapshots(session_factory: sessionmaker[Session], catalog: PuzzleCatalog) -> None:
    """Điền rating và chủ đề cho các lần giải tạo trước khi có ảnh chụp bài tập."""
    with session_factory() as db:
        for attempt in db.scalars(select(Attempt).where(Attempt.puzzle_rating.is_(None))):
            puzzle = catalog.get(attempt.puzzle_id)
            if puzzle is not None:
                attempt.puzzle_rating = puzzle.rating
                attempt.puzzle_themes = " ".join(puzzle.themes)
        db.commit()


class SkillOut(BaseModel):
    id: str
    name: str
    description: str
    group: str
    rating: float
    """Năng lực ở kỹ năng này (θ + θₖ), cùng thang rating bài tập."""
    deviation: float
    ci_low: float
    ci_high: float
    attempts: int
    enough_data: bool
    """False khi chưa có lần giải nào: giao diện hiện "chưa đủ dữ liệu"."""


class GroupOut(BaseModel):
    id: str
    name: str
    rating: float | None
    """Trung bình năng lực các kỹ năng đã có dữ liệu trong nhóm; None nếu chưa có."""
    skills: list[str]


class ProfileOut(BaseModel):
    theta: float
    ci_low: float
    ci_high: float
    attempts: int
    skills: list[SkillOut]
    groups: list[GroupOut]


@router.get("/profile")
def get_profile(player: CurrentPlayer, db: Db) -> ProfileOut:
    ability = player_ability(db, player.id)
    skills = []
    for s in SKILLS:
        rating = ability.skill_rating(s.id)
        half = Z_95 * ability.skill_sigma(s.id)
        n = ability.skill(s.id).attempts
        skills.append(
            SkillOut(
                id=s.id,
                name=s.name,
                description=s.description,
                group=s.group,
                rating=round(rating, 1),
                deviation=round(ability.skill(s.id).deviation, 1),
                ci_low=round(rating - half, 1),
                ci_high=round(rating + half, 1),
                attempts=n,
                enough_data=n > 0,
            )
        )
    groups = []
    for g in GROUPS:
        members = [s for s in skills if s.group == g.id]
        known = [s.rating for s in members if s.enough_data]
        groups.append(
            GroupOut(
                id=g.id,
                name=g.name,
                rating=round(sum(known) / len(known), 1) if known else None,
                skills=[s.id for s in members],
            )
        )
    half = Z_95 * ability.sigma
    return ProfileOut(
        theta=round(ability.theta, 1),
        ci_low=round(ability.theta - half, 1),
        ci_high=round(ability.theta + half, 1),
        attempts=ability.attempts,
        skills=skills,
        groups=groups,
    )
