"""Mô hình năng lực: Elo theo kỹ năng (ADR 0002), cùng thang với rating bài tập Lichess (ADR 0003).

Module Python thuần: không đọc DB, không biết HTTP. App và các thí nghiệm đánh giá đều dùng nó.

    p = sigmoid((θ + trung bình θₖ trên các kỹ năng của bài tập − rating bài tập) / s)
    sau mỗi lần giải:  θ += K(n)·(y − p),  θₖ += Kₖ(nₖ)·(y − p) / |kỹ năng của bài tập|

Bước của θₖ chia đều cho các kỹ năng của bài tập, vì p dùng trung bình θₖ. Khi dự đoán và hiển thị, θₖ được
co về 0 theo nₖ / (nₖ + độ co) để kỹ năng ít dữ liệu không lệch quá xa năng lực chung. K và độ bất định σ
giảm dần theo số lần giải. Mọi hằng số nằm trong `AbilityConfig`, đi kèm từng `Ability`.
"""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

ELO_SCALE = 400 / math.log(10)


@dataclass(frozen=True)
class AbilityConfig:
    """Các hằng số của mô hình năng lực.

    Mặc định là cấu hình tinh chỉnh ở E1b (docs/experiments/e1b-tuning.md): thang s gấp 3 lần Elo vì chênh rating
    dự báo kết quả yếu hơn công thức Elo giả định; K lớn lúc đầu để năng lực hội tụ nhanh rồi giảm xuống thấp.
    Bước hiệu chỉnh xác suất (`ProbabilityCalibration`) học thêm phần chênh còn lại từ dữ liệu của app.
    """

    scale: float = 3 * ELO_SCALE
    """Thang s của sigmoid; s lớn hơn thì xác suất bớt trải về hai đầu."""
    initial_theta: float = 1500.0
    k_overall_start: float = 256.0
    k_overall_min: float = 8.0
    k_skill_start: float = 192.0
    k_skill_min: float = 4.0
    k_decay: float = 4.0
    """K giảm theo 1/√(1 + n/k_decay)."""
    shrink: float = 2.0
    """θₖ hiển thị và dùng để dự đoán = θₖ thô · nₖ / (nₖ + shrink)."""
    initial_sigma: float = 350.0
    sigma_overall_min: float = 40.0
    sigma_skill_min: float = 60.0

    def k_overall(self, attempts: int) -> float:
        return max(self.k_overall_min, self.k_overall_start / math.sqrt(1 + attempts / self.k_decay))

    def k_skill(self, attempts: int) -> float:
        return max(self.k_skill_min, self.k_skill_start / math.sqrt(1 + attempts / self.k_decay))

    def sigma_overall(self, attempts: int) -> float:
        return max(self.sigma_overall_min, self.initial_sigma / math.sqrt(1 + attempts))

    def sigma_skill(self, attempts: int) -> float:
        return max(self.sigma_skill_min, self.initial_sigma / math.sqrt(1 + attempts))


DEFAULT_CONFIG = AbilityConfig()
# Cấu hình ban đầu trước khi tinh chỉnh, giữ lại để chạy lại E1 đúng như báo cáo.
E1_CONFIG = AbilityConfig(
    scale=ELO_SCALE, k_overall_start=64.0, k_overall_min=16.0, k_skill_start=48.0, k_skill_min=8.0, shrink=2.0
)


@dataclass(frozen=True)
class SkillAbility:
    deviation: float = 0.0
    """θₖ thô: độ lệch của kỹ năng so với năng lực chung, chưa co về 0."""
    attempts: int = 0


@dataclass(frozen=True)
class Ability:
    theta: float = DEFAULT_CONFIG.initial_theta
    attempts: int = 0
    skills: Mapping[str, SkillAbility] = field(default_factory=dict)
    config: AbilityConfig = DEFAULT_CONFIG

    def skill(self, skill_id: str) -> SkillAbility:
        return self.skills.get(skill_id, SkillAbility())

    def skill_deviation(self, skill_id: str) -> float:
        """θₖ đã co về 0 theo số lần giải; dùng để dự đoán và hiển thị."""
        s = self.skill(skill_id)
        return s.deviation * s.attempts / (s.attempts + self.config.shrink)

    def skill_ability(self, skill_id: str) -> float:
        """Năng lực ở một kỹ năng, trên thang rating bài tập: θ + θₖ (đã co)."""
        return self.theta + self.skill_deviation(skill_id)

    def skill_sigma(self, skill_id: str) -> float:
        """Độ bất định của năng lực kỹ năng, gộp độ bất định của θ và của θₖ."""
        return math.hypot(self.sigma, self.config.sigma_skill(self.skill(skill_id).attempts))

    @property
    def sigma(self) -> float:
        return self.config.sigma_overall(self.attempts)


