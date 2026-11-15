"""Phụ thuộc FastAPI dùng chung: kho bài tập và hiệu chỉnh xác suất của app."""

from typing import Annotated

from fastapi import Depends, Request

from chesscoach.ability_history import CalibrationCache
from chesscoach.puzzles import PuzzleCatalog


def get_catalog(request: Request) -> PuzzleCatalog:
    catalog: PuzzleCatalog = request.app.state.puzzle_catalog
    return catalog


Catalog = Annotated[PuzzleCatalog, Depends(get_catalog)]


def get_calibration_cache(request: Request) -> CalibrationCache:
    cache: CalibrationCache = request.app.state.calibration
    return cache


Calibration = Annotated[CalibrationCache, Depends(get_calibration_cache)]
