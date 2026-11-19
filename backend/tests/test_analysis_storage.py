from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from chesscoach.analysis.analyzer import GameMistake
from chesscoach.analysis.storage import (
    AnalysisValidationError,
    get_game_mistakes,
    mark_analysis_failed,
    save_game_mistakes,
)
from chesscoach.db import (
    Base,
    Game,
    GameMistakeRecord,
    LinkedAccount,
    Player,
    add_missing_columns,
)
from chesscoach.skills import SKILLS


VALID_SKILL_ID = SKILLS[0].id  # "hanging_piece"


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def seeded_game(session_factory: sessionmaker[Session]) -> tuple[int, int]:
    """Tạo sẵn Player (id=1) và Game (id=1) để phục vụ test."""
    with session_factory() as session:
        player = Player(
            email="player1@example.com",
            display_name="Player 1",
            password_hash=b"fakehash",
        )
        session.add(player)
        session.flush()

        account = LinkedAccount(
            player_id=player.id,
            platform="lichess",
            username="player1_lichess",
        )
        session.add(account)
        session.flush()

        game = Game(
            player_id=player.id,
            account_id=account.id,
            platform="lichess",
            platform_game_id="game_123",
            perf_type="blitz",
            played_at=datetime.now(timezone.utc),
            pgn='[Event "Rated blitz game"]\n1. e4 e5 2. Nf3 1-0',
            has_evals=True,
        )
        session.add(game)
        session.commit()
        return player.id, game.id


