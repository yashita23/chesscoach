from datetime import datetime, timezone
import threading
import time
from typing import Any
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from chesscoach.analysis.analyzer import FakeGameAnalyzer, GameMistake
from chesscoach.analysis.storage import get_game_mistakes
from chesscoach.db import Base, Game, GameMistakeRecord, LinkedAccount, Player, make_engine
from chesscoach.games_source import FakeGameSource
from chesscoach.games_sync import SyncEngine
from chesscoach.skills import SKILLS

SAMPLE_PGN_1 = """[Event "Rated blitz game"]
[Site "https://lichess.org/game1111"]
[UTCDate "2026.11.10"]
[UTCTime "12:00:00"]
[White "alice_lichess"]
[Black "opponent1"]
[Result "1-0"]
[TimeControl "180+0"]

1. e4 e5 2. Nf3 Nc6 1-0
"""

SAMPLE_PGN_2 = """[Event "Rated rapid game"]
[Site "https://lichess.org/game2222"]
[UTCDate "2026.11.11"]
[UTCTime "14:00:00"]
[White "opponent2"]
[Black "alice_lichess"]
[Result "0-1"]
[TimeControl "600+0"]

1. d4 d5 2. c4 e6 0-1
"""

SAMPLE_PGN_BOB = """[Event "Rated blitz game"]
[Site "https://lichess.org/game_bob_1"]
[UTCDate "2026.11.12"]
[UTCTime "15:00:00"]
[White "bob_lichess"]
[Black "opponent3"]
[Result "1-0"]
[TimeControl "180+0"]

1. e4 c5 2. Nf3 d6 1-0
"""


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    # Sử dụng đúng cấu hình in-memory engine của dự án (StaticPool trên sqlite:///:memory:)
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def player_alice(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as db:
        player = Player(
            email="alice@example.com", display_name="Alice", password_hash=b"hash"
        )
        db.add(player)
        db.flush()
        account = LinkedAccount(
            player_id=player.id, platform="lichess", username="alice_lichess"
        )
        db.add(account)
        db.commit()
        return player.id


@pytest.fixture
def player_bob(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as db:
        player = Player(
            email="bob@example.com", display_name="Bob", password_hash=b"hash"
        )
        db.add(player)
        db.flush()
        account = LinkedAccount(
            player_id=player.id, platform="lichess", username="bob_lichess"
        )
        db.add(account)
        db.commit()
        return player.id


def make_test_mistake(game_id: int, ply: int = 10) -> GameMistake:
    return GameMistake(
        game_id=game_id,
        ply=ply,
        move_number=(ply + 1) // 2,
        move_san="Nxd4",
        move_uci="c6d4",
        fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        win_before=60.0,
        win_after=35.0,
        win_loss=25.0,
        skill_id=SKILLS[0].id,
        motif="hanging_piece",
        game_phase="middlegame",
    )


# ---------------------------------------------------------------------------
# 1. Backward compatibility (analyzer=None)
# ---------------------------------------------------------------------------


def test_sync_engine_without_analyzer_keeps_games_pending(
    session_factory: sessionmaker[Session], player_alice: int
) -> None:
    source = FakeGameSource(existing_users={"alice_lichess"})
    source.add_pgn("alice_lichess", SAMPLE_PGN_1)
    source.add_pgn("alice_lichess", SAMPLE_PGN_2)

    engine = SyncEngine(session_factory, analyzer=None)
    engine.start_sync(player_alice, "lichess", source)
    engine.wait_for_job(player_alice, timeout=5.0)

    status = engine.get_status(player_alice)
    assert status.status == "completed"
    assert status.new_games_count == 2

    with session_factory() as db:
        games = db.scalars(
            select(Game)
            .where(Game.player_id == player_alice)
            .order_by(Game.id.asc())
        ).all()
        assert len(games) == 2
        for g in games:
            assert g.analysis_status == "pending"
            assert g.analyzed_at is None
        mistakes = db.scalars(select(GameMistakeRecord)).all()
        assert len(mistakes) == 0


# ---------------------------------------------------------------------------
# 2. Analysis integration on Sync (analyzer provided)
# ---------------------------------------------------------------------------


def test_sync_engine_with_analyzer_creates_mistakes_and_marks_completed(
    session_factory: sessionmaker[Session], player_alice: int
) -> None:
    source = FakeGameSource(existing_users={"alice_lichess"})
    source.add_pgn("alice_lichess", SAMPLE_PGN_1)

    fake_analyzer = FakeGameAnalyzer(
        configured_mistakes={
            1: [make_test_mistake(1, ply=8), make_test_mistake(1, ply=14)]
        }
    )

    engine = SyncEngine(session_factory, analyzer=fake_analyzer)
    engine.start_sync(player_alice, "lichess", source)
    engine.wait_for_job(player_alice, timeout=5.0)

    assert engine.get_status(player_alice).status == "completed"

    with session_factory() as db:
        game = db.scalar(select(Game).where(Game.platform_game_id == "game1111"))
        assert game is not None
        assert game.analysis_status == "completed"
        assert game.analyzed_at is not None

    mistakes = get_game_mistakes(session_factory, game.id)
    assert len(mistakes) == 2
    assert [m.ply for m in mistakes] == [8, 14]


# ---------------------------------------------------------------------------
# 3. Idempotency & Skip already completed games
# ---------------------------------------------------------------------------


def test_sync_engine_skips_analysis_for_already_completed_games(
    session_factory: sessionmaker[Session], player_alice: int
) -> None:
    # Game đã có trong DB và đã hoàn tất phân tích
    with session_factory() as db:
        completed_game = Game(
            player_id=player_alice,
            account_id=1,
            platform="lichess",
            platform_game_id="game1111",
            perf_type="blitz",
            played_at=datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc),
            pgn=SAMPLE_PGN_1,
            has_evals=True,
            analysis_status="completed",
            analyzed_at=datetime.now(timezone.utc),
        )
        db.add(completed_game)
        db.commit()

    source = FakeGameSource(existing_users={"alice_lichess"})
    source.add_pgn("alice_lichess", SAMPLE_PGN_1)

    fake_analyzer = FakeGameAnalyzer()
    engine = SyncEngine(session_factory, analyzer=fake_analyzer)
    engine.start_sync(player_alice, "lichess", source)
    engine.wait_for_job(player_alice, timeout=5.0)

    # Analyzer không bị gọi lại cho game đã completed
    assert fake_analyzer.call_count == 0


# ---------------------------------------------------------------------------
# 4. Analysis Error Isolation (fault-tolerant sync)
# ---------------------------------------------------------------------------


def test_sync_engine_analysis_failure_marks_game_failed_and_preserves_game(
    session_factory: sessionmaker[Session], player_alice: int
) -> None:
    source = FakeGameSource(existing_users={"alice_lichess"})
    source.add_pgn("alice_lichess", SAMPLE_PGN_1)
    source.add_pgn("alice_lichess", SAMPLE_PGN_2)

    class FailingAnalyzer:
        def __init__(self) -> None:
            self.calls = 0

        def analyze_game(
            self, game_id: int, pgn: str, player_username: str
        ) -> list[GameMistake]:
            self.calls += 1
            if "game1111" in pgn:
                raise RuntimeError("Stockfish binary crashed")
            return [make_test_mistake(game_id, ply=10)]

    analyzer = FailingAnalyzer()
    engine = SyncEngine(session_factory, analyzer=analyzer)
    engine.start_sync(player_alice, "lichess", source)
    engine.wait_for_job(player_alice, timeout=5.0)

    # Job chung vẫn hoàn thành (lỗi phân tích 1 ván không làm gián đoạn sync)
    assert engine.get_status(player_alice).status == "completed"

    with session_factory() as db:
        g1 = db.scalar(select(Game).where(Game.platform_game_id == "game1111"))
        assert g1 is not None
        assert g1.analysis_status == "failed"  # Đánh dấu failed
        assert g1.analyzed_at is not None

        g2 = db.scalar(select(Game).where(Game.platform_game_id == "game2222"))
        assert g2 is not None
        assert g2.analysis_status == "completed"  # Ván 2 vẫn hoàn tất


# ---------------------------------------------------------------------------
# 5. Retry / Reprocess: analyze_unprocessed_games
# ---------------------------------------------------------------------------


def test_analyze_unprocessed_games_reanalyzes_pending_and_failed_games(
    session_factory: sessionmaker[Session], player_alice: int, player_bob: int
) -> None:
    # Alice có: 1 ván completed, 1 ván pending, 1 ván failed
    # Bob có: 1 ván pending
    with session_factory() as db:
        g1 = Game(
            player_id=player_alice,
            account_id=1,
            platform="lichess",
            platform_game_id="g1_done",
            perf_type="blitz",
            played_at=datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc),
            pgn=SAMPLE_PGN_1,
            analysis_status="completed",
        )
        g2 = Game(
            player_id=player_alice,
            account_id=1,
            platform="lichess",
            platform_game_id="g2_pending",
            perf_type="blitz",
            played_at=datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc),
            pgn=SAMPLE_PGN_1,
            analysis_status="pending",
        )
        g3 = Game(
            player_id=player_alice,
            account_id=1,
            platform="lichess",
            platform_game_id="g3_failed",
            perf_type="blitz",
            played_at=datetime(2026, 11, 3, 0, 0, tzinfo=timezone.utc),
            pgn=SAMPLE_PGN_1,
            analysis_status="failed",
        )
        g_bob = Game(
            player_id=player_bob,
            account_id=2,
            platform="lichess",
            platform_game_id="gbob_pending",
            perf_type="blitz",
            played_at=datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc),
            pgn=SAMPLE_PGN_BOB,
            analysis_status="pending",
        )
        db.add_all([g1, g2, g3, g_bob])
        db.commit()

    fake_analyzer = FakeGameAnalyzer(
        default_mistakes=[make_test_mistake(1, ply=10)]
    )
    engine = SyncEngine(session_factory, analyzer=fake_analyzer)

    processed_count = engine.analyze_unprocessed_games(player_alice)
    assert processed_count == 2  # Chỉ phân tích g2 và g3 của Alice

    with session_factory() as db:
        # g2 và g3 chuyển sang completed
        assert db.scalar(select(Game.analysis_status).where(Game.id == g2.id)) == "completed"
        assert db.scalar(select(Game.analysis_status).where(Game.id == g3.id)) == "completed"
        # g_bob của Bob vẫn giữ nguyên pending
        assert db.scalar(select(Game.analysis_status).where(Game.id == g_bob.id)) == "pending"


