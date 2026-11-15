"""E1, lớp đánh giá 1: so các mô hình năng lực ở việc dự đoán đúng/sai lần giải tiếp theo trên bộ Stanford.

    uv run python -m chesscoach.experiments.e1_layer1 predict --model elo --seed 0
    uv run python -m chesscoach.experiments.e1_layer1 report
    uv run python -m chesscoach.experiments.e1_layer1 distribution

Bốn mô hình, chạy trên phép chia theo thời gian của E0 (`npm run data`):
- elo:       Elo chung. Module mô hình năng lực của app (`chesscoach.ability`), bài tập không mang kỹ năng nào.
- skill_elo: Elo theo kỹ năng. Cùng module đó, kỹ năng lấy từ chủ đề Chess.com qua bản đồ kỹ năng của app.
- irt:       IRT 1PL. θ người chơi và b bài tập fit trên phần train, co về tiên nghiệm lấy từ rating Chess.com.
- bkt:       Bayesian Knowledge Tracing (pyBKT), một mô hình cho mỗi kỹ năng, fit trên phần train.

elo, skill_elo và bkt dự đoán trực tuyến: dự đoán mỗi lần giải trước khi biết kết quả, rồi cập nhật. irt giữ θ
cố định sau khi fit. Thang rating là của Chess.com (`puzzle_rating_original`), không phải Lichess như ADR 0003,
vì bộ dữ liệu chỉ có thang đó. `puzzle_rating_ours` không dùng vì bị rò rỉ dữ liệu test (xem E0).
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NamedTuple

import duckdb
import numpy as np
import numpy.typing as npt

from chesscoach.ability import Ability, Observation, predict, update
from chesscoach.experiments.metrics import Calibration, FloatArray, Platt, score, sigmoid
from chesscoach.experiments.stanford import RAW_DIR, SPLIT_DIR
from chesscoach.skills import SKILLS, skills_of_chesscom

OUT_DIR = SPLIT_DIR.parent / "e1"
DOCS_DIR = Path(__file__).resolve().parents[4] / "docs" / "experiments"
SEEDS = (0, 1, 2)
ModelName = Literal["elo", "skill_elo", "irt", "bkt"]


@dataclass(frozen=True)
class Attempts:
    """Mọi lần giải (train rồi test) theo thứ tự thời gian trong từng người chơi."""

    user_id: npt.NDArray[np.int64]
    puzzle_id: npt.NDArray[np.int64]
    pre_rating: FloatArray
    puzzle_rating: FloatArray
    is_correct: FloatArray
    is_test: npt.NDArray[np.bool_]
    skills: list[frozenset[str]]

    def __len__(self) -> int:
        return len(self.is_correct)


def load_attempts() -> Attempts:
    split = str(SPLIT_DIR).replace("\\", "/")
    puzzles = str(RAW_DIR / "puzzles.csv").replace("\\", "/")
    rows = duckdb.connect().execute(
        f"""
        SELECT a.user_id, a.tactics_problem_id, a.pre_rating, a.puzzle_rating_original, a.is_correct, a.is_test,
               coalesce(p.themes, '') AS themes
        FROM (SELECT *, false AS is_test FROM read_parquet('{split}/train.parquet')
              UNION ALL SELECT *, true AS is_test FROM read_parquet('{split}/test.parquet')) a
        LEFT JOIN read_csv('{puzzles}', header = true) p USING (tactics_problem_id)
        ORDER BY a.user_id, a.seq
        """
    ).fetchnumpy()
    cache: dict[str, frozenset[str]] = {}
    skills = [cache.setdefault(t, skills_of_chesscom(t.split(";"))) for t in rows["themes"]]
    return Attempts(
        user_id=rows["user_id"].astype(np.int64),
        puzzle_id=rows["tactics_problem_id"].astype(np.int64),
        pre_rating=rows["pre_rating"].astype(np.float64),
        puzzle_rating=rows["puzzle_rating_original"].astype(np.float64),
        is_correct=rows["is_correct"].astype(np.float64),
        is_test=rows["is_test"].astype(bool),
        skills=skills,
    )


def run_elo(data: Attempts, with_skills: bool) -> tuple[FloatArray, dict[int, Ability]]:
    """Dự đoán trực tuyến bằng module năng lực của app; năng lực khởi tạo từ rating Chess.com đầu tiên."""
    p = np.empty(len(data))
    abilities: dict[int, Ability] = {}
    no_skills: frozenset[str] = frozenset()
    for i in range(len(data)):
        user = int(data.user_id[i])
        ability = abilities.get(user) or Ability(theta=float(data.pre_rating[i]))
        skills = data.skills[i] if with_skills else no_skills
        p[i] = predict(ability, skills, data.puzzle_rating[i])
        abilities[user] = update(ability, Observation(skills, data.puzzle_rating[i], bool(data.is_correct[i])))
    return p, abilities


def run_irt(data: Attempts, seed: int) -> FloatArray:
    """IRT 1PL: p = σ(θ người chơi − b bài tập + c), fit bằng Adam trên phần train.

    θ và b co về tiên nghiệm lấy từ rating Chess.com. Độ dốc và hệ số chặn của tiên nghiệm được fit trên phần
    train (như baseline hiệu chỉnh của E0), vì độ dốc 400/ln 10 của Elo sách giáo khoa quá dốc với bộ dữ liệu
    này. Trọng số co 1,25 tương đương khoảng 5 lần giải (mỗi lần giải đóng góp p(1−p) ≈ 0,25); chọn trước,
    không tinh chỉnh trên phần test.
    """
    iterations, prior_weight = 400, 1.25
    rng = np.random.default_rng(seed)
    users, user_of_row = np.unique(data.user_id, return_inverse=True)
    items, item_of_row = np.unique(data.puzzle_id, return_inverse=True)
    train = ~data.is_test
    prior = Calibration.fit(data.pre_rating[train] - data.puzzle_rating[train], data.is_correct[train])
    first_rating = np.zeros(len(users))
    first_rows = np.flatnonzero(np.r_[True, np.diff(user_of_row) != 0])  # dữ liệu đã sắp theo người chơi, thời gian
    first_rating[user_of_row[first_rows]] = data.pre_rating[first_rows]
    item_rating = np.zeros(len(items))
    item_rating[item_of_row] = data.puzzle_rating
    theta0 = prior.b * (first_rating - 1500) / 400
    b0 = prior.b * (item_rating - 1500) / 400
    theta = theta0 + rng.normal(0, 0.01, len(users))
    b = b0 + rng.normal(0, 0.01, len(items))
    params = [theta, b, np.array([prior.a])]
    first_moment = [np.zeros_like(x) for x in params]
    second_moment = [np.zeros_like(x) for x in params]
    users_train, items_train, y = user_of_row[train], item_of_row[train], data.is_correct[train]
    lr, beta1, beta2 = 0.05, 0.9, 0.999
    for step in range(1, iterations + 1):
        residual = sigmoid(theta[users_train] - b[items_train] + params[2][0]) - y  # đạo hàm log-loss theo logit
        grads = [
            np.bincount(users_train, residual, len(users)) + prior_weight * (theta - theta0),
            -np.bincount(items_train, residual, len(items)) + prior_weight * (b - b0),
            np.array([residual.sum()]),
        ]
        for j, g in enumerate(grads):
            first_moment[j] = beta1 * first_moment[j] + (1 - beta1) * g
            second_moment[j] = beta2 * second_moment[j] + (1 - beta2) * g * g
            corrected = first_moment[j] / (1 - beta1**step)
            params[j] -= lr * corrected / (np.sqrt(second_moment[j] / (1 - beta2**step)) + 1e-8)
    result: FloatArray = sigmoid(theta[user_of_row] - b[item_of_row] + params[2][0])
    return result


def run_elo_overall(data: Attempts, seed: int) -> FloatArray:
    return run_elo(data, with_skills=False)[0]


def run_skill_elo(data: Attempts, seed: int) -> FloatArray:
    return run_elo(data, with_skills=True)[0]


def run_bkt(data: Attempts, seed: int) -> FloatArray:
    """pyBKT, một mô hình cho mỗi kỹ năng. Lần giải nhiều kỹ năng được nhân bản theo kỹ năng rồi lấy trung bình."""
    import pandas as pd
    from pyBKT.models import Model

    rows = [(i, int(data.user_id[i]), s, int(data.is_correct[i])) for i in range(len(data)) for s in sorted(data.skills[i])]
    frame = pd.DataFrame(rows, columns=["row", "user_id", "skill_name", "correct"])
    frame["order_id"] = np.arange(len(frame))
    frame["user_id"] = frame["user_id"].astype(str)
    is_train = ~data.is_test[frame["row"].to_numpy()]
    model = Model(seed=seed, num_fits=1, parallel=False)
    model.fit(data=frame[is_train])
    predicted = model.predict(data=frame)
    per_row = predicted.groupby(frame["row"])["correct_predictions"].mean()
    p = np.full(len(data), 0.5)
    p[per_row.index.to_numpy()] = per_row.to_numpy()
    return p


@dataclass(frozen=True)
class ModelSpec:
    label: str
    run: Callable[[Attempts, int], FloatArray]
    color: str
    marker: str


# Màu theo thứ tự ô 1–4 của bảng màu đã kiểm tra (dataviz); mỗi mô hình giữ đúng màu của nó.
MODELS: dict[ModelName, ModelSpec] = {
    "elo": ModelSpec("Elo chung", run_elo_overall, "#2a78d6", "o"),
    "skill_elo": ModelSpec("Elo theo kỹ năng", run_skill_elo, "#eb6834", "s"),
    "irt": ModelSpec("IRT", run_irt, "#1baf7a", "^"),
    "bkt": ModelSpec("BKT (pyBKT)", run_bkt, "#eda100", "D"),
}


class CalibrationBin(NamedTuple):
    mean_p: float
    observed: float
    attempts: int


def predictions_path(model: ModelName, seed: int) -> Path:
    return OUT_DIR / f"pred_{model}_seed{seed}.npy"


def cmd_predict(model: ModelName, seed: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    p = MODELS[model].run(load_attempts(), seed)
    np.save(predictions_path(model, seed), p)
    print(f"{model} seed {seed}: {time.time() - started:.0f}s → {predictions_path(model, seed)}")


def cmd_distribution(min_attempts: int = 10) -> None:
    """Phân bố năng lực sau lần giải cuối của từng người chơi (Elo theo kỹ năng), cho người học mô phỏng ở lớp 3."""
    _, abilities = run_elo(load_attempts(), with_skills=True)
    thetas = np.array([a.theta for a in abilities.values()])
    skills = {}
    for s in SKILLS:
        deviations = np.array(
            [a.skill(s.id).effective_deviation for a in abilities.values() if a.skill(s.id).attempts >= min_attempts]
        )
        skills[s.id] = {
            "players": int(len(deviations)),
            "mean": round(float(deviations.mean()), 1) if len(deviations) else None,
            "std": round(float(deviations.std()), 1) if len(deviations) else None,
        }
    out = {
        "source": "Elo theo kỹ năng trên toàn bộ bộ Stanford (thang rating Chess.com), sau lần giải cuối",
        "caveat": "Ước lượng điểm đã co về 0, không phải phân bố ẩn thật: std gồm cả nhiễu ước lượng và bị co nhỏ lại",
        "min_attempts_per_skill": min_attempts,
        "theta": {"players": int(len(thetas)), "mean": round(float(thetas.mean()), 1), "std": round(float(thetas.std()), 1)},
        "skill_deviation": skills,
    }
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    target = DOCS_DIR / "e1-skill-distribution.json"
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Đã ghi {target}")


def calibration_bins(p: FloatArray, y: FloatArray, min_attempts: int = 500) -> list[CalibrationBin]:
    """Các khoảng p rộng 0,1 có ít nhất `min_attempts` lần giải."""
    bin_of_row = np.minimum((p * 10).astype(int), 9)
    bins = []
    for k in range(10):
        in_bin = bin_of_row == k
        if in_bin.sum() >= min_attempts:
            bins.append(CalibrationBin(float(p[in_bin].mean()), float(y[in_bin].mean()), int(in_bin.sum())))
    return bins


def format_bins(bins: list[CalibrationBin]) -> str:
    return "; ".join(f"{b.mean_p:.2f} → {b.observed:.2f} ({b.attempts:,})" for b in bins)


def mean_std(values: list[float]) -> str:
    return f"{np.mean(values):.4f} ± {np.std(values):.4f}"


def cmd_report() -> None:
    data = load_attempts()
    test, y_test, y_train = data.is_test, data.is_correct[data.is_test], data.is_correct[~data.is_test]
    raw_curves: dict[ModelName, list[CalibrationBin]] = {}
    platt_curves: dict[ModelName, list[CalibrationBin]] = {}
    print("| Mô hình | Accuracy | AUC | Log-loss | p trung bình |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for name, spec in MODELS.items():
        runs = [np.load(predictions_path(name, s)) for s in SEEDS if predictions_path(name, s).exists()]
        if not runs:
            continue
        # Hiệu chỉnh Platt fit trên dự đoán phần train của chính lần chạy đó.
        calibrated = [Platt.fit(r[~test], y_train).predict(r[test]) for r in runs]
        for label, preds in ((f"{spec.label} (thô)", [r[test] for r in runs]), (f"{spec.label} (Platt)", calibrated)):
            scores = [score(p, y_test) for p in preds]
            print(
                f"| {label} | {mean_std([s.accuracy for s in scores])} | {mean_std([s.auc for s in scores])} | "
                f"{mean_std([s.log_loss for s in scores])} | {np.mean([s.mean_p for s in scores]):.3f} |"
            )
        print(f"<!-- {name}: {len(runs)} seed -->")
        raw_curves[name] = calibration_bins(runs[0][test], y_test)
        platt_curves[name] = calibration_bins(calibrated[0], y_test)

    print("\nĐộ hiệu chỉnh (seed 0): p dự đoán → tỉ lệ đúng thật (số lần giải)\n")
    for name in raw_curves:
        print(f"- {MODELS[name].label} (thô): {format_bins(raw_curves[name])}")
        print(f"- {MODELS[name].label} (Platt): {format_bins(platt_curves[name])}")
    plot_calibration(raw_curves)


def plot_calibration(curves: dict[ModelName, list[CalibrationBin]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.2, 5.6), dpi=150)
    ax.plot([0, 1], [0, 1], color="#9aa0a6", linestyle=(0, (4, 4)), linewidth=1.5, label="Hiệu chỉnh hoàn hảo")
    for name, curve in curves.items():
        spec = MODELS[name]
        ax.plot([b.mean_p for b in curve], [b.observed for b in curve], color=spec.color, marker=spec.marker,
                markersize=6, linewidth=2, label=spec.label)
    # Nhãn trực tiếp ở mép phải, giãn cách để không đè nhau.
    ends = sorted(((curve[-1].observed, name) for name, curve in curves.items() if curve), reverse=True)
    placed: list[float] = []
    for y_end, name in ends:
        y_label = min([y_end] + [p - 0.05 for p in placed[-1:]])
        placed.append(y_label)
        ax.annotate(MODELS[name].label, xy=(curves[name][-1].mean_p, y_end), xytext=(1.02, y_label),
                    textcoords=("axes fraction", "data"), fontsize=8, color="#3c4043", va="center",
                    annotation_clip=False, arrowprops={"arrowstyle": "-", "color": MODELS[name].color, "linewidth": 0.8})
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Xác suất giải đúng dự đoán (thô, chưa hiệu chỉnh)")
    ax.set_ylabel("Tỉ lệ giải đúng thật")
    ax.set_title("Độ hiệu chỉnh trên phần test (seed 0)", loc="left", fontsize=11)
    ax.grid(color="#e8eaed", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(DOCS_DIR / "e1-calibration.png")
    print(f"\nĐã ghi {DOCS_DIR / 'e1-calibration.png'}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # console Windows mặc định cp1258
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    predict_cmd = sub.add_parser("predict", help="chạy một mô hình, ghi dự đoán ra data/stanford/e1/")
    predict_cmd.add_argument("--model", choices=list(MODELS), required=True)
    predict_cmd.add_argument("--seed", type=int, choices=SEEDS, required=True)
    sub.add_parser("report", help="bảng kết quả, bảng và biểu đồ độ hiệu chỉnh")
    sub.add_parser("distribution", help="phân bố năng lực theo kỹ năng cho lớp 3")
    args = parser.parse_args()
    if args.command == "predict":
        cmd_predict(args.model, args.seed)
    elif args.command == "report":
        cmd_report()
    else:
        cmd_distribution()


if __name__ == "__main__":
    main()
