from collections.abc import Iterator
from datetime import datetime, timezone
import threading
import time
from typing import Any, cast
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from chesscoach.app import create_app
from chesscoach.games_source import FakeGameSource, RawGame
from helpers import PUZZLE_SAMPLE, play, register_new_player, start

SAMPLE_PGN_1 = """[Event "Rated blitz game"]
[Site "https://lichess.org/api_g1"]
[UTCDate "2026.11.10"]
[UTCTime "12:00:00"]
[White "alice"]
[Black "bob"]
[Result "1-0"]
[TimeControl "180+0"]

1. e4 { [%eval 0.2] } 1... e5 1-0
"""

SAMPLE_PGN_2 = """[Event "Rated rapid game"]
[Site "https://lichess.org/api_g2"]
[UTCDate "2026.11.11"]
[UTCTime "14:00:00"]
[White "bob"]
[Black "alice"]
[Result "0-1"]
[TimeControl "600+0"]

1. d4 1... d5 0-1
"""

FORK_PUZZLE = "GqnTb"


def poll_sync_done(client: TestClient, timeout: float = 5.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = client.get("/api/sync/status")
        assert res.status_code == 200
        data: dict[str, Any] = res.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.01)
    raise TimeoutError("Sync did not finish within timeout")


@pytest.fixture
def fake_source() -> FakeGameSource:
    source = FakeGameSource(existing_users={"alice_lichess", "bob_lichess"})
    source.add_pgn("alice_lichess", SAMPLE_PGN_1)
    source.add_pgn("alice_lichess", SAMPLE_PGN_2)
    return source


@pytest.fixture
def app_client(fake_source: FakeGameSource) -> Iterator[TestClient]:
    app = create_app(
        database_url="sqlite:///:memory:",
        puzzle_catalog=PUZZLE_SAMPLE,
        game_source=fake_source,
    )
    with TestClient(app) as client:
        yield client


def test_unauthenticated_cannot_access_accounts_or_sync(app_client: TestClient) -> None:
    assert app_client.get("/api/accounts").status_code == 401
    assert app_client.post("/api/accounts/lichess", json={"username": "alice"}).status_code == 401
    assert app_client.get("/api/sync/status").status_code == 401
    assert app_client.post("/api/sync/lichess").status_code == 401
    assert app_client.get("/api/games").status_code == 401


def test_link_account_nonexistent_user_returns_404(app_client: TestClient) -> None:
    register_new_player(app_client, "user@example.com")
    res = app_client.post("/api/accounts/lichess", json={"username": "khong_ton_tai_123"})
    assert res.status_code == 404
    assert "không tồn tại" in res.json()["detail"].lower()


def test_link_account_success_and_syncs_games(
    app_client: TestClient, fake_source: FakeGameSource
) -> None:
    register_new_player(app_client, "alice@example.com")

    res = app_client.post("/api/accounts/lichess", json={"username": "alice_lichess"})
    assert res.status_code in (200, 201), res.text
    data = res.json()
    assert data["account"]["username"] == "alice_lichess"
    assert data["job"]["status"] in ("pending", "running", "completed")

    # Đợi sync hoàn tất qua polling status
    st_data = poll_sync_done(app_client)
    assert st_data["status"] == "completed"
    assert st_data["new_games_count"] == 2

    # Kiểm tra danh sách tài khoản
    acc_res = app_client.get("/api/accounts")
    assert acc_res.status_code == 200
    accounts = acc_res.json()
    assert len(accounts) == 1
    assert accounts[0]["username"] == "alice_lichess"
    assert accounts[0]["games_count"] == 2

    # Kiểm tra danh sách ván qua /api/games
    games_res = app_client.get("/api/games")
    assert games_res.status_code == 200
    games_data = games_res.json()
    assert games_data["total"] == 2
    assert {g["platform_game_id"] for g in games_data["games"]} == {"api_g1", "api_g2"}


def test_data_isolation_between_players(app_client: TestClient) -> None:
    # Alice liên kết và đồng bộ ván
    register_new_player(app_client, "alice@example.com")
    app_client.post("/api/accounts/lichess", json={"username": "alice_lichess"})
    poll_sync_done(app_client)

    # Bob đăng ký tài khoản khác
    register_new_player(app_client, "bob@example.com")

    # Bob không thấy tài khoản hay ván cờ của Alice
    acc_res = app_client.get("/api/accounts")
    assert acc_res.status_code == 200
    assert len(acc_res.json()) == 0

    games_res = app_client.get("/api/games")
    assert games_res.status_code == 200
    assert games_res.json()["total"] == 0

    status_res = app_client.get("/api/sync/status")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "idle"


def test_update_sync_via_api_incremental_and_no_duplicates(
    app_client: TestClient, fake_source: FakeGameSource
) -> None:
    register_new_player(app_client, "alice@example.com")
    app_client.post("/api/accounts/lichess", json={"username": "alice_lichess"})
    poll_sync_done(app_client)

    # Lần 1: 2 ván
    assert app_client.get("/api/games").json()["total"] == 2

    # Gọi POST /api/sync/lichess khi chưa có ván mới -> không lưu trùng
    sync_res = app_client.post("/api/sync/lichess")
    assert sync_res.status_code == 200
    poll_sync_done(app_client)

    status = app_client.get("/api/sync/status").json()
    assert status["status"] == "completed"
    assert status["new_games_count"] == 0
    assert app_client.get("/api/games").json()["total"] == 2


def test_sync_does_not_block_puzzle_solving(app_client: TestClient) -> None:
    gate = threading.Event()

    class BlockingSource(FakeGameSource):
        def fetch_games(
            self,
            username: str,
            since: datetime | None = None,
            perf_types: tuple[str, ...] = ("blitz", "rapid", "classical"),
            max_games: int = 50,
        ) -> list[RawGame]:
            gate.wait(timeout=5.0)
            return super().fetch_games(username, since, perf_types, max_games)

    fastapi_app = cast(FastAPI, app_client.app)
    fastapi_app.state.game_source = BlockingSource(existing_users={"alice_lichess"})
    register_new_player(app_client, "alice@example.com")

    # Bắt đầu liên kết/đồng bộ (job sẽ bị treo tại fetch_games cho đến khi gate mở)
    app_client.post("/api/accounts/lichess", json={"username": "alice_lichess"})

    # Người chơi vẫn mở bài tập và đi nước giải bình thường
    attempt = start(app_client, FORK_PUZZLE)
    assert attempt["puzzle_id"] == FORK_PUZZLE
    res1 = play(app_client, attempt["attempt_id"], "d1a4")
    assert res1["verdict"] == "correct"

    # Mở gate cho sync kết thúc
    gate.set()
    poll_sync_done(app_client)


def test_offline_mode_serves_saved_games(
    app_client: TestClient, fake_source: FakeGameSource
) -> None:
    register_new_player(app_client, "alice@example.com")
    app_client.post("/api/accounts/lichess", json={"username": "alice_lichess"})
    poll_sync_done(app_client)

    # Đã có 2 ván lưu trong DB
    assert app_client.get("/api/games").json()["total"] == 2

    # Mất mạng (nguồn bên ngoài ngắt kết nối)
    fake_source.network_error = True

    # App chạy offline: tài khoản và ván đã lưu vẫn đọc bình thường từ DB cục bộ
    acc_res = app_client.get("/api/accounts")
    assert acc_res.status_code == 200
    assert acc_res.json()[0]["games_count"] == 2

    games_res = app_client.get("/api/games")
    assert games_res.status_code == 200
    assert games_res.json()["total"] == 2