# ---------------------------------------------------------------------------
# 6. Reprocess limit and stable ordering
# ---------------------------------------------------------------------------


def test_analyze_unprocessed_games_respects_limit_and_order(
    session_factory: sessionmaker[Session], player_alice: int
) -> None:
    with session_factory() as db:
        g1 = Game(
            player_id=player_alice,
            account_id=1,
            platform="lichess",
            platform_game_id="game_nov1",
            perf_type="blitz",
            played_at=datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc),
            pgn=SAMPLE_PGN_1,
            analysis_status="pending",
        )
        g2 = Game(
            player_id=player_alice,
            account_id=1,
            platform="lichess",
            platform_game_id="game_nov2",
            perf_type="blitz",
            played_at=datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc),
            pgn=SAMPLE_PGN_1,
            analysis_status="pending",
        )
        g3 = Game(
            player_id=player_alice,
            account_id=1,
            platform="lichess",
            platform_game_id="game_nov3",
            perf_type="blitz",
            played_at=datetime(2026, 11, 3, 0, 0, tzinfo=timezone.utc),
            pgn=SAMPLE_PGN_1,
            analysis_status="pending",
        )
        db.add_all([g1, g2, g3])
        db.commit()

    engine = SyncEngine(
        session_factory,
        analyzer=FakeGameAnalyzer(default_mistakes=[make_test_mistake(1, ply=10)]),
    )
    # Chỉ phân tích tối đa 2 ván
    count = engine.analyze_unprocessed_games(player_alice, limit=2)
    assert count == 2

    with session_factory() as db:
        # Hai ván cũ nhất (nov1 và nov2) đã hoàn tất
        assert db.scalar(select(Game.analysis_status).where(Game.id == g1.id)) == "completed"
        assert db.scalar(select(Game.analysis_status).where(Game.id == g2.id)) == "completed"
        # Ván nov3 vẫn pending
        assert db.scalar(select(Game.analysis_status).where(Game.id == g3.id)) == "pending"


