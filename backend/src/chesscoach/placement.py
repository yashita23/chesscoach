"""Bài kiểm tra đầu vào: bộ bài tập cố định theo dải 200 điểm của tiên nghiệm năng lực.

Bộ bài tập chọn trước bằng `placement_build` và lưu thành JSON. Người chơi mới (chưa có lần giải nào) làm bài kiểm
tra trước buổi luyện. Dải được chốt khi người chơi mở lần giải đầu tiên của bài kiểm tra, nên khai rating ván trước
đó vẫn kịp đổi dải. Người chơi đã có lần giải từ trước (chưa từng bắt đầu bài kiểm tra) không phải làm.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from chesscoach.ability_history import prior_ability
from chesscoach.db import Attempt, Player


@dataclass(frozen=True)
class PlacementSets:
    band_width: int
    sets: dict[int, tuple[str, ...]]
    """Mép dưới dải → id các bài tập, theo thứ tự làm."""

    @classmethod
    def load(cls, path: Path) -> "PlacementSets":
        data = json.loads(path.read_text(encoding="utf-8"))
        sets = {int(low): tuple(p["puzzle_id"] for p in items) for low, items in data["sets"].items() if items}
        return cls(band_width=int(data["band_width"]), sets=sets)

    def band_for(self, theta: float) -> int:
        """Dải chứa θ; θ ngoài mọi dải thì lấy dải gần nhất."""
        lows = sorted(self.sets)
        inside = [low for low in lows if low <= theta < low + self.band_width]
        return inside[0] if inside else min(lows, key=lambda low: abs(low + self.band_width / 2 - theta))


@dataclass(frozen=True)
class PlacementStatus:
    band: int
    puzzle_ids: tuple[str, ...]
    completed: int
    """Số bài tập của bài kiểm tra đã có lần giải được chốt nhãn."""
    started: bool
    """Dải đã chốt (người chơi đã mở lần giải đầu tiên của bài kiểm tra)."""
    remaining: tuple[str, ...]


def placement_status(db: Session, player: Player, sets: PlacementSets | None) -> PlacementStatus | None:
    """Trạng thái bài kiểm tra đầu vào, hoặc None khi người chơi không cần (hoặc không còn phải) làm."""
    if sets is None:
        return None
    attempts = db.scalars(select(Attempt).where(Attempt.player_id == player.id)).all()
    if player.placement_band is None:
        if attempts:
            return None  # đã có lần giải trước khi bài kiểm tra bắt đầu: không phải người chơi mới
        band, started = sets.band_for(prior_ability(player).theta), False
    else:
        band, started = player.placement_band, True
    ids = sets.sets.get(band, ())
    labeled = {a.puzzle_id for a in attempts if a.correct is not None}
    remaining = tuple(pid for pid in ids if pid not in labeled)
    if not remaining:
        return None
    return PlacementStatus(band, ids, len(ids) - len(remaining), started, remaining)
