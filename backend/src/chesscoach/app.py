from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from chesscoach import ability_history, attempts, auth, practice, profile
from chesscoach.db import Base, add_missing_columns, make_engine
from chesscoach.puzzles import PuzzleCatalog
from chesscoach.recommend import DEFAULT_PRACTICE, PracticeConfig


def create_app(
    database_url: str,
    puzzle_catalog: Path,
    calibration_min_attempts: int = 200,
    practice_config: PracticeConfig = DEFAULT_PRACTICE,
) -> FastAPI:
    """`calibration_min_attempts`: số lần giải đã có nhãn (toàn app) tối thiểu để bật hiệu chỉnh xác suất.
    `practice_config`: các λ và giới hạn của buổi luyện.
    """
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    add_missing_columns(engine)

    app = FastAPI(title="Chess Coach")
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.puzzle_catalog = PuzzleCatalog(puzzle_catalog)
    app.state.practice_config = practice_config
    app.state.calibration = ability_history.CalibrationCache(min_attempts=calibration_min_attempts)
    ability_history.backfill_attempt_snapshots(app.state.session_factory, app.state.puzzle_catalog)
    app.include_router(auth.auth_router)
    app.include_router(auth.player_router)
    app.include_router(attempts.router)
    app.include_router(profile.router)
    app.include_router(practice.router)
    return app
