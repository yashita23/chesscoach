"""Điểm vào khi chạy local: `uvicorn chesscoach.main:app`."""

import json
import os
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from chesscoach.app import create_app
from chesscoach.recommend import DEFAULT_PRACTICE, PracticeConfig

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


def _practice_config() -> PracticeConfig:
    """CHESSCOACH_PRACTICE_CONFIG: JSON ghi đè từng trường, ví dụ {"lambda_exploration": 0.2}."""
    raw = os.environ.get("CHESSCOACH_PRACTICE_CONFIG")
    return replace(DEFAULT_PRACTICE, **json.loads(raw)) if raw else DEFAULT_PRACTICE


app = create_app(
    database_url=_database_url(),
    puzzle_catalog=_puzzle_catalog(),
    calibration_min_attempts=int(os.environ.get("CHESSCOACH_CALIBRATION_MIN_ATTEMPTS", "200")),
    practice_config=_practice_config(),
    placement_sets=Path(os.environ.get("CHESSCOACH_PLACEMENT_SETS", Path(__file__).parent / "placement_sets.json")),
)
