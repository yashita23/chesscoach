"""Năng lực của người chơi, tính lại từ lịch sử lần giải trong DB."""

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from chesscoach.ability import Ability, Observation, ProbabilityCalibration, replay, replay_with_predictions
from chesscoach.db import Attempt, Player
from chesscoach.puzzles import PuzzleCatalog
from chesscoach.skills import skills_of


def _labeled_attempts(db: Session, player_id: int | None = None) -> list[Attempt]:
    query = select(Attempt).where(Attempt.correct.is_not(None), Attempt.puzzle_rating.is_not(None))
    if player_id is not None:
        query = query.where(Attempt.player_id == player_id)
    return list(db.scalars(query).all())


def _decided_order(a: Attempt) -> tuple[datetime, int]:
    return (a.decided_at or a.started_at, a.id)


def _observation(a: Attempt) -> Observation:
    return Observation(skills=skills_of(a.themes), rating=float(a.puzzle_rating or 0), correct=bool(a.correct))


RATING_PRIOR_MIN, RATING_PRIOR_MAX = 400, 2800


def prior_ability(player: Player) -> Ability:
    """Năng lực trước lần giải đầu tiên: rating ván tự khai quy đổi thô (dùng thẳng, kẹp trong 400–2800),
    không khai thì 1500. Độ bất định ban đầu σ = 350 vẫn lớn như mọi người chơi mới."""
    if player.claimed_rating is None:
        return Ability()
    return Ability(theta=float(min(max(player.claimed_rating, RATING_PRIOR_MIN), RATING_PRIOR_MAX)))


def player_ability(db: Session, player: Player) -> Ability:
    """Chạy lại mô hình năng lực từ tiên nghiệm, trên các lần giải đã có nhãn, theo thứ tự lúc chốt nhãn."""
    history = sorted(_labeled_attempts(db, player.id), key=_decided_order)
    return replay((_observation(a) for a in history), start=prior_ability(player))


@dataclass
class CalibrationCache:
    """Hiệu chỉnh xác suất chung cho cả app.

    Mỗi request chỉ đếm số lần giải đã có nhãn. Fit lại (chạy lại mô hình cho mọi người chơi) chỉ khi vừa vượt
    ngưỡng `min_attempts`, hoặc số lần giải đã tăng ít nhất `refit_growth` (và ít nhất `refit_min_new`) so với
    lần fit trước. An toàn khi nhiều request chạy song song.
    """

    min_attempts: int
    refit_growth: float = 0.1
    refit_min_new: int = 50
    fitted_at: int = -1
    calibration: ProbabilityCalibration = ProbabilityCalibration()
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get(self, db: Session) -> ProbabilityCalibration:
        labeled = db.scalar(
            select(func.count()).select_from(Attempt).where(
                Attempt.correct.is_not(None), Attempt.puzzle_rating.is_not(None)
            )
        ) or 0
        with self._lock:
            if labeled < self.min_attempts:
                self.calibration, self.fitted_at = ProbabilityCalibration(), -1  # chưa đủ dữ liệu: không hiệu chỉnh
            elif self.fitted_at < 0 or labeled - self.fitted_at >= max(
                self.refit_min_new, self.refit_growth * self.fitted_at
            ):
                priors = {p.id: prior_ability(p) for p in db.scalars(select(Player))}
                self.calibration = fit_calibration(_labeled_attempts(db), self.min_attempts, priors)
                self.fitted_at = labeled
            return self.calibration


def fit_calibration(
    attempts: list[Attempt], min_attempts: int, priors: dict[int, Ability]
) -> ProbabilityCalibration:
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
    for player_id, history in by_player.items():
        history.sort(key=_decided_order)
        start = priors.get(player_id)
        _, predicted = replay_with_predictions((_observation(a) for a in history), start)
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
