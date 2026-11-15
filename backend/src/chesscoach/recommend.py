"""Buổi luyện: chọn top-K bài tập vừa sức và đa dạng kỹ năng. Hàm thuần: không đọc DB, không biết HTTP.

    điểm = −λ_vừa_sức·|p − p*| + λ_thăm_dò·max σₖ / σ₀ + λ_chất_lượng·Popularity / 100

p là xác suất giải đúng đã hiệu chỉnh. Ứng viên lấy trong khoảng ±`window` quanh rating bài tập cho p = p*
(với thang s của E1b, rating đó thấp hơn năng lực chung khoảng 440). Chọn top-K bằng MMR: mỗi bước lấy bài tập
có λ_mmr·điểm − (1 − λ_mmr)·độ trùng kỹ năng với các bài tập đã chọn lớn nhất, và không kỹ năng nào vượt
`max_skill_share` của buổi luyện. Thành phần điểm yếu (λ₂) thêm ở #9.
"""

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from chesscoach.ability import Ability, ProbabilityCalibration, predict
from chesscoach.puzzles import Puzzle
from chesscoach.skills import skills_of


@dataclass(frozen=True)
class SessionConfig:
    target_p: float = 0.7
    window: float = 300.0
    """Nửa độ rộng khoảng rating của ứng viên, quanh rating cho p = target_p."""
    candidate_pool: int = 300
    lambda_fit: float = 1.0
    lambda_exploration: float = 0.1
    lambda_quality: float = 0.05
    mmr_lambda: float = 0.7
    max_skill_share: float = 0.4
    seconds_per_puzzle: float = 105.0
    """30 phút → 17 bài tập."""
    min_size: int = 3
    max_size: int = 40


DEFAULT_SESSION = SessionConfig()


def session_size(daily_minutes: int, config: SessionConfig = DEFAULT_SESSION) -> int:
    return max(config.min_size, min(config.max_size, round(daily_minutes * 60 / config.seconds_per_puzzle)))


def target_rating(ability: Ability, calibration: ProbabilityCalibration, config: SessionConfig = DEFAULT_SESSION) -> float:
    """Rating bài tập mà người chơi (với năng lực chung) giải đúng với xác suất target_p, sau hiệu chỉnh."""
    raw = calibration.invert(config.target_p)
    return ability.theta - ability.config.scale * math.log(raw / (1 - raw))


@dataclass(frozen=True)
class ScoreParts:
    fit: float
    exploration: float
    quality: float

    @property
    def total(self) -> float:
        return self.fit + self.exploration + self.quality


@dataclass(frozen=True)
class Scored:
    puzzle: Puzzle
    skills: frozenset[str]
    p: float
    """Xác suất giải đúng đã hiệu chỉnh."""
    score: ScoreParts


def score_candidates(
    ability: Ability,
    calibration: ProbabilityCalibration,
    puzzles: Iterable[Puzzle],
    config: SessionConfig = DEFAULT_SESSION,
) -> list[Scored]:
    scored = []
    for puzzle in puzzles:
        skills = skills_of(puzzle.themes)
        p = calibration.apply(predict(ability, skills, puzzle.rating))
        uncertainty = max(ability.skill_sigma(k) for k in skills) / ability.config.initial_sigma
        parts = ScoreParts(
            fit=-config.lambda_fit * abs(p - config.target_p),
            exploration=config.lambda_exploration * uncertainty,
            quality=config.lambda_quality * puzzle.popularity / 100,
        )
        scored.append(Scored(puzzle, skills, p, parts))
    return scored


def _overlap(skills: frozenset[str], chosen: list[Scored]) -> float:
    """Độ trùng kỹ năng lớn nhất (Jaccard) với các bài tập đã chọn."""
    return max((len(skills & c.skills) / len(skills | c.skills) for c in chosen), default=0.0)


def select_session(candidates: list[Scored], size: int, config: SessionConfig = DEFAULT_SESSION) -> list[Scored]:
    """Chọn tối đa `size` bài tập bằng MMR, giới hạn số bài tập của mỗi kỹ năng."""
    cap = max(1, math.floor(config.max_skill_share * size))
    per_skill: Counter[str] = Counter()
    chosen: list[Scored] = []
    remaining = list(candidates)
    while remaining and len(chosen) < size:
        allowed = [c for c in remaining if all(per_skill[k] < cap for k in c.skills)]
        if not allowed:
            break
        best = max(
            allowed,
            key=lambda c: config.mmr_lambda * c.score.total - (1 - config.mmr_lambda) * _overlap(c.skills, chosen),
        )
        chosen.append(best)
        per_skill.update(best.skills)
        remaining.remove(best)
    return chosen