@dataclass(frozen=True)
class Observation:
    """Một lần giải đã có nhãn, đủ để cập nhật năng lực."""

    skills: frozenset[str]
    rating: float
    correct: bool


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z))


def predict(ability: Ability, skills: Iterable[str], rating: float) -> float:
    """Xác suất giải đúng một bài tập có các kỹ năng `skills` và rating `rating`."""
    ks = list(skills)
    deviation = sum(ability.skill_deviation(k) for k in ks) / len(ks) if ks else 0.0
    return _sigmoid((ability.theta + deviation - rating) / ability.config.scale)


def rating_for_probability(ability: Ability, p: float) -> float:
    """Nghịch đảo của `predict` khi bỏ qua độ lệch kỹ năng: rating bài tập cho xác suất thô `p`."""
    return ability.theta - ability.config.scale * _logit(p)


def update(ability: Ability, obs: Observation) -> Ability:
    config = ability.config
    surprise = (1.0 if obs.correct else 0.0) - predict(ability, obs.skills, obs.rating)
    skills = dict(ability.skills)
    for k in obs.skills:
        s = ability.skill(k)
        step = config.k_skill(s.attempts) * surprise / len(obs.skills)
        skills[k] = SkillAbility(s.deviation + step, s.attempts + 1)
    return replace(
        ability,
        theta=ability.theta + config.k_overall(ability.attempts) * surprise,
        attempts=ability.attempts + 1,
        skills=skills,
    )


def replay(observations: Iterable[Observation], start: Ability | None = None) -> Ability:
    """Năng lực sau một chuỗi lần giải theo thứ tự thời gian."""
    return replay_with_predictions(observations, start)[0]


def replay_with_predictions(
    observations: Iterable[Observation], start: Ability | None = None
) -> tuple[Ability, list[float]]:
    """Như `replay`, kèm xác suất mô hình đã dự đoán cho từng lần giải trước khi biết kết quả."""
    ability = start or Ability()
    predictions = []
    for obs in observations:
        predictions.append(predict(ability, obs.skills, obs.rating))
        ability = update(ability, obs)
    return ability, predictions


def _logit(p: float) -> float:
    q = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(q / (1 - q))


A_LIMIT = 3.0
B_MIN, B_MAX = 0.25, 4.0


@dataclass(frozen=True)
class ProbabilityCalibration:
    """Hiệu chỉnh xác suất của mô hình: p' = σ(a + b·logit p). Mặc định (0, 1) là không đổi gì.

    Bản Python thuần của `experiments.metrics.Platt` (numpy), vì app không dùng numpy lúc chạy.
    """

    a: float = 0.0
    b: float = 1.0

    def apply(self, p: float) -> float:
        return _sigmoid(self.a + self.b * _logit(p))

    def invert(self, p: float) -> float:
        """Xác suất thô mà sau hiệu chỉnh xác suất cho ra `p`."""
        return _sigmoid((_logit(p) - self.a) / self.b)

    @classmethod
    def fit(
        cls, predictions: list[float], outcomes: list[bool], prior_weight: float = 50.0
    ) -> "ProbabilityCalibration":
        """Hồi quy logistic trên logit p, giải bằng Newton, kéo về (a = 0, b = 1) với trọng số `prior_weight`.

        Phần kéo về giữ hiệu chỉnh ổn định khi ít dữ liệu hoặc khi dữ liệu lệch hẳn về một phía.
        """
        xs = [_logit(p) for p in predictions]
        ys = [1.0 if y else 0.0 for y in outcomes]
        a, b = 0.0, 1.0
        for _ in range(50):
            ga, gb = -prior_weight * a, -prior_weight * (b - 1)
            haa, hab, hbb = prior_weight, 0.0, prior_weight
            for x, y in zip(xs, ys, strict=True):
                q = _sigmoid(a + b * x)
                w = q * (1 - q)
                ga += y - q
                gb += (y - q) * x
                haa += w
                hab += w * x
                hbb += w * x * x
            det = haa * hbb - hab * hab
            step_a = (hbb * ga - hab * gb) / det
            step_b = (haa * gb - hab * ga) / det
            a, b = a + step_a, b + step_b
            if abs(step_a) + abs(step_b) < 1e-9:
                break
        # Giữ hệ số trong khoảng an toàn: b quá nhỏ làm phép nghịch đảo (tìm rating mục tiêu) vọt ra vô cùng.
        return cls(min(max(a, -A_LIMIT), A_LIMIT), min(max(b, B_MIN), B_MAX))