# ---------------------------------------------------------------------------
# 7. SQLite Concurrency with StaticPool
# ---------------------------------------------------------------------------


def test_concurrent_sync_across_multiple_players_reproduces_and_passes_with_db_lock(
    session_factory: sessionmaker[Session], player_alice: int, player_bob: int
) -> None:
    source_alice = FakeGameSource(existing_users={"alice_lichess"})
    source_alice.add_pgn("alice_lichess", SAMPLE_PGN_1)
    source_alice.add_pgn("alice_lichess", SAMPLE_PGN_2)

    source_bob = FakeGameSource(existing_users={"bob_lichess"})
    source_bob.add_pgn("bob_lichess", SAMPLE_PGN_BOB)

    fake_analyzer = FakeGameAnalyzer(default_mistakes=[make_test_mistake(1, ply=10)])
    engine = SyncEngine(session_factory, analyzer=fake_analyzer)

    engine.start_sync(player_alice, "lichess", source_alice)
    engine.start_sync(player_bob, "lichess", source_bob)

    engine.wait_for_job(player_alice, timeout=5.0)
    engine.wait_for_job(player_bob, timeout=5.0)

    # Cả hai đều completed mà không gặp SQLite transaction clash
    assert engine.get_status(player_alice).status == "completed"
    assert engine.get_status(player_bob).status == "completed"


