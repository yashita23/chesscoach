"""Phân tích ván cờ và nhận diện lỗi."""

from chesscoach.analysis.analyzer import (
    FakeGameAnalyzer,
    GameAnalyzer,
    GameMistake,
    PgnGameAnalyzer,
)
from chesscoach.analysis.engine import (
    CachedEngineAdapter,
    EnrichedGameAnalyzer,
    EngineAdapter,
    EngineEvaluation,
    FakeEngineAdapter,
)
from chesscoach.analysis.eval import (
    BlunderResult,
    Evaluation,
    MistakeResult,
    MoveEvaluation,
    detect_mistake,
    to_player_pov,
    win_chances,
)
from chesscoach.analysis.motifs import (
    GamePhase,
    MotifResult,
    MoveContext,
    classify_game_phase,
    detect_motif,
)
from chesscoach.analysis.parser import (
    ParsedMoveItem,
    RawParsedMove,
    parse_game_evaluations,
    parse_raw_game_moves,
)
from chesscoach.analysis.storage import (
    AnalysisValidationError,
    get_game_mistakes,
    mark_analysis_failed,
    save_game_mistakes,
)

__all__ = [
    "AnalysisValidationError",
    "BlunderResult",
    "CachedEngineAdapter",
    "EngineAdapter",
    "EngineEvaluation",
    "EnrichedGameAnalyzer",
    "Evaluation",
    "FakeEngineAdapter",
    "FakeGameAnalyzer",
    "GameAnalyzer",
    "GameMistake",
    "GamePhase",
    "MistakeResult",
    "MotifResult",
    "MoveContext",
    "MoveEvaluation",
    "ParsedMoveItem",
    "PgnGameAnalyzer",
    "RawParsedMove",
    "classify_game_phase",
    "detect_mistake",
    "detect_motif",
    "get_game_mistakes",
    "mark_analysis_failed",
    "parse_game_evaluations",
    "parse_raw_game_moves",
    "save_game_mistakes",
    "to_player_pov",
    "win_chances",
]
