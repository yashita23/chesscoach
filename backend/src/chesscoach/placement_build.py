"""Chọn trước bộ bài kiểm tra đầu vào: mỗi dải 200 điểm một bộ 12 bài tập, mỗi bài tập một kỹ năng.

    uv run python -m chesscoach.placement_build data/puzzles.parquet src/chesscoach/placement_sets.json
    uv run python -m chesscoach.placement_build tests/fixtures/puzzles_sample.csv tests/fixtures/placement_sample.json

- 12 kỹ năng: phổ biến nhất trong kho (đếm theo bài tập), trừ "bỏ lỡ chiến thuật" vì nó không đo một mẫu cụ thể.
- Dải: 400–600, 600–800, …, 2600–2800. Bài tập nhắm rating giữa dải, nơi người chơi có năng lực bằng giữa dải giải
  đúng khoảng 50%: mức cho nhiều thông tin nhất.
- Ưu tiên bài tập chỉ có đúng kỹ năng đó, rating cách giữa dải không quá 100, Popularity cao rồi NbPlays cao. Thiếu
  thì nới dần: cho phép có thêm kỹ năng khác, rồi nới khoảng rating tới ±400. Không bài tập nào dùng hai lần trong
  một bộ.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import duckdb

from chesscoach.puzzles import POPULAR, source_sql
from chesscoach.skills import MISSED_TACTIC, SKILLS, SKILLS_BY_ID, skills_of

BAND_LOWS = tuple(range(400, 2800, 200))
SKILLS_PER_SET = 12
RATING_STEPS = (100, 200, 400)


def _list(values: frozenset[str]) -> str:
    return "[" + ", ".join(f"'{v}'" for v in sorted(values)) + "]"


def most_common_skills(con: duckdb.DuckDBPyConnection) -> list[str]:
    counts: Counter[str] = Counter()
    for (themes,) in con.execute(f"SELECT Themes FROM puzzles WHERE {POPULAR}").fetchall():
        counts.update(skills_of((themes or "").split()))
    return [s for s, _ in counts.most_common() if s != MISSED_TACTIC][:SKILLS_PER_SET]


def pick(con: duckdb.DuckDBPyConnection, skill: str, center: int, used: set[str]) -> str | None:
    own = SKILLS_BY_ID[skill].themes
    others = frozenset(t for s in SKILLS if s.id != skill for t in s.themes)
    has_skill = f"list_has_any(string_split(Themes, ' '), {_list(own)})"
    only_skill = f"NOT list_has_any(string_split(Themes, ' '), {_list(others)})"
    for exclusive in (True, False):
        for step in RATING_STEPS:
            row = con.execute(
                f"SELECT PuzzleId FROM puzzles WHERE {POPULAR} AND {has_skill} "
                f"{'AND ' + only_skill if exclusive else ''} AND abs(Rating - ?) <= ? "
                "AND NOT list_contains(?, PuzzleId) ORDER BY Popularity DESC, NbPlays DESC, PuzzleId LIMIT 1",
                [center, step, sorted(used)],
            ).fetchone()
            if row:
                return str(row[0])
    return None


def build(source: Path) -> dict[str, object]:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW puzzles AS SELECT * FROM {source_sql(source)}")
    skills = most_common_skills(con)
    sets: dict[str, list[dict[str, str]]] = {}
    for low in BAND_LOWS:
        used: set[str] = set()
        chosen = []
        for skill in skills:
            puzzle = pick(con, skill, low + 100, used)
            if puzzle:
                used.add(puzzle)
                chosen.append({"skill": skill, "puzzle_id": puzzle})
        sets[str(low)] = chosen
    return {"source": source.name, "skills": skills, "band_width": 200, "sets": sets}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # console Windows mặc định cp1258
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("source", type=Path, help="kho bài tập (.parquet hoặc .csv)")
    parser.add_argument("target", type=Path, help="file JSON đầu ra")
    args = parser.parse_args()
    result = build(args.source)
    args.target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sizes = {low: len(s) for low, s in result["sets"].items()}  # type: ignore[attr-defined]
    print(f"12 kỹ năng: {', '.join(result['skills'])}")  # type: ignore[arg-type]
    print(f"Số bài tập mỗi dải: {sizes}")


if __name__ == "__main__":
    main()
