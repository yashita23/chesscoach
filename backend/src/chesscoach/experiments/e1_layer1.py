"""E1, lớp đánh giá 1: so các mô hình năng lực ở việc dự đoán đúng/sai lần giải tiếp theo trên bộ Stanford.

    uv run python -m chesscoach.experiments.e1_layer1 predict --model elo --seed 0
    uv run python -m chesscoach.experiments.e1_layer1 report

Bốn mô hình, chạy trên phép chia theo thời gian của E0 (`npm run data`):
- elo:       Elo chung. Module mô hình năng lực của app (`chesscoach.ability`), bài tập không mang kỹ năng nào.
- skill_elo: Elo theo kỹ năng. Cùng module đó, kỹ năng lấy từ chủ đề Chess.com qua bản đồ kỹ năng của app.
- irt:       IRT 1PL. θ người chơi và b bài tập fit trên phần train, co về mức lấy từ rating Chess.com.
- bkt:       Bayesian Knowledge Tracing (pyBKT), một mô hình cho mỗi kỹ năng, fit trên phần train.

elo, skill_elo và bkt dự đoán trực tuyến: dự đoán mỗi lần giải trước khi biết kết quả, rồi cập nhật. irt giữ θ
cố định sau khi fit. Thang rating là của Chess.com (`puzzle_rating_original`), không phải Lichess như ADR 0003,
vì bộ dữ liệu chỉ có thang đó. `puzzle_rating_ours` không dùng vì bị rò rỉ dữ liệu test (xem E0).
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import duckdb
import numpy as np
import numpy.typing as npt

from chesscoach.ability import SCALE, Ability, Observation, predict, update
from chesscoach.experiments.metrics import Calibration, FloatArray, logit, score, sigmoid
from chesscoach.experiments.stanford import RAW_DIR, SPLIT_DIR
from chesscoach.skills import SKILLS, skills_of_chesscom

OUT_DIR = SPLIT_DIR.parent / "e1"
DOCS_DIR = Path(__file__).resolve().parents[4] / "docs" / "experiments"
SEEDS = (0, 1, 2)
ModelName = Literal["elo", "skill_elo", "irt", "bkt"]
MODELS: tuple[ModelName, ...] = ("elo", "skill_elo", "irt", "bkt")
LABELS: dict[ModelName, str] = {
    "elo": "Elo chung",
    "skill_elo": "Elo theo kỹ năng",
    "irt": "IRT",
    "bkt": "BKT (pyBKT)",
}
# Hai mô hình Elo dùng thang rating Chess.com gốc nên lệch xác suất trên dữ liệu đã cân bằng 50%.
NEEDS_CALIBRATION: frozenset[ModelName] = frozenset({"elo", "skill_elo"})


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


def run_irt(data: Attempts, seed: int, iterations: int = 400, prior_weight: float = 1.25) -> FloatArray:
    """IRT 1PL: p = σ(θ_người chơi − b_bài tập), fit bằng Adam trên phần train.

    θ và b co về mức lấy từ rating Chess.com (trọng số `prior_weight`, tương đương vài lần giải), nên bài tập
    chưa xuất hiện trong train vẫn có độ khó hợp lý.
    """
    rng = np.random.default_rng(seed)
    users, u_idx = np.unique(data.user_id, return_inverse=True)
    items, i_idx = np.unique(data.puzzle_id, return_inverse=True)
    train = ~data.is_test
    first_rating = np.zeros(len(users))
    first_rows = np.flatnonzero(np.r_[True, np.diff(u_idx) != 0])  # dữ liệu đã sắp theo người chơi, thời gian
    first_rating[u_idx[first_rows]] = data.pre_rating[first_rows]
    item_rating = np.zeros(len(items))
    item_rating[i_idx] = data.puzzle_rating
    theta0, b0 = (first_rating - 1500) / SCALE, (item_rating - 1500) / SCALE
    theta = theta0 + rng.normal(0, 0.01, len(users))
    b = b0 + rng.normal(0, 0.01, len(items))
    bias = 0.0
    ut, it, y = u_idx[train], i_idx[train], data.is_correct[train]
    params = [theta, b, np.zeros(1)]
    m = [np.zeros_like(x) for x in params]
    v = [np.zeros_like(x) for x in params]
    lr, beta1, beta2 = 0.05, 0.9, 0.999
    for step in range(1, iterations + 1):
        residual = sigmoid(theta[ut] - b[it] + bias) - y  # đạo hàm log-loss theo logit
        grads = [
            np.bincount(ut, residual, len(users)) + prior_weight * (theta - theta0),
            -np.bincount(it, residual, len(items)) + prior_weight * (b - b0),
            np.array([residual.sum()]),
        ]
        for j, g in enumerate(grads):
            m[j] = beta1 * m[j] + (1 - beta1) * g
            v[j] = beta2 * v[j] + (1 - beta2) * g * g
            params[j] -= lr * (m[j] / (1 - beta1**step)) / (np.sqrt(v[j] / (1 - beta2**step)) + 1e-8)
        bias = float(params[2][0])
    result: FloatArray = sigmoid(theta[u_idx] - b[i_idx] + bias)
    return result


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


def predictions_path(model: ModelName, seed: int) -> Path:
    return OUT_DIR / f"pred_{model}_seed{seed}.npy"


def cmd_predict(model: ModelName, seed: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = load_attempts()
    started = time.time()
    if model in ("elo", "skill_elo"):
        p, abilities = run_elo(data, with_skills=model == "skill_elo")
        if model == "skill_elo":
            write_skill_distribution(abilities)
    elif model == "irt":
        p = run_irt(data, seed)
    else:
        p = run_bkt(data, seed)
    np.save(predictions_path(model, seed), p)
    print(f"{model} seed {seed}: {time.time() - started:.0f}s → {predictions_path(model, seed)}")


def write_skill_distribution(abilities: dict[int, Ability], min_attempts: int = 10) -> None:
    """Phân bố năng lực và độ lệch θₖ giữa các người chơi, cho người học mô phỏng ở lớp 3."""
    thetas = np.array([a.theta for a in abilities.values()])
    skills = {}
    for s in SKILLS:
        devs = np.array(
            [a.skill(s.id).effective_deviation for a in abilities.values() if a.skill(s.id).attempts >= min_attempts]
        )
        skills[s.id] = {
            "players": int(len(devs)),
            "mean": round(float(devs.mean()), 1) if len(devs) else None,
            "std": round(float(devs.std()), 1) if len(devs) else None,
        }
    out = {
        "source": "Elo theo kỹ năng trên toàn bộ bộ Stanford (thang rating Chess.com), sau lần giải cuối",
        "min_attempts_per_skill": min_attempts,
        "theta": {"players": int(len(thetas)), "mean": round(float(thetas.mean()), 1), "std": round(float(thetas.std()), 1)},
        "skill_deviation": skills,
    }
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "e1-skill-distribution.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")


def calibration_bins(p: FloatArray, y: FloatArray, bins: int = 10, min_count: int = 500) -> list[tuple[float, float, int]]:
    """(p trung bình, tỉ lệ đúng thật, số lần giải) cho mỗi khoảng p rộng 0,1 có ít nhất `min_count` lần giải."""
    edges = np.minimum((p * bins).astype(int), bins - 1)
    out = []
    for k in range(bins):
        mask = edges == k
        if mask.sum() >= min_count:
            out.append((float(p[mask].mean()), float(y[mask].mean()), int(mask.sum())))
    return out


def cmd_report() -> None:
    data = load_attempts()
    test, y_test, y_train = data.is_test, data.is_correct[data.is_test], data.is_correct[~data.is_test]
    final: dict[ModelName, list[FloatArray]] = defaultdict(list)
    print("| Mô hình | Accuracy | AUC | Log-loss | p trung bình |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for model in MODELS:
        runs = [np.load(predictions_path(model, s)) for s in SEEDS if predictions_path(model, s).exists()]
        if not runs:
            continue
        variants: list[tuple[str, list[FloatArray]]] = [(LABELS[model], [r[test] for r in runs])]
        if model in NEEDS_CALIBRATION:
            calibrated = []
            for r in runs:
                # Hiệu chỉnh Platt: σ(a + b·logit p), fit trên các dự đoán của phần train.
                cal = Calibration.fit(400 * logit(r[~test]), y_train)
                calibrated.append(cal.predict(400 * logit(r[test])))
            variants = [(f"{LABELS[model]} (thô)", [r[test] for r in runs]), (f"{LABELS[model]} (hiệu chỉnh)", calibrated)]
        final[model] = variants[-1][1]
        for name, preds in variants:
            scores = [score(p, y_test) for p in preds]

            def cell(values: list[float]) -> str:
                return f"{np.mean(values):.4f} ± {np.std(values):.4f}"

            print(
                f"| {name} | {cell([s.accuracy for s in scores])} | {cell([s.auc for s in scores])} | "
                f"{cell([s.log_loss for s in scores])} | {np.mean([s.mean_p for s in scores]):.3f} |"
            )
        print(f"<!-- {model}: {len(runs)} seed -->")

    print("\nĐộ hiệu chỉnh (seed 0): p trung bình → tỉ lệ đúng thật (số lần giải)\n")
    curves = {m: calibration_bins(preds[0], y_test) for m, preds in final.items()}
    for m, curve in curves.items():
        print(f"- {LABELS[m]}: " + "; ".join(f"{p:.2f} → {o:.2f} ({n:,})" for p, o, n in curve))
    plot_calibration(curves)


def plot_calibration(curves: dict[ModelName, list[tuple[float, float, int]]]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"elo": "#2a78d6", "skill_elo": "#eb6834", "irt": "#1baf7a", "bkt": "#eda100"}
    markers = {"elo": "o", "skill_elo": "s", "irt": "^", "bkt": "D"}
    fig, ax = plt.subplots(figsize=(7.2, 5.6), dpi=150)
    ax.plot([0, 1], [0, 1], color="#9aa0a6", linestyle=(0, (4, 4)), linewidth=1.5, label="Hiệu chỉnh hoàn hảo")
    for m, curve in curves.items():
        xs, ys = [c[0] for c in curve], [c[1] for c in curve]
        ax.plot(xs, ys, color=colors[m], marker=markers[m], markersize=6, linewidth=2, label=LABELS[m])
    # Nhãn trực tiếp ở mép phải, giãn cách để không đè nhau.
    ends = sorted(((curve[-1][1], m) for m, curve in curves.items() if curve), reverse=True)
    placed: list[float] = []
    for y_end, m in ends:
        y_label = min([y_end] + [p - 0.05 for p in placed[-1:]])
        placed.append(y_label)
        ax.annotate(LABELS[m], xy=(curves[m][-1][0], y_end), xytext=(1.02, y_label), textcoords=("axes fraction", "data"),
                    fontsize=8, color="#3c4043", va="center", annotation_clip=False,
                    arrowprops={"arrowstyle": "-", "color": colors[m], "linewidth": 0.8})
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Xác suất giải đúng dự đoán")
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
    p = sub.add_parser("predict")
    p.add_argument("--model", choices=MODELS, required=True)
    p.add_argument("--seed", type=int, choices=SEEDS, required=True)
    sub.add_parser("report")
    args = parser.parse_args()
    if args.command == "predict":
        cmd_predict(args.model, args.seed)
    else:
        cmd_report()


if __name__ == "__main__":
    main()

