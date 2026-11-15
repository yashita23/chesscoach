"""Năng lực của người chơi, tính lại từ lịch sử lần giải trong DB."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from chesscoach.ability import Ability, Observation, ProbabilityCalibration, replay, replay_with_predictions
from chesscoach.db import Attempt
from chesscoach.puzzles import PuzzleCatalog
from chesscoach.skills import skills_of


def _labeled_attempts(db: Session, player_id: int | None = None) -> list[Attempt]:
    query = select(Attempt).where(Attempt.correct.is_not(None), Attempt.puzzle_rating.is_not(None))
    if player_id is not None:
        query = query.where(Attempt.player_id == player_id)
    return list(db.scalars(query).all())


def _decided(a: Attempt) -> tuple[datetime, int]:
    return (a.decided_at or a.started_at, a.id)


def _observation(a: Attempt) -> Observation:
    return Observation(skills=skills_of(a.themes), rating=float(a.puzzle_rating or 0), correct=bool(a.correct))


def player_ability(db: Session, player_id: int) -> Ability:
    """Chạy lại mô hình năng lực trên các lần giải đã có nhãn, theo thứ tự lúc chốt nhãn."""
    return replay(_observation(a) for a in sorted(_labeled_attempts(db, player_id), key=_decided))


@dataclass
class CalibrationCache:
    """Hiệu chỉnh xác suất chung cho cả app, fit lại khi số lần giải đã có nhãn thay đổi."""

    min_attempts: int
    labeled: int = -1
    calibration: ProbabilityCalibration = ProbabilityCalibration()

    def get(self, db: Session) -> ProbabilityCalibration:
        attempts = _labeled_attempts(db)
        if len(attempts) != self.labeled:
            self.labeled = len(attempts)
            self.calibration = fit_calibration(attempts, self.min_attempts)
        return self.calibration


def fit_calibration(attempts: list[Attempt], min_attempts: int) -> ProbabilityCalibration:
    """Fit a, b trên xác suất mà mô hình đã dự đoán cho mọi lần giải (trước khi biết kết quả).

    Chưa đủ `min_attempts` lần giải đã có nhãn thì không hiệu chỉnh.
    """
    if len(attempts) < min_attempts:
        return ProbabilityCalibration()
    by_player: dict[int, list[Attempt]] = defaultdict(list)
    for a in attempts:
        by_player[a.player_id].append(a)
    predictions: list[float] = []
    outcomes: list[bool] = []
    for history in by_player.values():
        history.sort(key=_decided)
        _, predicted = replay_with_predictions(_observation(a) for a in history)
        predictions.extend(predicted)
        outcomes.extend(bool(a.correct) for a in history)
    return ProbabilityCalibration.fit(predictions, outcomes)


def backfill_attempt_snapshots(session_factory: sessionmaker[Session], catalog: PuzzleCatalog) -> None:
    """Điền rating và chủ đề cho các lần giải tạo trước khi có ảnh chụp bài tập."""
    with session_factory() as db:
        for attempt in db.scalars(select(Attempt).where(Attempt.puzzle_rating.is_(None))):
            puzzle = catalog.get(attempt.puzzle_id)
            if puzzle is not None:
                attempt.puzzle_rating = puzzle.rating
                attempt.themes = puzzle.themes
        db.commit()
