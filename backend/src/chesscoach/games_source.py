from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import re
from typing import Any, Protocol

import chess.pgn
import httpx


@dataclass(frozen=True)
class RawGame:
    """Ván cờ tải về từ nguồn bên ngoài (Lichess/Chess.com)."""

    game_id: str
    pgn: str
    played_at: datetime
    perf_type: str
    evals: dict[str, Any] | None = None


class UserNotFoundError(Exception):
    """Tài khoản không tồn tại trên nền tảng nguồn."""


class RateLimitError(Exception):
    """Bị giới hạn tốc độ yêu cầu (HTTP 429)."""


class SourceNetworkError(Exception):
    """Lỗi mạng hoặc không thể kết nối tới nguồn ván."""


class GameSource(Protocol):
    """Port nguồn ván cờ từ các nền tảng cờ trực tuyến."""

    def check_user_exists(self, username: str) -> bool:
        """Kiểm tra tài khoản có tồn tại trên nền tảng không."""
        ...

    def fetch_games(
        self,
        username: str,
        since: datetime | None = None,
        perf_types: tuple[str, ...] = ("blitz", "rapid", "classical"),
        max_games: int = 50,
    ) -> list[RawGame]:
        """Tải các ván cờ gần nhất của người chơi."""
        ...


def _parse_time_control_initial_seconds(time_control: str) -> int | None:
    """Trả về số giây cơ bản ban đầu từ TimeControl header (ví dụ '180+0' -> 180)."""
    if not time_control or time_control == "-":
        return None
    match = re.match(r"^(\d+)(?:\+(\d+))?", time_control)
    if match:
        return int(match.group(1))
    return None


def _parse_perf_type(event: str) -> str:
    """Suy đoán perf_type (blitz, rapid, classical) từ Event header."""
    lower = event.lower()
    if "bullet" in lower:
        return "bullet"
    if "blitz" in lower:
        return "blitz"
    if "rapid" in lower:
        return "rapid"
    if "classical" in lower:
        return "classical"
    if "correspondence" in lower:
        return "correspondence"
    return "unknown"


def _parse_played_at(headers: chess.pgn.Headers) -> datetime:
    """Rút trích thời điểm ván diễn ra theo UTC."""
    utc_date = headers.get("UTCDate", headers.get("Date", ""))
    utc_time = headers.get("UTCTime", headers.get("Time", "00:00:00"))

    cleaned_date = utc_date.replace("?", "1").replace(".", "-")
    cleaned_time = utc_time.replace("?", "0")

    try:
        dt = datetime.fromisoformat(f"{cleaned_date}T{cleaned_time}")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def parse_lichess_pgn(
    pgn_text: str,
    allowed_perfs: Collection[str] = ("blitz", "rapid", "classical"),
    min_initial_seconds: int = 180,
) -> list[RawGame]:
    """Phân tích chuỗi PGN (có thể chứa nhiều ván) từ Lichess.

    - Bỏ ván bullet và ván có thời gian cơ bản dưới 3 phút (min_initial_seconds = 180).
    - Rút trích game_id, played_at, perf_type và đánh giá máy tính (%eval).
    """
    sio = io.StringIO(pgn_text)
    games: list[RawGame] = []

    while True:
        game = chess.pgn.read_game(sio)
        if game is None:
            break

        headers = game.headers
        event = headers.get("Event", "")
        perf_type = _parse_perf_type(event)

        # Lọc bỏ bullet hoặc thể thức không thuộc danh sách cho phép
        if perf_type not in allowed_perfs:
            continue

        # Lọc ván dưới 3 phút (180 giây)
        time_control = headers.get("TimeControl", "")
        base_sec = _parse_time_control_initial_seconds(time_control)
        if base_sec is not None and base_sec < min_initial_seconds:
            continue

        # Lấy game_id từ Site URL (ví dụ https://lichess.org/abc12345)
        site = headers.get("Site", "")
        game_id = site.rstrip("/").split("/")[-1] if site else ""
        if not game_id:
            game_id = headers.get("GameId", "")
        if not game_id:
            continue

        played_at = _parse_played_at(headers)

        # Kiểm tra evals trong comment nước đi
        has_evals = False
        eval_list: list[dict[str, Any]] = []
        for node in game.mainline():
            comment = node.comment
            if "[%eval" in comment:
                has_evals = True
                eval_match = re.search(r"\[%eval\s+([^\]]+)\]", comment)
                if eval_match:
                    eval_list.append({"ply": node.ply(), "eval": eval_match.group(1)})

        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        game_pgn = game.accept(exporter)

        evals_dict: dict[str, Any] | None = None
        if has_evals:
            evals_dict = {"has_evals": True, "evals": eval_list}

        games.append(
            RawGame(
                game_id=game_id,
                pgn=game_pgn,
                played_at=played_at,
                perf_type=perf_type,
                evals=evals_dict,
            )
        )

    return games