def make_dummy_mistake(
    game_id: int,
    ply: int = 10,
    skill_id: str = VALID_SKILL_ID,
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


# ---------------------------------------------------------------------------
# 1. Model tests
# ---------------------------------------------------------------------------


def test_model_creates_mistake_record(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, game_id = seeded_game
    with session_factory() as session:
        record = GameMistakeRecord(
            game_id=game_id,
            player_id=player_id,
            ply=10,
            move_number=5,
            move_san="Nxd4",
            move_uci="c6d4",
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            win_before=70.0,
            win_after=45.0,
            win_loss=25.0,
            skill_id=VALID_SKILL_ID,
            motif="hanging_piece",
            game_phase="middlegame",
            best_move="e2e4",
            refutation_move="d7d5",
        )
        session.add(record)
        session.commit()

        loaded = session.scalar(
            select(GameMistakeRecord).where(GameMistakeRecord.game_id == game_id)
        )
        assert loaded is not None
        assert loaded.player_id == player_id
        assert loaded.ply == 10
        assert loaded.move_number == 5
        assert loaded.move_san == "Nxd4"
        assert loaded.move_uci == "c6d4"
        assert loaded.skill_id == VALID_SKILL_ID
        assert loaded.win_loss == 25.0
        assert loaded.created_at is not None


def test_model_foreign_key_cascade_on_game_delete(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, game_id = seeded_game
    with session_factory() as session:
        session.execute(text("PRAGMA foreign_keys = ON"))
        session.add(
            GameMistakeRecord(
                game_id=game_id,
                player_id=player_id,
                ply=10,
                move_number=5,
                move_san="Nxd4",
                move_uci="c6d4",
                fen="fen_str",
                win_before=60.0,
                win_after=35.0,
                win_loss=25.0,
                skill_id=VALID_SKILL_ID,
                motif="hanging_piece",
                game_phase="middlegame",
            )
        )
        session.commit()

        # Xóa game
        game = session.get(Game, game_id)
        assert game is not None
        session.delete(game)
        session.commit()

        # Cascade xóa mistakes
        mistakes = session.scalars(
            select(GameMistakeRecord).where(GameMistakeRecord.game_id == game_id)
        ).all()
        assert len(mistakes) == 0


def test_model_unique_constraint_game_ply(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, game_id = seeded_game
    with session_factory() as session:
        rec1 = GameMistakeRecord(
            game_id=game_id,
            player_id=player_id,
            ply=10,
            move_number=5,
            move_san="Nxd4",
            move_uci="c6d4",
            fen="fen_1",
            win_before=60.0,
            win_after=35.0,
            win_loss=25.0,
            skill_id=VALID_SKILL_ID,
            motif="hanging_piece",
            game_phase="middlegame",
        )
        rec2 = GameMistakeRecord(
            game_id=game_id,
            player_id=player_id,
            ply=10,  # Trùng ply trong cùng 1 game
            move_number=5,
            move_san="Bxf7",
            move_uci="c4f7",
            fen="fen_2",
            win_before=55.0,
            win_after=30.0,
            win_loss=25.0,
            skill_id=VALID_SKILL_ID,
            motif="fork",
            game_phase="middlegame",
        )
        session.add(rec1)
        session.commit()

        session.add(rec2)
        with pytest.raises(Exception):  # IntegrityError
            session.commit()


# ---------------------------------------------------------------------------
# 2. Persistence & Retrieve
# ---------------------------------------------------------------------------


def test_save_and_retrieve_multiple_mistakes(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, game_id = seeded_game
    mistakes = [
        make_dummy_mistake(game_id, ply=14),
        make_dummy_mistake(game_id, ply=8),
        make_dummy_mistake(game_id, ply=22),
    ]

    save_game_mistakes(session_factory, game_id, player_id, mistakes)

    loaded = get_game_mistakes(session_factory, game_id)
    assert len(loaded) == 3
    # Sắp xếp tăng dần theo ply
    assert [m.ply for m in loaded] == [8, 14, 22]
    assert all(m.player_id == player_id for m in loaded)
    assert all(m.game_id == game_id for m in loaded)


# ---------------------------------------------------------------------------
# 3. Idempotency
# ---------------------------------------------------------------------------


def test_save_game_mistakes_idempotent(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, game_id = seeded_game
    mistakes = [
        make_dummy_mistake(game_id, ply=10),
        make_dummy_mistake(game_id, ply=16),
    ]

    # Lưu lần 1
    save_game_mistakes(session_factory, game_id, player_id, mistakes)
    assert len(get_game_mistakes(session_factory, game_id)) == 2

    # Lưu lại lần 2 (cùng dữ liệu)
    save_game_mistakes(session_factory, game_id, player_id, mistakes)
    loaded = get_game_mistakes(session_factory, game_id)
    assert len(loaded) == 2
    assert [m.ply for m in loaded] == [10, 16]


# ---------------------------------------------------------------------------
# 4. Transactional Replace
# ---------------------------------------------------------------------------


def test_save_game_mistakes_replaces_old_mistakes(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, game_id = seeded_game
    old_mistakes = [
        make_dummy_mistake(game_id, ply=6),
        make_dummy_mistake(game_id, ply=12),
        make_dummy_mistake(game_id, ply=18),
    ]
    save_game_mistakes(session_factory, game_id, player_id, old_mistakes)
    assert len(get_game_mistakes(session_factory, game_id)) == 3

    # Phân tích lại với kết quả mới (ví dụ chỉ còn 1 mistake ở ply 24)
    new_mistakes = [
        make_dummy_mistake(game_id, ply=24, skill_id="fork"),
    ]
    save_game_mistakes(session_factory, game_id, player_id, new_mistakes)

    loaded = get_game_mistakes(session_factory, game_id)
    assert len(loaded) == 1
    assert loaded[0].ply == 24
    assert loaded[0].skill_id == "fork"


# ---------------------------------------------------------------------------
# 5. Empty result handling
# ---------------------------------------------------------------------------


def test_save_empty_mistakes_marks_completed(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, game_id = seeded_game
    # Ban đầu ván có 1 lỗi
    save_game_mistakes(
        session_factory, game_id, player_id, [make_dummy_mistake(game_id, ply=10)]
    )
    assert len(get_game_mistakes(session_factory, game_id)) == 1

    # Lưu danh sách rỗng (ván không có lỗi nào)
    save_game_mistakes(session_factory, game_id, player_id, [])

    loaded = get_game_mistakes(session_factory, game_id)
    assert len(loaded) == 0

    with session_factory() as session:
        game = session.get(Game, game_id)
        assert game is not None
        assert game.analysis_status == "completed"
        assert game.analyzed_at is not None


# ---------------------------------------------------------------------------
# 6. Atomicity & Rollback
# ---------------------------------------------------------------------------


def test_atomicity_rollback_preserves_old_mistakes_on_failure(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, game_id = seeded_game
    old_mistakes = [
        make_dummy_mistake(game_id, ply=10),
        make_dummy_mistake(game_id, ply=20),
    ]
    save_game_mistakes(session_factory, game_id, player_id, old_mistakes)
    assert len(get_game_mistakes(session_factory, game_id)) == 2

    # Chuẩn bị danh sách mới nhưng có 2 phần tử trùng ply -> gây IntegrityError khi insert
    duplicate_ply_mistakes = [
        make_dummy_mistake(game_id, ply=15),
        make_dummy_mistake(game_id, ply=15),  # Trùng ply vi phạm UniqueConstraint
    ]

    with pytest.raises(Exception):
        save_game_mistakes(session_factory, game_id, player_id, duplicate_ply_mistakes)

    # Dữ liệu cũ phải còn nguyên vẹn 100% nhờ rollback
    loaded = get_game_mistakes(session_factory, game_id)
    assert len(loaded) == 2
    assert [m.ply for m in loaded] == [10, 20]


# ---------------------------------------------------------------------------
# 7. Status updates & Mark Failed
# ---------------------------------------------------------------------------


def test_analysis_status_and_analyzed_at_updated_on_success(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, game_id = seeded_game
    with session_factory() as session:
        game = session.get(Game, game_id)
        assert game is not None
        assert game.analysis_status == "pending"
        assert game.analyzed_at is None

    save_game_mistakes(
        session_factory, game_id, player_id, [make_dummy_mistake(game_id, ply=8)]
    )

    with session_factory() as session:
        game = session.get(Game, game_id)
        assert game is not None
        assert game.analysis_status == "completed"
        assert game.analyzed_at is not None


def test_mark_analysis_failed_updates_status(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, game_id = seeded_game
    mark_analysis_failed(session_factory, game_id, error="Stockfish timeout")

    with session_factory() as session:
        game = session.get(Game, game_id)
        assert game is not None
        assert game.analysis_status == "failed"
        assert game.analyzed_at is not None


# ---------------------------------------------------------------------------
# 8. Backward Migration
# ---------------------------------------------------------------------------


def test_backward_migration_adds_missing_columns() -> None:
    # Tạo engine với bảng games kiểu cũ (thiếu analysis_status và analyzed_at)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
            CREATE TABLE players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(320) UNIQUE NOT NULL,
                display_name VARCHAR(100) NOT NULL,
                daily_minutes INTEGER,
                claimed_rating INTEGER,
                placement_band INTEGER,
                password_hash BLOB NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
            )
        )
        conn.execute(
            text(
                """
            CREATE TABLE linked_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                platform VARCHAR(32) NOT NULL,
                username VARCHAR(100) NOT NULL,
                last_synced_at DATETIME,
                last_game_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
            )
        )
        conn.execute(
            text(
                """
            CREATE TABLE games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                platform VARCHAR(32) NOT NULL,
                platform_game_id VARCHAR(64) NOT NULL,
                perf_type VARCHAR(32) NOT NULL,
                played_at DATETIME NOT NULL,
                pgn TEXT NOT NULL,
                has_evals BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
            )
        )
        # Chèn 1 ván mẫu trong schema cũ
        conn.execute(
            text(
                """
            INSERT INTO games (player_id, account_id, platform, platform_game_id, perf_type, played_at, pgn)
            VALUES (1, 1, 'lichess', 'old_g1', 'blitz', '2026-11-10 12:00:00', '1. e4')
        """
            )
        )

    # Chạy migration add_missing_columns
    add_missing_columns(engine)

    # Kiểm tra cột mới đã được thêm và giá trị mặc định của hàng cũ là pending
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, analysis_status, analyzed_at FROM games WHERE id = 1")
        ).fetchone()
        assert row is not None
        assert row[1] == "pending"
        assert row[2] is None

    # Chạy lại lần 2 để kiểm tra tính idempotent
    add_missing_columns(engine)


# ---------------------------------------------------------------------------
# 9. Validation tests
# ---------------------------------------------------------------------------


def test_validation_rejects_nonexistent_game(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, _ = seeded_game
    mistake = make_dummy_mistake(game_id=99999, ply=10)

    with pytest.raises(AnalysisValidationError, match="không tồn tại"):
        save_game_mistakes(session_factory, 99999, player_id, [mistake])


def test_validation_rejects_player_mismatch(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    _, game_id = seeded_game
    # Player 999 không sở hữu ván cờ này
    mistake = make_dummy_mistake(game_id=game_id, ply=10)

    with pytest.raises(AnalysisValidationError, match="không khớp"):
        save_game_mistakes(session_factory, game_id, 999, [mistake])


def test_validation_rejects_invalid_skill_id(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, game_id = seeded_game
    mistake = make_dummy_mistake(game_id=game_id, ply=10, skill_id="chua_biet_choi_co")

    with pytest.raises(AnalysisValidationError, match="skill_id"):
        save_game_mistakes(session_factory, game_id, player_id, [mistake])


def test_validation_rejects_invalid_game_phase(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, game_id = seeded_game
    mistake = make_dummy_mistake(game_id=game_id, ply=10, game_phase="late_game")

    with pytest.raises(AnalysisValidationError, match="game_phase"):
        save_game_mistakes(session_factory, game_id, player_id, [mistake])


@pytest.mark.parametrize(
    "ply,win_before,win_after,win_loss",
    [
        (0, 60.0, 35.0, 25.0),  # ply < 1
        (-1, 60.0, 35.0, 25.0),  # ply âm
        (10, -5.0, 35.0, -40.0),  # win_before < 0
        (10, 105.0, 35.0, 70.0),  # win_before > 100
        (10, 60.0, -1.0, 61.0),  # win_after < 0
        (10, 60.0, 101.0, -41.0),  # win_after > 100
    ],
)
def test_validation_rejects_invalid_probabilities_and_ply(
    session_factory: sessionmaker[Session],
    seeded_game: tuple[int, int],
    ply: int,
    win_before: float,
    win_after: float,
    win_loss: float,
) -> None:
    player_id, game_id = seeded_game
    mistake = make_dummy_mistake(
        game_id=game_id,
        ply=ply,
        win_before=win_before,
        win_after=win_after,
        win_loss=win_loss,
    )
    with pytest.raises(AnalysisValidationError):
        save_game_mistakes(session_factory, game_id, player_id, [mistake])


def test_validation_rejects_inconsistent_win_loss(
    session_factory: sessionmaker[Session], seeded_game: tuple[int, int]
) -> None:
    player_id, game_id = seeded_game
    # win_before=60, win_after=35 -> win_loss đúng phải là 25, nhưng truyền 30
    mistake = make_dummy_mistake(
        game_id=game_id,
        ply=10,
        win_before=60.0,
        win_after=35.0,
        win_loss=30.0,
    )
    with pytest.raises(AnalysisValidationError, match="win_loss"):
        save_game_mistakes(session_factory, game_id, player_id, [mistake])
