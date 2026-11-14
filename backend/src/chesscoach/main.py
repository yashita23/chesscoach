"""Điểm vào khi chạy local: `uvicorn chesscoach.main:app`."""

import os
from pathlib import Path

from chesscoach.app import create_app

_DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "chesscoach.db"


def _database_url() -> str:
    url = os.environ.get("CHESSCOACH_DATABASE_URL")
    if url:
        return url
    _DEFAULT_DB.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{_DEFAULT_DB.as_posix()}"


app = create_app(database_url=_database_url())
