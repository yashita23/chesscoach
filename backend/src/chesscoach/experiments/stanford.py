"""Bộ Stanford CS398 Chess.com Knowledge Tracing: đọc dữ liệu và chia train/test theo thời gian.

Dữ liệu không nằm trong repo. Tải starter bundle từ
https://web.stanford.edu/class/cs398/handouts/knowledge-tracing/starter_bundle.zip rồi giải nén vào
`backend/data/stanford/raw/` (xem docs/experiments/e0-stanford.md).

Tập test gốc ẩn nhãn, nên mỗi người chơi được chia lại: 20% lần giải cuối theo thời gian làm test.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import duckdb
import numpy as np
import numpy.typing as npt

from chesscoach.experiments.metrics import FloatArray

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "stanford" / "raw"
SPLIT_DIR = RAW_DIR.parent / "split"
TEST_FRACTION = 0.2
DEFAULT_SEED = 398

Part = Literal["train", "test"]
_COLUMNS = (
    "user_id, tactics_problem_id, create_date, seq, pre_rating, puzzle_rating_original, "
    "puzzle_rating_ours, puzzle_move_count, target_time, solve_time, is_correct"
)


def _sql_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


def make_split(raw_dir: Path = RAW_DIR, out_dir: Path = SPLIT_DIR, seed: int = DEFAULT_SEED) -> dict[Part, int]:
    """Chia train.csv theo thời gian trong từng người chơi và ghi ra parquet.

    Mỗi người chơi: sắp lần giải theo create_date, lấy ceil(20%) lần giải cuối làm test. Lần giải trùng
    thời điểm được xếp theo hash(số dòng trong file, seed), nên cùng seed thì ra đúng phép chia đó, kể cả
    thứ tự `seq`. Trên bộ hiện tại chỉ 12 dòng trùng thời điểm, nên seed hầu như không đổi phép chia.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(
        f"""
        CREATE TABLE ordered AS
        SELECT *,
               row_number() OVER (PARTITION BY user_id ORDER BY create_date, hash(file_row, {int(seed)})) AS seq,
               count(*) OVER (PARTITION BY user_id) AS n_user
        FROM (SELECT *, row_number() OVER () AS file_row
              FROM read_csv('{_sql_path(raw_dir / "train.csv")}', header = true))
        """
    )
    in_test = f"seq > n_user - ceil(n_user * {TEST_FRACTION})"
    parts: dict[Part, str] = {"train": f"NOT ({in_test})", "test": in_test}
    counts: dict[Part, int] = {}
    for part, condition in parts.items():
        con.execute(
            f"COPY (SELECT {_COLUMNS} FROM ordered WHERE {condition} ORDER BY user_id, seq) "
            f"TO '{_sql_path(out_dir / f'{part}.parquet')}' (FORMAT parquet)"
        )
        row = con.execute(f"SELECT count(*) FROM ordered WHERE {condition}").fetchone()
        counts[part] = int(row[0]) if row else 0
    manifest = {"seed": seed, "test_fraction": TEST_FRACTION, "train": counts["train"], "test": counts["test"]}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return counts


@dataclass(frozen=True)
class SplitPart:
    """Một phần (train hoặc test) của phép chia, dạng cột numpy."""

    user_id: npt.NDArray[np.int64]
    tactics_problem_id: npt.NDArray[np.int64]
    pre_rating: FloatArray
    """Rating giải bài tập (tactics rating) của người chơi trên Chess.com, trước lần giải."""
    puzzle_rating_original: FloatArray
    puzzle_rating_ours: FloatArray
    is_correct: FloatArray

    def __len__(self) -> int:
        return len(self.is_correct)

    def where(self, mask: npt.NDArray[np.bool_]) -> "SplitPart":
        return SplitPart(
            self.user_id[mask],
            self.tactics_problem_id[mask],
            self.pre_rating[mask],
            self.puzzle_rating_original[mask],
            self.puzzle_rating_ours[mask],
            self.is_correct[mask],
        )


def load_split(part: Part, split_dir: Path = SPLIT_DIR) -> SplitPart:
    rows = duckdb.connect().execute(
        "SELECT user_id, tactics_problem_id, pre_rating, puzzle_rating_original, puzzle_rating_ours, is_correct "
        f"FROM read_parquet('{_sql_path(split_dir / f'{part}.parquet')}') ORDER BY user_id, seq"
    ).fetchnumpy()
    return SplitPart(
        user_id=rows["user_id"].astype(np.int64),
        tactics_problem_id=rows["tactics_problem_id"].astype(np.int64),
        pre_rating=rows["pre_rating"].astype(np.float64),
        puzzle_rating_original=rows["puzzle_rating_original"].astype(np.float64),
        puzzle_rating_ours=rows["puzzle_rating_ours"].astype(np.float64),
        is_correct=rows["is_correct"].astype(np.float64),
    )


def hidden_test_puzzles(raw_dir: Path = RAW_DIR) -> npt.NDArray[np.int64]:
    """Các bài tập có trong test.csv gốc (leaderboard), để đo lại trên cùng tập bài tập đó."""
    rows = duckdb.connect().execute(
        f"SELECT DISTINCT tactics_problem_id FROM read_csv('{_sql_path(raw_dir / 'test.csv')}', header = true)"
    ).fetchnumpy()
    return rows["tactics_problem_id"].astype(np.int64)
