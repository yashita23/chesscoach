"""Nạp kho bài tập Lichess (CC0) thành định dạng cột.

Tải file gốc (khoảng 300 MB) từ https://database.lichess.org/lichess_db_puzzle.csv.zst rồi chạy:

    uv run python -m chesscoach.puzzle_import full data/raw/lichess_db_puzzle.csv.zst data/puzzles.parquet
    uv run python -m chesscoach.puzzle_import sample data/puzzles.parquet tests/fixtures/puzzles_sample.csv

`full` sắp xếp theo PuzzleId để tra một bài theo id chỉ phải đọc vài row group.
`sample` lấy một bản nhỏ tái lập được (cùng seed thì cùng bộ bài) dùng cho test.
"""

import argparse
import sys
from pathlib import Path

import duckdb

from chesscoach.puzzles import source_sql, sql_path


def import_full(source_csv: Path, target_parquet: Path) -> int:
    target_parquet.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT * FROM {source_sql(source_csv)} ORDER BY PuzzleId) "
        f"TO '{sql_path(target_parquet)}' (FORMAT parquet, COMPRESSION zstd)"
    )
    row = con.execute(f"SELECT count(*) FROM read_parquet('{sql_path(target_parquet)}')").fetchone()
    return int(row[0]) if row else 0


def write_sample(source: Path, target_csv: Path, size: int, seed: int) -> int:
    """Lấy `size` bài ngẫu nhiên (tái lập theo `seed`) trong số bài đủ phổ biến."""
    target_csv.parent.mkdir(parents=True, exist_ok=True)
    reader = source_sql(source)
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT * FROM (SELECT * FROM {reader} WHERE Popularity >= 80 AND NbPlays >= 500) "
        f"USING SAMPLE reservoir({size} ROWS) REPEATABLE ({seed}) ORDER BY PuzzleId) "
        f"TO '{sql_path(target_csv)}' (HEADER, DELIMITER ',')"
    )
    return size


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # console Windows mặc định cp1258
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    full = sub.add_parser("full", help="CSV (.csv hoặc .csv.zst) → parquet đầy đủ")
    full.add_argument("source", type=Path)
    full.add_argument("target", type=Path)
    sample = sub.add_parser("sample", help="lấy bản nhỏ ra CSV")
    sample.add_argument("source", type=Path)
    sample.add_argument("target", type=Path)
    sample.add_argument("--size", type=int, default=300)
    sample.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.command == "full":
        print(f"Đã nạp {import_full(args.source, args.target):,} bài tập vào {args.target}")
    else:
        print(f"Đã ghi {write_sample(args.source, args.target, args.size, args.seed)} bài vào {args.target}")


if __name__ == "__main__":
    main()
