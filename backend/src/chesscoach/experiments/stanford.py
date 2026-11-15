"""Bộ Stanford CS398 Chess.com Knowledge Tracing: đọc dữ liệu, chia train/test theo thời gian, đo dự đoán.

Dữ liệu không nằm trong repo. Tải starter bundle từ
https://web.stanford.edu/class/cs398/handouts/knowledge-tracing/starter_bundle.zip rồi giải nén vào
`backend/data/stanford/raw/` (xem docs/experiments/e0-stanford.md).

Tập test gốc ẩn nhãn, nên mỗi người chơi được chia lại: 20% lần giải cuối theo thời gian làm test.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import numpy.typing as npt

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "stanford" / "raw"
SPLIT_DIR = RAW_DIR.parent / "split"
TEST_FRACTION = 0.2
DEFAULT_SEED = 398

FloatArray = npt.NDArray[np.float64]


def _sql_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


def make_split(raw_dir: Path = RAW_DIR, out_dir: Path = SPLIT_DIR, seed: int = DEFAULT_SEED) -> dict[str, int]:
    """Chia train.csv theo thời gian trong từng người chơi và ghi ra parquet.

    Mỗi người chơi: sắp lần giải theo create_date (lần giải trùng thời điểm được xếp theo một hoán vị
    cố định theo `seed`), lấy ceil(20%) lần giải cuối làm test. Cùng seed thì ra đúng phép chia đó.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SELECT setseed(?)", [1 / (1 + seed)])
    con.execute(
        f"""
        CREATE TABLE ordered AS
        SELECT *,
               row_number() OVER (PARTITION BY user_id ORDER BY create_date, tiebreak) AS seq,
               count(*) OVER (PARTITION BY user_id) AS n_user
        FROM (SELECT *, hash(user_id, tactics_problem_id, create_date, {seed}) AS tiebreak
              FROM read_csv('{_sql_path(raw_dir / "train.csv")}', header = true))
        """
    )
    split = f"seq > n_user - ceil(n_user * {TEST_FRACTION})"
    columns = (
        "user_id, tactics_problem_id, create_date, seq, pre_rating, puzzle_rating_original, "
        "puzzle_rating_ours, puzzle_move_count, target_time, solve_time, is_correct"
    )
    for name, cond in (("train", f"NOT ({split})"), ("test", split)):
        con.execute(
            f"COPY (SELECT {columns} FROM ordered WHERE {cond} ORDER BY user_id, seq) "
            f"TO '{_sql_path(out_dir / f'{name}.parquet')}' (FORMAT parquet)"
        )
    counts = {
        name: int(con.execute(f"SELECT count(*) FROM ordered WHERE {cond}").fetchone()[0])  # type: ignore[index]
        for name, cond in (("train", f"NOT ({split})"), ("test", split))
    }
    manifest = {"seed": seed, "test_fraction": TEST_FRACTION, **counts}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return counts


@dataclass(frozen=True)
class Split:
    """Một phần của phép chia, dạng cột numpy."""

    user_id: npt.NDArray[np.int64]
    pre_rating: FloatArray
    puzzle_rating_original: FloatArray
    puzzle_rating_ours: FloatArray
    is_correct: FloatArray

    def __len__(self) -> int:
        return len(self.is_correct)


def load_split(name: str, split_dir: Path = SPLIT_DIR) -> Split:
    rows = duckdb.connect().execute(
        "SELECT user_id, pre_rating, puzzle_rating_original, puzzle_rating_ours, is_correct "
        f"FROM read_parquet('{_sql_path(split_dir / f'{name}.parquet')}') ORDER BY user_id, seq"
    ).fetchnumpy()
    return Split(
        user_id=rows["user_id"].astype(np.int64),
        pre_rating=rows["pre_rating"].astype(np.float64),
        puzzle_rating_original=rows["puzzle_rating_original"].astype(np.float64),
        puzzle_rating_ours=rows["puzzle_rating_ours"].astype(np.float64),
        is_correct=rows["is_correct"].astype(np.float64),
    )


@dataclass(frozen=True)
class Scores:
    accuracy: float
    auc: float
    log_loss: float
    mean_p: float


def score(p: FloatArray, y: FloatArray) -> Scores:
    """Accuracy (ngưỡng 0,5, giống leaderboard), AUC và log-loss."""
    p = np.clip(p, 1e-6, 1 - 1e-6)
    accuracy = float(np.mean((p >= 0.5) == (y == 1)))
    log_loss = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    return Scores(accuracy, auc(p, y), log_loss, float(np.mean(p)))


def auc(p: FloatArray, y: FloatArray) -> float:
    """AUC theo hạng (Mann–Whitney), xử lý điểm bằng nhau bằng hạng trung bình."""
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


def elo(player_rating: FloatArray, puzzle_rating: FloatArray) -> FloatArray:
    """Công thức Elo sách giáo khoa: 1 / (1 + 10^((rating bài tập − rating người chơi) / 400))."""
    result: FloatArray = 1.0 / (1.0 + 10.0 ** ((puzzle_rating - player_rating) / 400.0))
    return result


def fit_logistic(x: FloatArray, y: FloatArray, iterations: int = 25) -> tuple[float, float]:
    """Hồi quy logistic một biến p = σ(a + b·x), giải bằng Newton. Trả về (a, b)."""
    a, b = 0.0, 0.0
    for _ in range(iterations):
        z = np.clip(a + b * x, -30, 30)
        p = 1 / (1 + np.exp(-z))
        w = p * (1 - p)
        g = np.array([np.sum(y - p), np.sum((y - p) * x)])
        h = np.array([[np.sum(w), np.sum(w * x)], [np.sum(w * x), np.sum(w * x * x)]])
        step = np.linalg.solve(h, g)
        a, b = a + float(step[0]), b + float(step[1])
        if math.hypot(*step) < 1e-10:
            break
    return a, b
