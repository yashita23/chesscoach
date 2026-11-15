"""E1b: tinh chỉnh và hiệu chỉnh mô hình năng lực (Elo theo kỹ năng) trên bộ Stanford.

    uv run python -m chesscoach.experiments.e1b_tuning [--workers 14]

Quy tắc: mọi lựa chọn chỉ dựa trên phần validation (20% lần giải cuối của phần train mỗi người chơi); phần test
chỉ được đo một lần, ở cuối, cho cấu hình đã chọn.

Ba giai đoạn:
1. Tinh chỉnh AbilityConfig (thang s, K, độ co) của module năng lực trong app. Tiêu chí: log-loss trên validation
   sau hiệu chỉnh Platt (fit trên phần train còn lại), vì app sẽ có bước hiệu chỉnh riêng (#22).
2. Thêm độ lệch rating δ cho từng bài tập, cập nhật trực tuyến như θ (Elo hai chiều): bài tập bị giải đúng nhiều
   hơn dự đoán thì dễ đi. Mọi lần giải chạy theo thứ tự thời gian chung, nên δ chỉ học từ lần giải trước đó.
3. Đo trên phần test: E1 (mặc định) so với cấu hình đã chỉnh, có và không có δ, thô và sau Platt.
"""

import argparse
import itertools
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from typing import Any

import duckdb
import numpy as np
import numpy.typing as npt

from chesscoach.ability import E1_CONFIG, Ability, AbilityConfig, Observation, predict, update
from chesscoach.experiments.e1_layer1 import DOCS_DIR, Attempts, CalibrationBin, calibration_bins, load_attempts
from chesscoach.experiments.metrics import FloatArray, Platt, Scores, score
from chesscoach.experiments.stanford import SPLIT_DIR

VALIDATION_FRACTION = 0.2
# Kết quả đánh giá một cấu hình, dạng ghi được ra JSON.
Result = dict[str, Any]
# Nhân thang s của Elo (400/ln 10). ×1 là thang chuẩn của công thức Elo.
SCALE_MULTIPLIERS = (1.0, 2.0, 3.0, 4.0, 5.0)


@dataclass(frozen=True)
class ItemConfig:
    """Độ lệch rating theo bài tập: δ += −K(n)·(y − p), dùng δ·n/(n + shrink) khi dự đoán."""

    k_start: float
    k_min: float
    shrink: float

    def k(self, attempts: int) -> float:
        return max(self.k_min, self.k_start / math.sqrt(1 + attempts / 4))


@dataclass(frozen=True)
class Data:
    attempts: Attempts
    order: npt.NDArray[np.int64]
    """Thứ tự thời gian chung (mọi người chơi) để duyệt các lần giải."""
    fit_rows: npt.NDArray[np.bool_]
    """Phần train trừ validation: nơi fit Platt khi tinh chỉnh."""
    val_rows: npt.NDArray[np.bool_]


def load_data() -> Data:
    attempts = load_attempts()
    split = str(SPLIT_DIR).replace("\\", "/")
    times = duckdb.connect().execute(
        f"""SELECT epoch(create_date) AS t FROM (
              SELECT user_id, seq, create_date FROM read_parquet('{split}/train.parquet')
              UNION ALL SELECT user_id, seq, create_date FROM read_parquet('{split}/test.parquet'))
            ORDER BY user_id, seq"""
    ).fetchnumpy()["t"].astype(np.float64)
    # Trùng thời điểm: giữ thứ tự trong từng người chơi (dữ liệu đã sắp theo người chơi, seq).
    order = np.lexsort((np.arange(len(times)), times)).astype(np.int64)

    train = ~attempts.is_test
    val = np.zeros(len(attempts), dtype=bool)
    starts = np.flatnonzero(np.r_[True, np.diff(attempts.user_id) != 0])
    ends = np.r_[starts[1:], len(attempts)]
    for start, end in zip(starts, ends, strict=True):
        n_train = int(train[start:end].sum())  # phần train của mỗi người chơi đứng trước phần test
        n_val = int(np.ceil(n_train * VALIDATION_FRACTION))
        val[start + n_train - n_val : start + n_train] = True
    return Data(attempts, order, fit_rows=train & ~val, val_rows=val)


def run(data: Data, config: AbilityConfig, item: ItemConfig | None, learn_from_test: bool = True) -> FloatArray:
    """Dự đoán trực tuyến mọi lần giải theo thứ tự thời gian chung.

    `learn_from_test=False`: δ của bài tập không học từ lần giải thuộc phần test. Bắt buộc khi tinh chỉnh, vì lần
    giải test của người chơi khác có thể xảy ra trước lần giải validation, khiến nhãn test lọt vào việc chọn cấu hình.
    """
    a = data.attempts
    p = np.empty(len(a))
    abilities: dict[int, Ability] = {}
    delta: dict[int, float] = {}
    seen: dict[int, int] = {}
    for i in data.order:
        user, puzzle = int(a.user_id[i]), int(a.puzzle_id[i])
        ability = abilities.get(user) or Ability(theta=float(a.pre_rating[i]), config=config)
        rating = float(a.puzzle_rating[i])
        if item is not None:
            n = seen.get(puzzle, 0)
            rating += delta.get(puzzle, 0.0) * n / (n + item.shrink)
        p[i] = predict(ability, a.skills[i], rating)
        y = bool(a.is_correct[i])
        abilities[user] = update(ability, Observation(a.skills[i], rating, y))
        if item is not None and (learn_from_test or not a.is_test[i]):
            n = seen.get(puzzle, 0)
            delta[puzzle] = delta.get(puzzle, 0.0) - item.k(n) * ((1.0 if y else 0.0) - p[i])
            seen[puzzle] = n + 1
    return p