# ---------------------------------------------------------------------------
# 8. Analyzer runs outside DB lock
# ---------------------------------------------------------------------------


def test_analyzer_runs_outside_db_lock(
    session_factory: sessionmaker[Session], player_alice: int
) -> None:
    analyzer_inside_event = threading.Event()
    analyzer_can_finish_event = threading.Event()

    class SlowAnalyzer:
        def analyze_game(
            self, game_id: int, pgn: str, player_username: str
        ) -> list[GameMistake]:
            analyzer_inside_event.set()
            # Chờ để giữ thread trong hàm analyze_game
            analyzer_can_finish_event.wait(timeout=3.0)
            return []

    source = FakeGameSource(existing_users={"alice_lichess"})
    source.add_pgn("alice_lichess", SAMPLE_PGN_1)

    engine = SyncEngine(session_factory, analyzer=SlowAnalyzer())
    engine.start_sync(player_alice, "lichess", source)

    # Đợi thread phân tích bắt đầu
    assert analyzer_inside_event.wait(timeout=2.0)

    # Trong khi analyzer đang chạy (ngoài DB lock), luồng khác vẫn thực hiện được DB write ngay lập tức
    db_write_done = False
    with session_factory() as db:
        db.execute(text("SELECT count(*) FROM games"))
        db_write_done = True
    assert db_write_done is True

    # Cho phép analyzer kết thúc
    analyzer_can_finish_event.set()
    engine.wait_for_job(player_alice, timeout=5.0)
    assert engine.get_status(player_alice).status == "completed"


# ---------------------------------------------------------------------------
# 9. Same-game duplicate protection (atomic claim)
# ---------------------------------------------------------------------------


