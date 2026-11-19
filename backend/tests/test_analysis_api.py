from datetime import datetime, timezone
from typing import Any
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from chesscoach.analysis.analyzer import GameMistake
from chesscoach.analysis.storage import save_game_mistakes
from chesscoach.app import create_app
from chesscoach.db import Game, LinkedAccount, Player
from chesscoach.games_source import FakeGameSource
from chesscoach.skills import SKILLS
from helpers import PUZZLE_SAMPLE, register_new_player


SAMPLE_PGN = """[Event "Rated blitz game"]
[Site "https://lichess.org/game_test"]
[UTCDate "2026.11.10"]
[UTCTime "12:00:00"]
[White "alice"]
[Black "bob"]
[Result "1-0"]
[TimeControl "180+0"]

1. e4 e5 1-0
"""


@pytest.fixture
def fake_source() -> FakeGameSource:
    return FakeGameSource(existing_users={"alice_lichess", "bob_lichess"})


@pytest.fixture
def client(fake_source: FakeGameSource) -> TestClient:
    app = create_app(
        database_url="sqlite:///:memory:",
        puzzle_catalog=PUZZLE_SAMPLE,
        game_source=fake_source,
    )
    return TestClient(app)


def seed_player_and_game(
    session_factory: sessionmaker[Session],
    email: str,
    username: str,
    platform_game_id: str = "game_1",
    played_at: datetime | None = None,
    analysis_status: str = "pending",
    analyzed_at: datetime | None = None,
) -> tuple[int, int]:
    """Helper tạo sẵn Game trong DB."""
    if played_at is None:
        played_at = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    with session_factory() as db:
        player = db.scalar(select(Player).where(Player.email == email))
        if player is None:
            player = Player(
                email=email,
                display_name=email.split("@")[0].capitalize(),
                password_hash=b"fakehash",
            )
            db.add(player)
            db.flush()

        account = db.scalar(
            select(LinkedAccount).where(
                LinkedAccount.player_id == player.id,
                LinkedAccount.platform == "lichess",
            )
        )
        if account is None:
            account = LinkedAccount(
                player_id=player.id,
                platform="lichess",
                username=username,
            )
            db.add(account)
            db.flush()

        game = Game(
            player_id=player.id,
            account_id=account.id,
            platform="lichess",
            platform_game_id=platform_game_id,
            perf_type="blitz",
            played_at=played_at,
            pgn=SAMPLE_PGN,
            has_evals=True,
            analysis_status=analysis_status,
            analyzed_at=analyzed_at,
        )
        db.add(game)
        db.commit()
        return player.id, game.id


def make_mistake(
    game_id: int,
    ply: int,
    skill_id: str = SKILLS[0].id,
    game_phase: str = "middlegame",
    win_before: float = 65.0,
    win_after: float = 40.0,
    win_loss: float = 25.0,
    motif: str = "hanging_piece",
    best_move: str | None = "e2e4",
    refutation_move: str | None = "d7d5",
) -> GameMistake:
    return GameMistake(
        game_id=game_id,
        ply=ply,
        move_number=(ply + 1) // 2,
        move_san="Nxd4",
        move_uci="c6d4",
        fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        win_before=win_before,
        win_after=win_after,
        win_loss=win_loss,
        skill_id=skill_id,
        motif=motif,
        game_phase=game_phase,
        best_move=best_move,
        refutation_move=refutation_move,
    )


# Cần import select
from sqlalchemy import select


# ---------------------------------------------------------------------------
# 1. Authentication & Authorization (401 & 404)
# ---------------------------------------------------------------------------


def test_unauthenticated_cannot_access_analysis_api(client: TestClient) -> None:
    # Chưa đăng nhập phải nhận 401
    assert client.get("/api/games/1/analysis").status_code == 401
    assert client.get("/api/games/analysis/mistakes").status_code == 401


def test_get_game_analysis_nonexistent_returns_404(client: TestClient) -> None:
    register_new_player(client, "alice@example.com")
    res = client.get("/api/games/99999/analysis")
    assert res.status_code == 404
    assert "không tìm thấy" in res.json()["detail"].lower()


