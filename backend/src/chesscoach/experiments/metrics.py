"""Công cụ đo dự đoán đúng/sai dùng chung cho các thí nghiệm đánh giá."""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


def sigmoid(z: FloatArray) -> FloatArray:
    result: FloatArray = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
    return result


@dataclass(frozen=True)
class Scores:
    accuracy: float
    auc: float
    log_loss: float
    mean_p: float


def score(p: FloatArray, y: FloatArray) -> Scores:
    """Accuracy (dự đoán đúng khi p ≥ 0,5), AUC và log-loss."""
    p = np.clip(p, 1e-6, 1 - 1e-6)
    accuracy = float(np.mean((p >= 0.5) == (y == 1)))
    log_loss = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    return Scores(accuracy, auc(p, y), log_loss, float(np.mean(p)))


def auc(p: FloatArray, y: FloatArray) -> float:
    """AUC theo hạng (Mann–Whitney), điểm bằng nhau lấy hạng trung bình."""
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p), dtype=np.float64)
    sorted_p = p[order]
    i = 0
    while i < len(p):
        j = i
        while j + 1 < len(p) and sorted_p[j + 1] == sorted_p[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    pos = y == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def elo_expected_score(player_rating: FloatArray, puzzle_rating: FloatArray) -> FloatArray:
    """Xác suất giải đúng theo công thức Elo sách giáo khoa: 1 / (1 + 10^((rating bài tập − rating người chơi) / 400))."""
    result: FloatArray = 1.0 / (1.0 + 10.0 ** ((puzzle_rating - player_rating) / 400.0))
    return result


@dataclass(frozen=True)
class Calibration:
    """Hiệu chỉnh p = σ(a + b·Δ/400) trên hiệu rating Δ = rating người chơi − rating bài tập.

    Công thức Elo sách giáo khoa ứng với a = 0, b = ln 10 ≈ 2,30.
    """

    a: float
    b: float

    @classmethod
    def fit(cls, rating_diff: FloatArray, y: FloatArray, iterations: int = 25) -> "Calibration":
        """Hồi quy logistic một biến, giải bằng Newton."""
        x = rating_diff / 400
        a, b = 0.0, 0.0
        for _ in range(iterations):
            p = sigmoid(a + b * x)
            w = p * (1 - p)
            g = np.array([np.sum(y - p), np.sum((y - p) * x)])
            h = np.array([[np.sum(w), np.sum(w * x)], [np.sum(w * x), np.sum(w * x * x)]])
            step = np.linalg.solve(h, g)
            a, b = a + float(step[0]), b + float(step[1])
            if math.hypot(*step) < 1e-10:
                break
        return cls(a, b)

    def predict(self, rating_diff: FloatArray) -> FloatArray:
        return sigmoid(self.a + self.b * rating_diff / 400)