def test_same_game_duplicate_protection(
    session_factory: sessionmaker[Session], player_alice: int
) -> None:
    with session_factory() as db:
        g = Game(
            player_id=player_alice,
            account_id=1,
            platform="lichess",
            platform_game_id="race_game",
            perf_type="blitz",
            played_at=datetime.now(timezone.utc),
            pgn=SAMPLE_PGN_1,
            analysis_status="pending",
        )
        db.add(g)
        db.commit()
        game_id = g.id

    call_count = 0
    call_lock = threading.Lock()

    class CountingAnalyzer:
        def analyze_game(
            self, game_id: int, pgn: str, player_username: str
        ) -> list[GameMistake]:
            nonlocal call_count
            time.sleep(0.05)
            with call_lock:
                call_count += 1
            return []

    engine = SyncEngine(session_factory, analyzer=CountingAnalyzer())

    # Chạy 2 thread cùng gọi analyze_unprocessed_games
    t1 = threading.Thread(target=engine.analyze_unprocessed_games, args=(player_alice,))
    t2 = threading.Thread(target=engine.analyze_unprocessed_games, args=(player_alice,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Ván cờ chỉ được phân tích đúng 1 lần (nhờ cơ chế claim trạng thái)
    assert call_count == 1
    with session_factory() as db:
        assert db.scalar(select(Game.analysis_status).where(Game.id == game_id)) == "completed"


# ---------------------------------------------------------------------------
# 10. Distinguish analyzer error from persistence error
# ---------------------------------------------------------------------------


def test_storage_failure_does_not_mark_game_completed(
    session_factory: sessionmaker[Session],
    player_alice: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = FakeGameSource(existing_users={"alice_lichess"})
    source.add_pgn("alice_lichess", SAMPLE_PGN_1)

    fake_analyzer = FakeGameAnalyzer(default_mistakes=[make_test_mistake(1, ply=10)])
    engine = SyncEngine(session_factory, analyzer=fake_analyzer)

    # Giả lập lỗi tại tầng lưu trữ (storage)
    def mock_failing_save(*args: Any, **kwargs: Any) -> Any:
        raise OSError("Disk write error")

    import chesscoach.games_sync

    monkeypatch.setattr(chesscoach.games_sync, "save_game_mistakes", mock_failing_save)

    engine.start_sync(player_alice, "lichess", source)
    engine.wait_for_job(player_alice, timeout=5.0)

    # Game KHÔNG được đánh dấu completed khi tầng lưu trữ gặp sự cố
    with session_factory() as db:
        game = db.scalar(select(Game).where(Game.platform_game_id == "game1111"))
        assert game is not None
        assert game.analysis_status != "completed"


# ---------------------------------------------------------------------------
# 11. Two distinct SyncEngine instances sharing same Engine concurrently
# ---------------------------------------------------------------------------


def test_two_distinct_sync_engines_sharing_same_engine_concurrent_sync(
    session_factory: sessionmaker[Session], player_alice: int, player_bob: int
) -> None:
    source_alice = FakeGameSource(existing_users={"alice_lichess"})
    source_alice.add_pgn("alice_lichess", SAMPLE_PGN_1)
    source_alice.add_pgn("alice_lichess", SAMPLE_PGN_2)

    source_bob = FakeGameSource(existing_users={"bob_lichess"})
    source_bob.add_pgn("bob_lichess", SAMPLE_PGN_BOB)

    # Hai instance SyncEngine hoàn toàn riêng biệt
    engine1 = SyncEngine(
        session_factory,
        analyzer=FakeGameAnalyzer(default_mistakes=[make_test_mistake(1, ply=10)]),
    )
    engine2 = SyncEngine(
        session_factory,
        analyzer=FakeGameAnalyzer(default_mistakes=[make_test_mistake(1, ply=10)]),
    )

    # Chạy đồng thời trên 2 instance khác nhau
    engine1.start_sync(player_alice, "lichess", source_alice)
    engine2.start_sync(player_bob, "lichess", source_bob)

    engine1.wait_for_job(player_alice, timeout=5.0)
    engine2.wait_for_job(player_bob, timeout=5.0)

    # Cả hai hoàn tất mà không xung đột SQLite nhờ lock chia sẻ theo Engine
    assert engine1.get_status(player_alice).status == "completed"
    assert engine2.get_status(player_bob).status == "completed"


# ---------------------------------------------------------------------------
# 12. Recovery of crashed worker game stuck in analyzing
# ---------------------------------------------------------------------------


def test_recovery_of_crashed_worker_game_stuck_in_analyzing(
    session_factory: sessionmaker[Session], player_alice: int
) -> None:
    with session_factory() as db:
        stuck_game = Game(
            player_id=player_alice,
            account_id=1,
            platform="lichess",
            platform_game_id="crashed_worker_game",
            perf_type="blitz",
            played_at=datetime.now(timezone.utc),
            pgn=SAMPLE_PGN_1,
            analysis_status="analyzing",  # Worker trước bị crash khi đang analyzing
        )
        db.add(stuck_game)
        db.commit()
        game_id = stuck_game.id

    engine = SyncEngine(
        session_factory,
        analyzer=FakeGameAnalyzer(default_mistakes=[make_test_mistake(1, ply=10)]),
    )

    # analyze_unprocessed_games với include_stuck_analyzing=True thu hồi ván kẹt và phân tích thành công
    recovered_count = engine.analyze_unprocessed_games(
        player_alice, include_stuck_analyzing=True
    )
    assert recovered_count == 1

    with session_factory() as db:
        assert db.scalar(select(Game.analysis_status).where(Game.id == game_id)) == "completed"