def test_get_game_analysis_other_player_returns_404(client: TestClient) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    register_new_player(client, "alice@example.com")
    alice_id, game_alice_id = seed_player_and_game(
        session_factory, "alice@example.com", "alice_lichess", "g_alice"
    )

    # Bob đăng nhập và cố truy cập ván của Alice
    register_new_player(client, "bob@example.com")
    res = client.get(f"/api/games/{game_alice_id}/analysis")
    # Phải trả về 404 (data isolation, không tiết lộ tài nguyên của Alice)
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# 2. Game Analysis Detail Endpoint: GET /api/games/{id}/analysis
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_val", ["pending", "analyzing", "failed"])
def test_get_game_analysis_non_completed_status(
    client: TestClient, status_val: str
) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    register_new_player(client, "alice@example.com")
    alice_id, game_id = seed_player_and_game(
        session_factory,
        "alice@example.com",
        "alice_lichess",
        f"g_{status_val}",
        analysis_status=status_val,
        analyzed_at=datetime.now(timezone.utc) if status_val == "failed" else None,
    )

    res = client.get(f"/api/games/{game_id}/analysis")
    assert res.status_code == 200
    data = res.json()
    assert data["game_id"] == game_id
    assert data["analysis_status"] == status_val
    assert data["mistakes"] == []  # Không có lỗi khi chưa completed


def test_get_game_analysis_completed_returns_mistakes_in_order(
    client: TestClient,
) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    register_new_player(client, "alice@example.com")
    alice_id, game_id = seed_player_and_game(
        session_factory,
        "alice@example.com",
        "alice_lichess",
        "g_completed",
        analysis_status="completed",
        analyzed_at=datetime.now(timezone.utc),
    )

    # Lưu 3 mistakes với thứ tự ply lộn xộn (14, 6, 20)
    mistakes = [
        make_mistake(game_id, ply=14, skill_id="fork", motif="fork"),
        make_mistake(game_id, ply=6, skill_id="hanging_piece", motif="hanging_piece"),
        make_mistake(game_id, ply=20, skill_id="pin", motif="pin"),
    ]
    save_game_mistakes(session_factory, game_id, alice_id, mistakes)

    res = client.get(f"/api/games/{game_id}/analysis")
    assert res.status_code == 200
    data = res.json()
    assert data["game_id"] == game_id
    assert data["platform"] == "lichess"
    assert data["platform_game_id"] == "g_completed"
    assert data["analysis_status"] == "completed"
    assert data["analyzed_at"] is not None

    # Danh sách mistakes phải sắp xếp tăng dần theo ply (6, 14, 20)
    assert len(data["mistakes"]) == 3
    assert [m["ply"] for m in data["mistakes"]] == [6, 14, 20]
    m0 = data["mistakes"][0]
    assert m0["ply"] == 6
    assert m0["move_san"] == "Nxd4"
    assert m0["win_loss"] == 25.0
    assert m0["skill_id"] == "hanging_piece"
    assert m0["best_move"] == "e2e4"
    assert m0["refutation_move"] == "d7d5"


def test_get_game_analysis_completed_with_no_mistakes(client: TestClient) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    register_new_player(client, "alice@example.com")
    alice_id, game_id = seed_player_and_game(
        session_factory,
        "alice@example.com",
        "alice_lichess",
        "g_perfect",
        analysis_status="completed",
        analyzed_at=datetime.now(timezone.utc),
    )
    # Lưu danh sách rỗng (ván không có lỗi)
    save_game_mistakes(session_factory, game_id, alice_id, [])

    res = client.get(f"/api/games/{game_id}/analysis")
    assert res.status_code == 200
    data = res.json()
    assert data["analysis_status"] == "completed"
    assert data["mistakes"] == []


# ---------------------------------------------------------------------------
# 3. Player Mistakes List Endpoint: GET /api/games/analysis/mistakes
# ---------------------------------------------------------------------------


def test_list_player_mistakes_returns_all_mistakes_for_current_player(
    client: TestClient,
) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    register_new_player(client, "alice@example.com")
    alice_id, g1 = seed_player_and_game(
        session_factory, "alice@example.com", "alice_lichess", "g1"
    )
    _, g2 = seed_player_and_game(
        session_factory, "alice@example.com", "alice_lichess", "g2"
    )

    save_game_mistakes(
        session_factory, g1, alice_id, [make_mistake(g1, ply=8), make_mistake(g1, ply=16)]
    )
    save_game_mistakes(
        session_factory, g2, alice_id, [make_mistake(g2, ply=10)]
    )

    res = client.get("/api/games/analysis/mistakes")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert len(data["mistakes"]) == 3