_DATA: Data | None = None


def _init_worker() -> None:
    global _DATA
    _DATA = load_data()


def _evaluate(job: tuple[AbilityConfig, ItemConfig | None]) -> Result:
    assert _DATA is not None
    config, item = job
    p = run(_DATA, config, item, learn_from_test=False)
    y = _DATA.attempts.is_correct
    platt = Platt.fit(p[_DATA.fit_rows], y[_DATA.fit_rows])
    raw = score(p[_DATA.val_rows], y[_DATA.val_rows])
    calibrated = score(platt.predict(p[_DATA.val_rows]), y[_DATA.val_rows])
    return {
        "config": asdict(config),
        "item": asdict(item) if item else None,
        "val_raw_log_loss": raw.log_loss,
        "val_log_loss": calibrated.log_loss,
        "val_auc": raw.auc,
        "platt": [platt.a, platt.b],
    }


def search(jobs: list[tuple[AbilityConfig, ItemConfig | None]], workers: int) -> list[Result]:
    started = time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as pool:
        results = list(pool.map(_evaluate, jobs))
    print(f"  {len(jobs)} cấu hình, {time.time() - started:.0f}s")
    return sorted(results, key=lambda r: float(r["val_log_loss"]))


def player_grid() -> list[tuple[AbilityConfig, ItemConfig | None]]:
    jobs: list[tuple[AbilityConfig, ItemConfig | None]] = []
    for scale_mult, k0, kmin, ks0, shrink in itertools.product(
        SCALE_MULTIPLIERS, (32.0, 64.0, 128.0, 256.0), (8.0, 16.0), (24.0, 48.0, 96.0, 192.0), (2.0, 5.0)
    ):
        config = replace(
            E1_CONFIG,
            scale=E1_CONFIG.scale * scale_mult,
            k_overall_start=k0,
            k_overall_min=kmin,
            k_skill_start=ks0,
            k_skill_min=kmin / 2,
            shrink=shrink,
        )
        jobs.append((config, None))
    return jobs


def item_grid(config: AbilityConfig) -> list[tuple[AbilityConfig, ItemConfig | None]]:
    return [
        (config, ItemConfig(k0, k0 / 8, shrink))
        for k0, shrink in itertools.product((32.0, 64.0, 128.0, 256.0, 512.0), (1.0, 2.0, 5.0))
    ]


def test_scores(data: Data, p: FloatArray) -> tuple[Scores, Scores, list[CalibrationBin], list[CalibrationBin]]:
    """Điểm trên phần test, thô và sau Platt fit trên toàn bộ phần train (gồm validation)."""
    a = data.attempts
    train, test = ~a.is_test, a.is_test
    calibrated = Platt.fit(p[train], a.is_correct[train]).predict(p[test])
    y = a.is_correct[test]
    return (
        score(p[test], y),
        score(calibrated, y),
        calibration_bins(p[test], y),
        calibration_bins(calibrated, y),
    )


def near_target(bins: list[CalibrationBin]) -> str:
    """Khoảng p gần 0,7, nơi buổi luyện nhắm tới."""
    best = min(bins, key=lambda b: abs(b.mean_p - 0.7))
    return f"{best.mean_p:.2f} → {best.observed:.2f}"