class FakeGameSource(GameSource):
    """Nguồn ván giả lập dùng cho kiểm thử."""

    def __init__(
        self,
        existing_users: set[str] | None = None,
        games_by_user: dict[str, list[RawGame]] | None = None,
        rate_limited: bool = False,
        network_error: bool = False,
    ) -> None:
        self.existing_users = set(existing_users or ())
        self.games_by_user: dict[str, list[RawGame]] = {
            k: list(v) for k, v in (games_by_user or {}).items()
        }
        self.rate_limited = rate_limited
        self.network_error = network_error

    def add_pgn(self, username: str, pgn_text: str) -> None:
        """Nạp thêm PGN mẫu cho user."""
        parsed = parse_lichess_pgn(pgn_text)
        if username not in self.games_by_user:
            self.games_by_user[username] = []
        self.games_by_user[username].extend(parsed)

    def check_user_exists(self, username: str) -> bool:
        if self.network_error:
            raise SourceNetworkError("Mất kết nối mạng tới Lichess")
        if self.rate_limited:
            raise RateLimitError("Bị giới hạn tốc độ (HTTP 429)")
        return username.lower() in {u.lower() for u in self.existing_users}

    def fetch_games(
        self,
        username: str,
        since: datetime | None = None,
        perf_types: tuple[str, ...] = ("blitz", "rapid", "classical"),
        max_games: int = 50,
    ) -> list[RawGame]:
        if self.network_error:
            raise SourceNetworkError("Mất kết nối mạng tới Lichess")
        if self.rate_limited:
            raise RateLimitError("Bị giới hạn tốc độ (HTTP 429)")
        if not self.check_user_exists(username):
            raise UserNotFoundError(f"Tài khoản '{username}' không tồn tại")

        all_games = self.games_by_user.get(username, [])
        since_cmp = since
        if since_cmp is not None and since_cmp.tzinfo is None:
            since_cmp = since_cmp.replace(tzinfo=timezone.utc)

        filtered: list[RawGame] = []
        for g in all_games:
            if g.perf_type not in perf_types:
                continue
            g_played = g.played_at
            if g_played.tzinfo is None:
                g_played = g_played.replace(tzinfo=timezone.utc)
            if since_cmp is not None and g_played <= since_cmp:
                continue
            filtered.append(g)

        filtered.sort(key=lambda g: g.played_at, reverse=True)
        return filtered[:max_games]


class LichessAdapter(GameSource):
    """Adapter lấy ván cờ từ Lichess API công khai."""

    def __init__(self, base_url: str = "https://lichess.org", timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def check_user_exists(self, username: str) -> bool:
        url = f"{self.base_url}/api/user/{username}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url)
                if res.status_code == 200:
                    return True
                if res.status_code == 404:
                    return False
                if res.status_code == 429:
                    raise RateLimitError("Lichess: Quá nhiều yêu cầu (HTTP 429). Vui lòng thử lại sau.")
                res.raise_for_status()
                return False
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
            raise SourceNetworkError(f"Lỗi kết nối tới Lichess: {e}") from e

    def fetch_games(
        self,
        username: str,
        since: datetime | None = None,
        perf_types: tuple[str, ...] = ("blitz", "rapid", "classical"),
        max_games: int = 50,
    ) -> list[RawGame]:
        url = f"{self.base_url}/api/games/user/{username}"
        params: dict[str, Any] = {
            "perfType": ",".join(perf_types),
            "max": max_games,
            "evals": "true",
            "clocks": "true",
            "opening": "false",
        }
        if since is not None:
            # Lichess API dùng timestamp tính bằng mili-giây
            params["since"] = int(since.timestamp() * 1000)

        headers = {"Accept": "application/x-chess-pgn"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(url, params=params, headers=headers)
                if res.status_code == 404:
                    raise UserNotFoundError(f"Tài khoản '{username}' không tồn tại trên Lichess")
                if res.status_code == 429:
                    raise RateLimitError("Lichess: Quá nhiều yêu cầu (HTTP 429). Vui lòng chờ vài phút rồi thử lại.")
                res.raise_for_status()
                return parse_lichess_pgn(res.text, allowed_perfs=perf_types)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
            raise SourceNetworkError(f"Không thể tải ván từ Lichess do lỗi mạng: {e}") from e