def test_list_player_mistakes_filter_by_skill_id(client: TestClient) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    register_new_player(client, "alice@example.com")
    alice_id, g1 = seed_player_and_game(
        session_factory, "alice@example.com", "alice_lichess", "g1"
    )

    save_game_mistakes(
        session_factory,
        g1,
        alice_id,
        [
            make_mistake(g1, ply=6, skill_id="fork"),
            make_mistake(g1, ply=12, skill_id="fork"),
            make_mistake(g1, ply=18, skill_id="pin"),
        ],
    )

    # Lọc skill_id=fork
    res = client.get("/api/games/analysis/mistakes?skill_id=fork")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["mistakes"]) == 2
    assert all(m["skill_id"] == "fork" for m in data["mistakes"])


def test_list_player_mistakes_filter_by_game_phase(client: TestClient) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    register_new_player(client, "alice@example.com")
    alice_id, g1 = seed_player_and_game(
        session_factory, "alice@example.com", "alice_lichess", "g1"
    )

    save_game_mistakes(
        session_factory,
        g1,
        alice_id,
        [
            make_mistake(g1, ply=6, game_phase="opening"),
            make_mistake(g1, ply=16, game_phase="middlegame"),
            make_mistake(g1, ply=40, game_phase="endgame"),
        ],
    )

    res = client.get("/api/games/analysis/mistakes?game_phase=opening")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["mistakes"][0]["game_phase"] == "opening"


