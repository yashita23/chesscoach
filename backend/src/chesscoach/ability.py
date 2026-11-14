"""Mô hình năng lực: Elo theo kỹ năng (ADR 0002), cùng thang với rating bài tập Lichess (ADR 0003).

Module Python thuần: không đọc DB, không biết HTTP. App và các thí nghiệm đánh giá đều dùng nó.

    p = sigmoid((θ + trung bình θₖ trên các kỹ năng của bài tập − rating bài tập) / s),  s = 400 / ln 10
    sau mỗi lần giải:  θ += K(n)·(y − p),  θₖ += Kₖ(nₖ)·(y − p) với mọi kỹ năng k của bài tập

K và độ bất định σ giảm dần theo số lần giải. Hằng số là lựa chọn ban đầu; lớp đánh giá 1 sẽ hiệu chỉnh.
"""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

SCALE = 400 / math.log(10)
INITIAL_THETA = 1500.0
INITIAL_SIGMA = 350.0


def k_overall(attempts: int) -> float:
    return max(16.0, 64.0 / math.sqrt(1 + attempts / 4))


def k_skill(attempts: int) -> float:
    return max(8.0, 48.0 / math.sqrt(1 + attempts / 4))


def sigma_overall(attempts: int) -> float:
    return max(40.0, INITIAL_SIGMA / math.sqrt(1 + attempts))


def sigma_skill(attempts: int) -> float:
    return max(60.0, INITIAL_SIGMA / math.sqrt(1 + attempts))


@dataclass(frozen=True)
class SkillAbility:
    deviation: float = 0.0
    """θₖ: độ lệch của kỹ năng so với năng lực chung."""
    attempts: int = 0


@dataclass(frozen=True)
class Ability:
    theta: float = INITIAL_THETA
    attempts: int = 0
    skills: Mapping[str, SkillAbility] = field(default_factory=dict)

    def skill(self, skill_id: str) -> SkillAbility:
        return self.skills.get(skill_id, SkillAbility())

    def skill_rating(self, skill_id: str) -> float:
        """Năng lực ở một kỹ năng trên thang rating bài tập: θ + θₖ."""
        return self.theta + self.skill(skill_id).deviation

    def skill_sigma(self, skill_id: str) -> float:
        return sigma_skill(self.skill(skill_id).attempts)

    @property
    def sigma(self) -> float:
        return sigma_overall(self.attempts)


@dataclass(frozen=True)
class Observation:
    """Một lần giải đã có nhãn, đủ để cập nhật năng lực."""

    skills: frozenset[str]
    rating: float
    correct: bool


def predict(ability: Ability, skills: Iterable[str], rating: float) -> float:
    """Xác suất giải đúng một bài tập có các kỹ năng `skills` và rating `rating`."""
    ks = list(skills)
    deviation = sum(ability.skill(k).deviation for k in ks) / len(ks) if ks else 0.0
    return 1 / (1 + math.exp(-(ability.theta + deviation - rating) / SCALE))


def update(ability: Ability, obs: Observation) -> Ability:
    surprise = (1.0 if obs.correct else 0.0) - predict(ability, obs.skills, obs.rating)
    skills = dict(ability.skills)
    for k in obs.skills:
        s = ability.skill(k)
        skills[k] = SkillAbility(s.deviation + k_skill(s.attempts) * surprise, s.attempts + 1)
    return replace(
        ability,
        theta=ability.theta + k_overall(ability.attempts) * surprise,
        attempts=ability.attempts + 1,
        skills=skills,
    )


def replay(observations: Iterable[Observation], start: Ability | None = None) -> Ability:
    """Năng lực sau một chuỗi lần giải theo thứ tự thời gian."""
    ability = start or Ability()
    for obs in observations:
        ability = update(ability, obs)
    return ability
