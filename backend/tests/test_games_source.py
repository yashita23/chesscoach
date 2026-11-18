from datetime import datetime, timezone
import httpx
import pytest
from chesscoach.games_source import (
    FakeGameSource,
    GameSource,
    LichessAdapter,
    RateLimitError,
    RawGame,
    SourceNetworkError,
    UserNotFoundError,
    parse_lichess_pgn,
)

SAMPLE_PGN_BLITZ = """[Event "Rated blitz game"]
[Site "https://lichess.org/abc12345"]
[Date "2026.11.10"]
[Time "14:30:00"]
[UTCDate "2026.11.10"]
[UTCTime "14:30:00"]
[White "PlayerWhite"]
[Black "PlayerBlack"]
[Result "1-0"]
[TimeControl "180+0"]
[Termination "Normal"]

1. e4 { [%eval 0.2] } 1... e5 { [%eval 0.3] } 2. Nf3 { [%eval 0.4] } 1-0
"""

SAMPLE_PGN_BULLET = """[Event "Rated bullet game"]
[Site "https://lichess.org/bullet01"]
[Date "2026.11.10"]
[UTCDate "2026.11.10"]
[UTCTime "15:00:00"]
[White "PlayerWhite"]
[Black "PlayerBlack"]
[Result "0-1"]
[TimeControl "60+0"]

1. e4 1... e5 0-1
"""

SAMPLE_PGN_UNDER_3_MIN = """[Event "Rated blitz game"]
[Site "https://lichess.org/under3m"]
[Date "2026.11.10"]
[UTCDate "2026.11.10"]
[UTCTime "15:30:00"]
[White "PlayerWhite"]
[Black "PlayerBlack"]
[Result "1/2-1/2"]
[TimeControl "120+1"]

1. d4 1... d5 1/2-1/2
"""

SAMPLE_PGN_RAPID_NO_EVAL = """[Event "Rated rapid game"]
[Site "https://lichess.org/rapid999"]
[Date "2026.11.12"]
[UTCDate "2026.11.12"]
[UTCTime "10:00:00"]
[White "PlayerWhite"]
[Black "PlayerBlack"]
[Result "1-0"]
[TimeControl "600+0"]

1. e4 e5 2. Bc4 Bc5 1-0
"""


def test_fake_source_user_exists() -> None:
    source = FakeGameSource(existing_users={"lichess_user"})
    assert source.check_user_exists("lichess_user") is True
    assert source.check_user_exists("unknown_user") is False


def test_fake_source_fetch_games() -> None:
    game_blitz = RawGame(
        game_id="abc12345",
        pgn=SAMPLE_PGN_BLITZ,
        played_at=datetime(2026, 11, 10, 14, 30, tzinfo=timezone.utc),
        perf_type="blitz",
        evals={"has_evals": True},
    )
    source = FakeGameSource(
        existing_users={"test_user"},
        games_by_user={"test_user": [game_blitz]},
    )
    games = source.fetch_games("test_user")
    assert len(games) == 1
    assert games[0].game_id == "abc12345"
    assert games[0].perf_type == "blitz"
    assert games[0].evals is not None


def test_fake_source_filters_bullet_and_under_3_minutes() -> None:
    source = FakeGameSource(existing_users={"user1"})
    source.add_pgn("user1", SAMPLE_PGN_BLITZ)  # 180+0 blitz: keep
    source.add_pgn("user1", SAMPLE_PGN_BULLET)  # 60+0 bullet: filter out
    source.add_pgn("user1", SAMPLE_PGN_UNDER_3_MIN)  # 120+1 (< 180s): filter out
    source.add_pgn("user1", SAMPLE_PGN_RAPID_NO_EVAL)  # 600+0 rapid: keep

    games = source.fetch_games("user1")
    ids = [g.game_id for g in games]
    assert "abc12345" in ids
    assert "rapid999" in ids
    assert "bullet01" not in ids
    assert "under3m" not in ids


def test_fake_source_respects_since() -> None:
    source = FakeGameSource(existing_users={"user1"})
    source.add_pgn("user1", SAMPLE_PGN_BLITZ)  # 2026-11-10
    source.add_pgn("user1", SAMPLE_PGN_RAPID_NO_EVAL)  # 2026-11-12

    since = datetime(2026, 11, 11, 0, 0, tzinfo=timezone.utc)
    games = source.fetch_games("user1", since=since)
    assert len(games) == 1
    assert games[0].game_id == "rapid999"


def test_fake_source_simulates_errors() -> None:
    source = FakeGameSource(
        existing_users={"user1"},
        rate_limited=True,
    )
    with pytest.raises(RateLimitError):
        source.fetch_games("user1")

    source_net_err = FakeGameSource(
        existing_users={"user1"},
        network_error=True,
    )
    with pytest.raises(SourceNetworkError):
        source_net_err.fetch_games("user1")


def test_parse_lichess_pgn_extracts_metadata_and_evals() -> None:
    games = parse_lichess_pgn(SAMPLE_PGN_BLITZ)
    assert len(games) == 1
    game = games[0]
    assert game.game_id == "abc12345"
    assert game.perf_type == "blitz"
    assert game.played_at == datetime(2026, 11, 10, 14, 30, tzinfo=timezone.utc)
    assert game.evals is not None
    assert game.evals.get("has_evals") is True


def test_lichess_adapter_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = LichessAdapter()

    # Test user 200 vs 404 vs 429
    class DummyClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "DummyClient":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def get(self, url: str, **kwargs: object) -> httpx.Response:
            headers = kwargs.get("headers", {})
            header_keys = [k.lower() for k in headers.keys()] if isinstance(headers, dict) else []
            assert "user-agent" in header_keys, "Lichess requests must specify a User-Agent header"

            req = httpx.Request("GET", url)
            if "api/user/existing" in url:
                return httpx.Response(200, json={"id": "existing"}, request=req)
            if "api/user/nonexistent" in url:
                return httpx.Response(404, request=req)
            if "api/user/rate_limited" in url:
                return httpx.Response(429, request=req)
            if "api/games/user/existing" in url:
                return httpx.Response(200, text=SAMPLE_PGN_BLITZ, request=req)
            return httpx.Response(404, request=req)

    monkeypatch.setattr(httpx, "Client", DummyClient)

    assert adapter.check_user_exists("existing") is True
    assert adapter.check_user_exists("nonexistent") is False
    with pytest.raises(RateLimitError):
        adapter.check_user_exists("rate_limited")

    games = adapter.fetch_games("existing")
    assert len(games) == 1
    assert games[0].game_id == "abc12345"

