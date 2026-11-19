import logging
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from chesscoach import ability_history, accounts, analysis_api, attempts, auth, practice, profile
from chesscoach.db import Base, add_missing_columns, make_engine
from chesscoach.games_source import GameSource, LichessAdapter
from chesscoach.games_sync import SyncEngine
from chesscoach.placement import PlacementSets
from chesscoach.puzzles import PuzzleCatalog
from chesscoach.recommend import DEFAULT_PRACTICE, PracticeConfig


log = logging.getLogger(__name__)


def create_app(
    database_url: str,
    puzzle_catalog: Path,
    calibration_min_attempts: int = 200,
    practice_config: PracticeConfig = DEFAULT_PRACTICE,
    placement_sets: Path | None = None,
    game_source: GameSource | None = None,
) -> FastAPI:
    """`calibration_min_attempts`: số lần giải đã có nhãn (toàn app) tối thiểu để bật hiệu chỉnh xác suất.
    `practice_config`: các λ và giới hạn của buổi luyện.
    `placement_sets`: file JSON bộ bài kiểm tra đầu vào (`placement_build`); None thì không có bài kiểm tra.
    `game_source`: nguồn ván trực tuyến (None thì dùng LichessAdapter mặc định).
    """
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    add_missing_columns(engine)

    app = FastAPI(title="Chess Coach")
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.puzzle_catalog = PuzzleCatalog(puzzle_catalog)
    app.state.practice_config = practice_config
    app.state.placement_sets = _load_placement(placement_sets, app.state.puzzle_catalog) if placement_sets else None
    app.state.calibration = ability_history.CalibrationCache(min_attempts=calibration_min_attempts)
    app.state.game_source = game_source or LichessAdapter()
    app.state.sync_engine = SyncEngine(app.state.session_factory)
    ability_history.backfill_attempt_snapshots(app.state.session_factory, app.state.puzzle_catalog)
    app.include_router(auth.auth_router)
    app.include_router(auth.player_router)
    app.include_router(attempts.router)
    app.include_router(profile.router)
    app.include_router(practice.router)
    app.include_router(accounts.router)
    app.include_router(analysis_api.router)
    return app


def _load_placement(path: Path, catalog: PuzzleCatalog) -> PlacementSets:
    sets = PlacementSets.load(path)
    kept = sets.restricted_to(catalog.existing_ids(sets.all_ids()))
    dropped = len(sets.all_ids()) - len(kept.all_ids())
    if dropped:
        log.warning("Bỏ %d bài tập của bài kiểm tra đầu vào không có trong kho bài tập %s", dropped, path)
    return kept
