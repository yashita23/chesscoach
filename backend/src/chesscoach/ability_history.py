"""Năng lực của người chơi, tính lại từ lịch sử lần giải trong DB."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from chesscoach.ability import Ability, Observation, replay
from chesscoach.db import Attempt
from chesscoach.puzzles import PuzzleCatalog
from chesscoach.skills import skills_of


def player_ability(db: Session, player_id: int) -> Ability:
    """Chạy lại mô hình năng lực trên các lần giải đã có nhãn, theo thứ tự lúc chốt nhãn."""
    attempts = db.scalars(
        select(Attempt).where(
            Attempt.player_id == player_id,
            Attempt.correct.is_not(None),
            Attempt.puzzle_rating.is_not(None),
        )
    ).all()

    def decided(a: Attempt) -> tuple[datetime, int]:
        return (a.decided_at or a.started_at, a.id)

    return replay(
        Observation(
            skills=skills_of(a.themes),
            rating=float(a.puzzle_rating or 0),
            correct=bool(a.correct),
        )
        for a in sorted(attempts, key=decided)
    )


def backfill_attempt_snapshots(session_factory: sessionmaker[Session], catalog: PuzzleCatalog) -> None:
    """Điền rating và chủ đề cho các lần giải tạo trước khi có ảnh chụp bài tập."""
    with session_factory() as db:
        for attempt in db.scalars(select(Attempt).where(Attempt.puzzle_rating.is_(None))):
            puzzle = catalog.get(attempt.puzzle_id)
            if puzzle is not None:
                attempt.puzzle_rating = puzzle.rating
                attempt.themes = puzzle.themes
        db.commit()
