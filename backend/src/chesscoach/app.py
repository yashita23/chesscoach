from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from chesscoach import attempts, auth, profile
from chesscoach.db import Base, add_missing_columns, make_engine
from chesscoach.puzzles import PuzzleCatalog


def create_app(database_url: str, puzzle_catalog: Path) -> FastAPI:
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    add_missing_columns(engine)

    app = FastAPI(title="Chess Coach")
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.puzzle_catalog = PuzzleCatalog(puzzle_catalog)
    profile.backfill_attempt_snapshots(app.state.session_factory, app.state.puzzle_catalog)
    app.include_router(auth.auth_router)
    app.include_router(auth.player_router)
    app.include_router(attempts.router)
    app.include_router(profile.router)
    return app
