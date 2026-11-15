"""Kho bài tập: đọc bài tập Lichess từ parquet (bản đầy đủ) hoặc CSV (bản mẫu) qua DuckDB."""

from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

# Cột của bản CSV Lichess; khai báo rõ kiểu để không phụ thuộc vào việc DuckDB tự đoán.
CSV_COLUMNS = {
    "PuzzleId": "VARCHAR",
    "FEN": "VARCHAR",
    "Moves": "VARCHAR",
    "Rating": "INTEGER",
    "RatingDeviation": "INTEGER",
    "Popularity": "INTEGER",
    "NbPlays": "INTEGER",
    "Themes": "VARCHAR",
    "GameUrl": "VARCHAR",
    "OpeningTags": "VARCHAR",
    "DailyDate": "BIGINT",
}

# Bài tập đủ phổ biến để đưa cho người chơi (lọc bài lỗi hoặc gượng ép).
POPULAR = "Popularity >= 80 AND NbPlays >= 500"

_SELECT = (
    "PuzzleId, FEN, Moves, Rating, RatingDeviation, Popularity, NbPlays, Themes, GameUrl, OpeningTags"
)


def sql_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


def source_sql(path: Path) -> str:
    """Biểu thức FROM của DuckDB cho một file kho bài tập (.parquet, .csv hoặc .csv.zst)."""
    if path.suffix == ".parquet":
        return f"read_parquet('{sql_path(path)}')"
    columns = ", ".join(f"'{name}': '{kind}'" for name, kind in CSV_COLUMNS.items())
    return f"read_csv('{sql_path(path)}', header = true, columns = {{{columns}}})"


@dataclass(frozen=True)
class Puzzle:
    """Bài tập: thế cờ FEN trước nước của đối thủ, và chuỗi nước giải (UCI) bắt đầu bằng nước đó."""

    id: str
    fen: str
    moves: tuple[str, ...]
    rating: int
    rating_deviation: int
    popularity: int
    nb_plays: int
    themes: tuple[str, ...]
    game_url: str
    opening_tags: tuple[str, ...]


def _puzzle(row: tuple[Any, ...]) -> Puzzle:
    pid, fen, moves, rating, rd, popularity, nb_plays, themes, game_url, opening_tags = row
    return Puzzle(
        id=pid,
        fen=fen,
        moves=tuple(moves.split()),
        rating=rating,
        rating_deviation=rd,
        popularity=popularity,
        nb_plays=nb_plays,
        themes=tuple((themes or "").split()),
        game_url=game_url or "",
        opening_tags=tuple((opening_tags or "").split()),
    )


class PuzzleCatalog:
    """Kho bài tập chỉ đọc. An toàn khi gọi từ nhiều thread: mỗi truy vấn dùng cursor riêng."""

    def __init__(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(
                f"Không thấy kho bài tập {path}. Chạy `uv run python -m chesscoach.puzzle_import` "
                "(xem README) hoặc đặt CHESSCOACH_PUZZLE_CATALOG."
            )
        self._con = duckdb.connect()
        self._con.execute(f"CREATE VIEW puzzles AS SELECT {_SELECT} FROM {source_sql(path)}")

    def _fetch(self, sql: str, params: list[Any]) -> list[tuple[Any, ...]]:
        """Chạy truy vấn trên một cursor riêng rồi đóng nó ngay.

        Cursor riêng giúp an toàn khi nhiều request chạy song song; đóng ngay để không giữ tài nguyên.
        """
        cursor = self._con.cursor()
        try:
            return cursor.execute(sql, params).fetchall()
        finally:
            cursor.close()

    def get(self, puzzle_id: str) -> Puzzle | None:
        rows = self._fetch(f"SELECT {_SELECT} FROM puzzles WHERE PuzzleId = ?", [puzzle_id])
        return _puzzle(rows[0]) if rows else None

    def candidates(
        self, min_rating: float, max_rating: float, exclude: Collection[str], limit: int, seed: str
    ) -> list[Puzzle]:
        """Tối đa `limit` bài tập phổ biến trong khoảng rating, chưa nằm trong `exclude`.

        Thứ tự giả ngẫu nhiên nhưng cố định theo `seed`: cùng seed thì cùng danh sách.
        """
        rows = self._fetch(
            f"SELECT {_SELECT} FROM puzzles "
            f"WHERE {POPULAR} AND Rating BETWEEN ? AND ? AND NOT list_contains(?, PuzzleId) "
            "ORDER BY hash(PuzzleId || ?) LIMIT ?",
            [min_rating, max_rating, list(exclude), seed, limit],
        )
        return [_puzzle(row) for row in rows]

    def random_excluding(self, exclude: Collection[str]) -> Puzzle | None:
        """Một bài tập phổ biến bất kỳ chưa nằm trong `exclude`; dùng khi buổi luyện không còn bài tập vừa sức."""
        rows = self._fetch(
            f"SELECT {_SELECT} FROM puzzles WHERE {POPULAR} AND NOT list_contains(?, PuzzleId) "
            "ORDER BY random() LIMIT 1",
            [list(exclude)],
        )
        return _puzzle(rows[0]) if rows else None