def test_list_player_mistakes_filter_by_date_range(client: TestClient) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    register_new_player(client, "alice@example.com")
    alice_id, g1 = seed_player_and_game(
        session_factory,
        "alice@example.com",
        "alice_lichess",
        "g_early",
        played_at=datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc),
    )
    _, g2 = seed_player_and_game(
        session_factory,
        "alice@example.com",
        "alice_lichess",
        "g_mid",
        played_at=datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc),
    )
    _, g3 = seed_player_and_game(
        session_factory,
        "alice@example.com",
        "alice_lichess",
        "g_late",
        played_at=datetime(2026, 11, 28, 10, 0, tzinfo=timezone.utc),
    )

    save_game_mistakes(session_factory, g1, alice_id, [make_mistake(g1, ply=8)])
    save_game_mistakes(session_factory, g2, alice_id, [make_mistake(g2, ply=8)])
    save_game_mistakes(session_factory, g3, alice_id, [make_mistake(g3, ply=8)])

    # Lọc từ ngày 10 đến ngày 20
    res = client.get(
        "/api/games/analysis/mistakes?from_date=2026-11-10T00:00:00Z&to_date=2026-11-20T00:00:00Z"
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["mistakes"][0]["game_id"] == g2


def test_list_player_mistakes_order_by_win_loss_desc(client: TestClient) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    register_new_player(client, "alice@example.com")
    alice_id, g1 = seed_player_and_game(
        session_factory, "alice@example.com", "alice_lichess", "g1"
    )

    save_game_mistakes(
        session_factory,
        g1,
        alice_id,
        [
            make_mistake(g1, ply=6, win_before=60.0, win_after=40.0, win_loss=20.0),
            make_mistake(g1, ply=12, win_before=80.0, win_after=30.0, win_loss=50.0),
            make_mistake(g1, ply=18, win_before=70.0, win_after=35.0, win_loss=35.0),
        ],
    )

    res = client.get("/api/games/analysis/mistakes?order_by=win_loss_desc")
    assert res.status_code == 200
    data = res.json()
    assert [m["win_loss"] for m in data["mistakes"]] == [50.0, 35.0, 20.0]


def test_list_player_mistakes_stable_ordering(client: TestClient) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    register_new_player(client, "alice@example.com")
    alice_id, g1 = seed_player_and_game(
        session_factory, "alice@example.com", "alice_lichess", "g1"
    )

    # 2 mistakes có cùng win_loss
    save_game_mistakes(
        session_factory,
        g1,
        alice_id,
        [
            make_mistake(g1, ply=10, win_loss=25.0),
            make_mistake(g1, ply=20, win_loss=25.0),
        ],
    )

    res = client.get("/api/games/analysis/mistakes?order_by=win_loss_desc")
    assert res.status_code == 200
    data = res.json()
    # Tie-breaker id DESC đảm bảo thứ tự luôn cố định
    ids = [m["id"] for m in data["mistakes"]]
    assert ids[0] > ids[1]


def test_list_player_mistakes_pagination_and_total_count(client: TestClient) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    register_new_player(client, "alice@example.com")
    alice_id, g1 = seed_player_and_game(
        session_factory, "alice@example.com", "alice_lichess", "g1"
    )

    mistakes = [make_mistake(g1, ply=p * 2) for p in range(1, 6)]  # 5 mistakes
    save_game_mistakes(session_factory, g1, alice_id, mistakes)

    # limit=2, offset=2
    res = client.get("/api/games/analysis/mistakes?limit=2&offset=2")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 5  # Total phải là tổng sau filter, trước pagination
    assert len(data["mistakes"]) == 2


def test_list_player_mistakes_data_isolation(client: TestClient) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    register_new_player(client, "alice@example.com")
    alice_id, g_alice = seed_player_and_game(
        session_factory, "alice@example.com", "alice_lichess", "g_alice"
    )
    save_game_mistakes(
        session_factory, g_alice, alice_id, [make_mistake(g_alice, ply=10)]
    )

    # Tạo ván và mistake cho Bob
    bob_id, g_bob = seed_player_and_game(
        session_factory, "bob@example.com", "bob_lichess", "g_bob"
    )
    save_game_mistakes(
        session_factory, g_bob, bob_id, [make_mistake(g_bob, ply=12)]
    )

    # Alice đang đăng nhập
    res = client.get("/api/games/analysis/mistakes")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["mistakes"][0]["game_id"] == g_alice


# ---------------------------------------------------------------------------
# 4. Parameter Validations (422)
# ---------------------------------------------------------------------------


def test_list_player_mistakes_invalid_skill_id_returns_422(client: TestClient) -> None:
    register_new_player(client, "alice@example.com")
    res = client.get("/api/games/analysis/mistakes?skill_id=chua_biet_choi_co")
    assert res.status_code == 422


def test_list_player_mistakes_invalid_game_phase_returns_422(
    client: TestClient,
) -> None:
    register_new_player(client, "alice@example.com")
    res = client.get("/api/games/analysis/mistakes?game_phase=super_endgame")
    assert res.status_code == 422


@pytest.mark.parametrize(
    "query_param",
    [
        "limit=0",
        "limit=-5",
        "limit=101",
        "offset=-1",
    ],
)
def test_list_player_mistakes_invalid_pagination_returns_422(
    client: TestClient, query_param: str
) -> None:
    register_new_player(client, "alice@example.com")
    res = client.get(f"/api/games/analysis/mistakes?{query_param}")
    assert res.status_code == 422


def test_list_player_mistakes_from_date_after_to_date_returns_422(
    client: TestClient,
) -> None:
    register_new_player(client, "alice@example.com")
    res = client.get(
        "/api/games/analysis/mistakes?from_date=2026-11-20T00:00:00Z&to_date=2026-11-01T00:00:00Z"
    )
    assert res.status_code == 422


def test_analysis_api_does_not_trigger_analyzer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    register_new_player(client, "alice@example.com")
    alice_id, game_id = seed_player_and_game(
        session_factory,
        "alice@example.com",
        "alice_lichess",
        "g1",
        analysis_status="completed",
    )

    analyzer_called = False

    def mock_analyze(*args: Any, **kwargs: Any) -> Any:
        nonlocal analyzer_called
        analyzer_called = True
        raise AssertionError("REST API tuyệt đối không được gọi GameAnalyzer!")

    # Monkeypatch analyze_game trong analyzer
    import chesscoach.analysis.analyzer

    monkeypatch.setattr(
        chesscoach.analysis.analyzer.PgnGameAnalyzer, "analyze_game", mock_analyze
    )

    # Gọi API
    res1 = client.get(f"/api/games/{game_id}/analysis")
    res2 = client.get("/api/games/analysis/mistakes")

    assert analyzer_called is False