def plot(results_path: str) -> None:
    """Biểu đồ độ hiệu chỉnh (xác suất thô) trên phần test cho E1 và hai cấu hình đã chọn."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    chosen = json.loads(open(results_path, encoding="utf-8").read())
    config = AbilityConfig(**chosen["chosen_config"])
    item = ItemConfig(**chosen["chosen_item"])
    data = load_data()
    variants = [
        ("E1: mặc định", E1_CONFIG, None, "#2a78d6", "o"),
        ("Đã tinh chỉnh", config, None, "#eb6834", "s"),
        ("Đã tinh chỉnh + độ lệch rating bài tập", config, item, "#1baf7a", "^"),
    ]
    fig, ax = plt.subplots(figsize=(7.4, 5.6), dpi=150)
    ax.plot([0, 1], [0, 1], color="#9aa0a6", linestyle=(0, (4, 4)), linewidth=1.5, label="Hiệu chỉnh hoàn hảo")
    ax.axvspan(0.65, 0.75, color="#eda100", alpha=0.12, label="Vùng buổi luyện nhắm tới (p ≈ 0,7)")
    ends = []
    for label, cfg, itm, color, marker in variants:
        _, _, raw_bins, _ = test_scores(data, run(data, cfg, itm))
        ax.plot([b.mean_p for b in raw_bins], [b.observed for b in raw_bins], color=color, marker=marker,
                markersize=6, linewidth=2, label=label)
        ends.append((raw_bins[-1].observed, raw_bins[-1].mean_p, label, color))
    placed: list[float] = []
    for y_end, x_end, label, color in sorted(ends, reverse=True):
        y_label = min([y_end] + [p - 0.05 for p in placed[-1:]])
        placed.append(y_label)
        ax.annotate(label, xy=(x_end, y_end), xytext=(1.02, y_label), textcoords=("axes fraction", "data"),
                    fontsize=8, color="#3c4043", va="center", annotation_clip=False,
                    arrowprops={"arrowstyle": "-", "color": color, "linewidth": 0.8})
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Xác suất giải đúng dự đoán (thô, chưa hiệu chỉnh)")
    ax.set_ylabel("Tỉ lệ giải đúng thật")
    ax.set_title("E1b: độ hiệu chỉnh trên phần test", loc="left", fontsize=11)
    ax.grid(color="#e8eaed", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(DOCS_DIR / "e1b-calibration.png")
    print(f"Đã ghi {DOCS_DIR / 'e1b-calibration.png'}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # console Windows mặc định cp1258
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--workers", type=int, default=14)
    parser.add_argument("--plot", action="store_true", help="chỉ vẽ biểu đồ từ e1b-results.json đã có")
    parser.add_argument("--reuse-stage1", action="store_true", help="dùng lại giai đoạn 1 đã lưu (không bị ảnh hưởng bởi δ)")
    args = parser.parse_args()
    if args.plot:
        plot(str(DOCS_DIR / "e1b-results.json"))
        return

    results_path = DOCS_DIR / "e1b-results.json"
    if args.reuse_stage1:
        print("Giai đoạn 1: dùng lại kết quả trong e1b-results.json")
        stage1: list[Result] = json.loads(results_path.read_text(encoding="utf-8"))["stage1_all"]
    else:
        print("Giai đoạn 1: tinh chỉnh AbilityConfig trên validation")
        stage1 = search(player_grid(), args.workers)
    best_config = AbilityConfig(**stage1[0]["config"])
    default_row = next(r for r in stage1 if r["config"] == asdict(E1_CONFIG))
    for label, r in (("mặc định (E1)", default_row), ("tốt nhất", stage1[0])):
        print(f"  {label}: val log-loss {r['val_log_loss']:.4f} (thô {r['val_raw_log_loss']:.4f}), AUC {r['val_auc']:.4f}, {r['config']}")

    standard = [r for r in stage1 if r["config"]["scale"] == E1_CONFIG.scale]
    best_standard = AbilityConfig(**standard[0]["config"])
    print(f"  tốt nhất với thang chuẩn: val log-loss {standard[0]['val_log_loss']:.4f} (thô {standard[0]['val_raw_log_loss']:.4f}), AUC {standard[0]['val_auc']:.4f}, {standard[0]['config']}")

    print("Giai đoạn 2: thêm độ lệch rating theo bài tập")
    stage2 = search(item_grid(best_config), args.workers)
    best_item = ItemConfig(**stage2[0]["item"])
    print(f"  tốt nhất: val log-loss {stage2[0]['val_log_loss']:.4f}, AUC {stage2[0]['val_auc']:.4f}, {stage2[0]['item']}")

    print("Giai đoạn 3: đo một lần trên phần test")
    data = load_data()
    variants = {
        "E1: Elo theo kỹ năng, mặc định": (E1_CONFIG, None),
        "Tinh chỉnh K, giữ thang chuẩn": (best_standard, None),
        "Đã tinh chỉnh (mặc định của app)": (best_config, None),
        "Đã tinh chỉnh + độ lệch rating bài tập": (best_config, best_item),
    }
    rows = []
    print("| Cấu hình | Accuracy | AUC | Log-loss thô | Log-loss sau Platt | p≈0,7 (thô) | p≈0,7 (Platt) |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    runs = {label: run(data, config, item) for label, (config, item) in variants.items()}
    runs["… nhưng δ không học từ phần test"] = run(data, best_config, best_item, learn_from_test=False)
    for label, predictions in runs.items():
        raw, cal, raw_bins, cal_bins = test_scores(data, predictions)
        print(
            f"| {label} | {raw.accuracy:.4f} | {raw.auc:.4f} | {raw.log_loss:.4f} | {cal.log_loss:.4f} | "
            f"{near_target(raw_bins)} | {near_target(cal_bins)} |"
        )
        rows.append({
            "label": label,
            "raw": asdict(raw),
            "platt": asdict(cal),
            "raw_bins": [b._asdict() for b in raw_bins],
            "platt_bins": [b._asdict() for b in cal_bins],
        })

    out = {
        "validation_fraction": VALIDATION_FRACTION,
        "stage1_all": stage1,
        "stage1_default": default_row,
        "stage2_all": stage2,
        "chosen_standard_scale_config": asdict(best_standard),
        "chosen_config": asdict(best_config),
        "chosen_item": asdict(best_item),
        "test": rows,
    }
    target = results_path
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Đã ghi {target}")


if __name__ == "__main__":
    main()
