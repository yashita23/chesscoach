"""Điểm vào khi chạy local: `uvicorn chesscoach.main:app`."""

import os
from pathlib import Path

from dotenv import load_dotenv

from chesscoach.app import create_app

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"

load_dotenv(BACKEND_DIR / ".env")


def _database_url() -> str:
    url = os.environ.get("CHESSCOACH_DATABASE_URL")
    if url:
        return url
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(DATA_DIR / 'chesscoach.db').as_posix()}"


def _puzzle_catalog() -> Path:
    path = Path(os.environ.get("CHESSCOACH_PUZZLE_CATALOG", DATA_DIR / "puzzles.parquet"))
    return path if path.is_absolute() else BACKEND_DIR / path


app = create_app(
    database_url=_database_url(),
    puzzle_catalog=_puzzle_catalog(),
    calibration_min_attempts=int(os.environ.get("CHESSCOACH_CALIBRATION_MIN_ATTEMPTS", "200")),
)
