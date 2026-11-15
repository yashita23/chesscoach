"""E0: chia lại bộ Stanford theo thời gian và chạy các baseline dùng rating Chess.com.

    uv run python -m chesscoach.experiments.e0_baselines [--seed 398]

In ra bảng Markdown, dùng nguyên văn trong docs/experiments/e0-stanford.md.
"""

import argparse
import sys
from collections.abc import Callable

import numpy as np

from chesscoach.experiments.metrics import Calibration, FloatArray, elo_expected_score, score
from chesscoach.experiments.stanford import DEFAULT_SEED, SplitPart, hidden_test_puzzles, load_split, make_split

Baseline = Callable[[SplitPart], FloatArray]


def baselines(train: SplitPart) -> dict[str, Baseline]:
    """Các baseline; bản hiệu chỉnh chỉ fit trên train."""
    calibrated_original = Calibration.fit(train.pre_rating - train.puzzle_rating_original, train.is_correct)
    calibrated_ours = Calibration.fit(train.pre_rating - train.puzzle_rating_ours, train.is_correct)
    base_rate = float(train.is_correct.mean())
    return {
        "Luôn đoán tỉ lệ đúng của train": lambda s: np.full(len(s), base_rate),
        "Elo sách giáo khoa: pre_rating vs puzzle_rating_original": lambda s: elo_expected_score(
            s.pre_rating, s.puzzle_rating_original
        ),
        (
            "Rating Chess.com hiệu chỉnh: pre_rating vs puzzle_rating_original "
            f"(a = {calibrated_original.a:.3f}, b = {calibrated_original.b:.3f})"
        ): lambda s: calibrated_original.predict(s.pre_rating - s.puzzle_rating_original),
        "*Elo sách giáo khoa: pre_rating vs puzzle_rating_ours*": lambda s: elo_expected_score(
            s.pre_rating, s.puzzle_rating_ours
        ),
        (
            "*Hiệu chỉnh: pre_rating vs puzzle_rating_ours "
            f"(a = {calibrated_ours.a:.3f}, b = {calibrated_ours.b:.3f})*"
        ): lambda s: calibrated_ours.predict(s.pre_rating - s.puzzle_rating_ours),
    }


def print_table(title: str, part: SplitPart, models: dict[str, Baseline]) -> None:
    print(f"\n{title}: {len(part):,} lần giải, tỉ lệ đúng {part.is_correct.mean():.4f}\n")
    print("| Baseline | Accuracy | AUC | Log-loss | p trung bình |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for name, predict in models.items():
        s = score(predict(part), part.is_correct)
        print(f"| {name} | {s.accuracy:.4f} | {s.auc:.4f} | {s.log_loss:.4f} | {s.mean_p:.3f} |")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # console Windows mặc định cp1258
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    counts = make_split(seed=args.seed)
    print(f"Phép chia (seed {args.seed}): train {counts['train']:,}, test {counts['test']:,} lần giải")
    train, test = load_split("train"), load_split("test")
    models = baselines(train)
    print_table("Toàn bộ phần test", test, models)
    on_hidden = test.where(np.isin(test.tactics_problem_id, hidden_test_puzzles()))
    print_table("Phần test, chỉ các bài tập có trong test.csv gốc", on_hidden, models)


if __name__ == "__main__":
    main()
