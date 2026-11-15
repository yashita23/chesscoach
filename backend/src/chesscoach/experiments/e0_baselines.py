"""E0: chia lại bộ Stanford theo thời gian và chạy các baseline dùng rating Chess.com.

    uv run python -m chesscoach.experiments.e0_baselines [--seed 398]

In ra bảng Markdown để chép vào docs/experiments/e0-stanford.md.
"""

import argparse
import sys

import numpy as np

from chesscoach.experiments.stanford import (
    DEFAULT_SEED,
    FloatArray,
    Scores,
    elo,
    fit_logistic,
    load_split,
    make_split,
    score,
)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # console Windows mặc định cp1258
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    counts = make_split(seed=args.seed)
    train, test = load_split("train"), load_split("test")
    print(f"Phép chia (seed {args.seed}): train {counts['train']:,} lần giải, test {counts['test']:,} lần giải")
    print(f"Tỉ lệ đúng: train {train.is_correct.mean():.4f}, test {test.is_correct.mean():.4f}\n")

    rows: list[tuple[str, Scores]] = []

    def add(name: str, p: FloatArray) -> None:
        rows.append((name, score(p, test.is_correct)))

    add("Luôn đoán tỉ lệ đúng của train", np.full(len(test), train.is_correct.mean()))
    add("Elo sách giáo khoa (rating bài tập Chess.com)", elo(test.pre_rating, test.puzzle_rating_original))
    add("Elo sách giáo khoa (puzzle_rating_ours)", elo(test.pre_rating, test.puzzle_rating_ours))
    for column, label in (("puzzle_rating_original", "Chess.com"), ("puzzle_rating_ours", "ours")):
        x_train = (train.pre_rating - getattr(train, column)) / 400
        a, b = fit_logistic(x_train, train.is_correct)
        x_test = (test.pre_rating - getattr(test, column)) / 400
        add(f"Rating Chess.com hiệu chỉnh trên train ({label}; a={a:.3f}, b={b:.3f})", 1 / (1 + np.exp(-(a + b * x_test))))

    print("| Baseline | Accuracy | AUC | Log-loss | p trung bình |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for name, s in rows:
        print(f"| {name} | {s.accuracy:.4f} | {s.auc:.4f} | {s.log_loss:.4f} | {s.mean_p:.3f} |")


if __name__ == "__main__":
    main()
