"""Phụ thuộc FastAPI dùng chung: kho bài tập, hiệu chỉnh xác suất và cấu hình buổi luyện của app."""

from typing import Annotated

from fastapi import Depends, Request

from chesscoach.ability_history import CalibrationCache
from chesscoach.placement import PlacementSets
from chesscoach.puzzles import PuzzleCatalog
from chesscoach.recommend import PracticeConfig


def get_catalog(request: Request) -> PuzzleCatalog:
    catalog: PuzzleCatalog = request.app.state.puzzle_catalog
    return catalog


Catalog = Annotated[PuzzleCatalog, Depends(get_catalog)]


def get_calibration_cache(request: Request) -> CalibrationCache:
    cache: CalibrationCache = request.app.state.calibration
    return cache


Calibration = Annotated[CalibrationCache, Depends(get_calibration_cache)]


def get_practice_config(request: Request) -> PracticeConfig:
    config: PracticeConfig = request.app.state.practice_config
    return config


Practice = Annotated[PracticeConfig, Depends(get_practice_config)]


def get_placement_sets(request: Request) -> PlacementSets | None:
    sets: PlacementSets | None = request.app.state.placement_sets
    return sets


Placement = Annotated[PlacementSets | None, Depends(get_placement_sets)]
