from datetime import datetime, timezone
import time
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from chesscoach.db import Base, Game, LinkedAccount, Player, make_engine
from chesscoach.games_source import FakeGameSource, RateLimitError, RawGame
from chesscoach.games_sync import AlreadySyncingError, SyncEngine, SyncJob

SAMPLE_PGN_1 = """[Event "Rated blitz game"]
[Site "https://lichess.org/game1111"]
[UTCDate "2026.11.10"]
[UTCTime "12:00:00"]
[White "alice"]
[Black "bob"]
[Result "1-0"]
[TimeControl "180+0"]

1. e4 { [%eval 0.2] } 1... e5 1-0
"""

SAMPLE_PGN_2 = """[Event "Rated rapid game"]
[Site "https://lichess.org/game2222"]
[UTCDate "2026.11.11"]
[UTCTime "14:00:00"]
[White "bob"]
[Black "alice"]
[Result "0-1"]
[TimeControl "600+0"]

1. d4 1... d5 0-1
"""

SAMPLE_PGN_3 = """[Event "Rated blitz game"]
[Site "https://lichess.org/game3333"]
[UTCDate "2026.11.12"]
[UTCTime "16:00:00"]
[White "alice"]
[Black "carol"]
[Result "1-0"]
[TimeControl "180+2"]

1. c4 1... c5 1-0
"""


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def player_alice(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as db:
        player = Player(email="alice@example.com", display_name="Alice", password_hash=b"hash")
        db.add(player)
        db.commit()
        account = LinkedAccount(player_id=player.id, platform="lichess", username="alice_lichess")
        db.add(account)
        db.commit()
        return player.id


@pytest.fixture
def player_bob(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as db:
        player = Player(email="bob@example.com", display_name="Bob", password_hash=b"hash")
        db.add(player)
        db.commit()
        account = LinkedAccount(player_id=player.id, platform="lichess", username="bob_lichess")
        db.add(account)
        db.commit()
        return player.id


def test_sync_job_lifecycle_success(session_factory: sessionmaker[Session], player_alice: int) -> None:
    source = FakeGameSource(existing_users={"alice_lichess"})
    source.add_pgn("alice_lichess", SAMPLE_PGN_1)
    source.add_pgn("alice_lichess", SAMPLE_PGN_2)

    engine = SyncEngine(session_factory)
    job = engine.start_sync(player_alice, "lichess", source)
    engine.wait_for_job(player_alice, timeout=5.0)

    status = engine.get_status(player_alice)
    assert status.status == "completed"
    assert status.current == 2
    assert status.total == 2
    assert status.new_games_count == 2
    assert status.error is None

    # Kiểm tra ván và thời điểm cập nhật trong DB
    with session_factory() as db:
        games = db.scalars(select(Game).where(Game.player_id == player_alice)).all()
        assert len(games) == 2
        game_ids = {g.platform_game_id for g in games}
        assert game_ids == {"game1111", "game2222"}

        account = db.scalars(
            select(LinkedAccount).where(
                LinkedAccount.player_id == player_alice, LinkedAccount.platform == "lichess"
            )
        ).one()
        assert account.last_synced_at is not None
        assert account.last_game_at is not None
        assert account.last_game_at.replace(tzinfo=timezone.utc) == datetime(
            2026, 11, 11, 14, 0, tzinfo=timezone.utc
        )


def test_sync_idempotent_no_duplicate_games(session_factory: sessionmaker[Session], player_alice: int) -> None:
    source = FakeGameSource(existing_users={"alice_lichess"})
    source.add_pgn("alice_lichess", SAMPLE_PGN_1)

    engine = SyncEngine(session_factory)
    # Lần 1: lưu 1 ván
    engine.start_sync(player_alice, "lichess", source)
    engine.wait_for_job(player_alice, timeout=5.0)

    # Lần 2: chạy lại với cùng nguồn
    engine.start_sync(player_alice, "lichess", source)
    engine.wait_for_job(player_alice, timeout=5.0)

    status = engine.get_status(player_alice)
    assert status.status == "completed"
    assert status.new_games_count == 0

    with session_factory() as db:
        games = db.scalars(select(Game).where(Game.player_id == player_alice)).all()
        assert len(games) == 1


def test_incremental_sync_uses_last_game_at(session_factory: sessionmaker[Session], player_alice: int) -> None:
    source = FakeGameSource(existing_users={"alice_lichess"})
    source.add_pgn("alice_lichess", SAMPLE_PGN_1)  # 2026-11-10

    engine = SyncEngine(session_factory)
    engine.start_sync(player_alice, "lichess", source)
    engine.wait_for_job(player_alice, timeout=5.0)

    # Thêm ván mới ngày 12
    source.add_pgn("alice_lichess", SAMPLE_PGN_3)  # 2026-11-12

    # Đồng bộ lần 2: incremental sync
    engine.start_sync(player_alice, "lichess", source)
    engine.wait_for_job(player_alice, timeout=5.0)

    status = engine.get_status(player_alice)
    assert status.status == "completed"
    assert status.new_games_count == 1

    with session_factory() as db:
        games = db.scalars(select(Game).where(Game.player_id == player_alice)).all()
        assert len(games) == 2
        account = db.scalars(
            select(LinkedAccount).where(
                LinkedAccount.player_id == player_alice, LinkedAccount.platform == "lichess"
            )
        ).one()
        assert account.last_game_at is not None
        assert account.last_game_at.replace(tzinfo=timezone.utc) == datetime(
            2026, 11, 12, 16, 0, tzinfo=timezone.utc
        )


def test_two_concurrent_sync_requests_for_same_player(
    session_factory: sessionmaker[Session], player_alice: int
) -> None:
    import threading

    gate = threading.Event()

    class BlockingSource(FakeGameSource):
        def fetch_games(self, *args: object, **kwargs: object) -> list[RawGame]:
            gate.wait(timeout=5.0)
            return super().fetch_games(*args, **kwargs)  # type: ignore[arg-type]

    source = BlockingSource(existing_users={"alice_lichess"})
    source.add_pgn("alice_lichess", SAMPLE_PGN_1)

    engine = SyncEngine(session_factory)
    job1 = engine.start_sync(player_alice, "lichess", source)

    try:
        with pytest.raises(AlreadySyncingError):
            engine.start_sync(player_alice, "lichess", source)
    finally:
        gate.set()
        engine.wait_for_job(player_alice, timeout=5.0)


def test_two_different_players_can_sync_concurrently(
    session_factory: sessionmaker[Session], player_alice: int, player_bob: int
) -> None:
    source_alice = FakeGameSource(existing_users={"alice_lichess"})
    source_alice.add_pgn("alice_lichess", SAMPLE_PGN_1)

    source_bob = FakeGameSource(existing_users={"bob_lichess"})
    source_bob.add_pgn("bob_lichess", SAMPLE_PGN_2)

    engine = SyncEngine(session_factory)
    engine.start_sync(player_alice, "lichess", source_alice)
    engine.start_sync(player_bob, "lichess", source_bob)

    engine.wait_for_job(player_alice, timeout=5.0)
    engine.wait_for_job(player_bob, timeout=5.0)

    assert engine.get_status(player_alice).status == "completed"
    assert engine.get_status(player_bob).status == "completed"


def test_sync_partial_failure_preserves_saved_games(
    session_factory: sessionmaker[Session], player_alice: int
) -> None:
    # Nguồn có lỗi mạng khi gọi fetch_games
    source = FakeGameSource(existing_users={"alice_lichess"}, network_error=True)

    # Đã có sẵn 1 ván trước đó
    with session_factory() as db:
        db.add(
            Game(
                player_id=player_alice,
                account_id=1,
                platform="lichess",
                platform_game_id="existing_game",
                perf_type="blitz",
                played_at=datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc),
                pgn="existing pgn",
                has_evals=False,
            )
        )
        db.commit()

    engine = SyncEngine(session_factory)
    engine.start_sync(player_alice, "lichess", source)
    engine.wait_for_job(player_alice, timeout=5.0)

    status = engine.get_status(player_alice)
    assert status.status == "failed"
    assert "mạng" in (status.error or "").lower()

    # Ván đã có không bị mất, last_synced_at không bị cập nhật
    with session_factory() as db:
        games = db.scalars(select(Game).where(Game.player_id == player_alice)).all()
        assert len(games) == 1
        account = db.scalars(
            select(LinkedAccount).where(
                LinkedAccount.player_id == player_alice, LinkedAccount.platform == "lichess"
            )
        ).one()
        assert account.last_synced_at is None


def test_sync_retry_on_429(session_factory: sessionmaker[Session], player_alice: int) -> None:
    class FlakyRateLimitedSource(FakeGameSource):
        def __init__(self) -> None:
            super().__init__(existing_users={"alice_lichess"})
            self.add_pgn("alice_lichess", SAMPLE_PGN_1)
            self.attempts = 0

        def fetch_games(self, *args: object, **kwargs: object) -> list[RawGame]:
            self.attempts += 1
            if self.attempts == 1:
                raise RateLimitError("HTTP 429")
            return super().fetch_games(*args, **kwargs)  # type: ignore[arg-type]

    source = FlakyRateLimitedSource()
    engine = SyncEngine(session_factory, max_retries=2, retry_delay_sec=0.01)
    engine.start_sync(player_alice, "lichess", source)
    engine.wait_for_job(player_alice, timeout=5.0)

    status = engine.get_status(player_alice)
    assert status.status == "completed"
    assert status.new_games_count == 1

