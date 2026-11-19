import chess
import pytest

from chesscoach.analysis.analyzer import GameAnalyzer, GameMistake
from chesscoach.analysis.engine import (
    CachedEngineAdapter,
    EngineAdapter,
    EngineEvaluation,
    EnrichedGameAnalyzer,
    FakeEngineAdapter,
)
from chesscoach.analysis.eval import Evaluation
from chesscoach.skills import MISSED_TACTIC

PGN_PARTIAL_EVALS = """[Event "Rated blitz game"]
[Site "https://lichess.org/partial1"]
[White "Alice"]
[Black "Bob"]
[Result "*"]

1. e4 { [%eval 0.25] } 1... e5 2. Nf3 { [%eval -3.00] } *
"""

PGN_FULL_EVALS_NO_MISTAKES = """[Event "Rated blitz game"]
[Site "https://lichess.org/full1"]
[White "Alice"]
[Black "Bob"]
[Result "*"]

1. e4 { [%eval 0.25] } 1... e5 { [%eval 0.30] } 2. Nf3 { [%eval 0.35] } *
"""

PGN_BLUNDER_FORK_TACTIC = """[Event "Rated blitz game"]
[Site "https://lichess.org/fork1"]
[White "Alice"]
[Black "Bob"]
[Result "0-1"]

1. e4 { [%eval 0.25] } 1... e5 { [%eval 0.30] } 2. d4 { [%eval -3.50] } 0-1
"""


class TestEngineProtocolAndFake:
    """Kiểm tra giao diện EngineAdapter và FakeEngineAdapter."""

    def test_fake_engine_adapter_protocol_conformance(self) -> None:
        def check_protocol(adapter: EngineAdapter) -> None:
            pass

        fake = FakeEngineAdapter()
        check_protocol(fake)


class TestEngineCache:
    """Kiểm tra cơ chế bộ nhớ đệm CachedEngineAdapter."""

    def test_cache_hit_same_fen_depth_and_time_limit(self) -> None:
        board = chess.Board()
        fake = FakeEngineAdapter(
            default_eval=EngineEvaluation(evaluation=Evaluation(cp=20), depth=10)
        )
        cached = CachedEngineAdapter(fake)

        res1 = cached.evaluate_position(board, depth=10, time_limit_seconds=0.5)
        res2 = cached.evaluate_position(board, depth=10, time_limit_seconds=0.5)

        assert res1 == res2
        assert fake.call_count == 1  # Lần 2 lấy từ cache

    def test_cache_miss_on_different_depth(self) -> None:
        board = chess.Board()
        fake = FakeEngineAdapter(
            default_eval=EngineEvaluation(evaluation=Evaluation(cp=20), depth=10)
        )
        cached = CachedEngineAdapter(fake)

        cached.evaluate_position(board, depth=10, time_limit_seconds=0.5)
        cached.evaluate_position(board, depth=12, time_limit_seconds=0.5)

        assert fake.call_count == 2

    def test_cache_miss_on_different_time_limit(self) -> None:
        board = chess.Board()
        fake = FakeEngineAdapter(
            default_eval=EngineEvaluation(evaluation=Evaluation(cp=20), depth=10)
        )
        cached = CachedEngineAdapter(fake)

        cached.evaluate_position(board, depth=10, time_limit_seconds=0.5)
        cached.evaluate_position(board, depth=10, time_limit_seconds=1.0)

        assert fake.call_count == 2

    def test_cache_miss_on_different_engine_version(self) -> None:
        board = chess.Board()
        fake = FakeEngineAdapter(
            default_eval=EngineEvaluation(evaluation=Evaluation(cp=20), depth=10)
        )
        cached_v1 = CachedEngineAdapter(fake, engine_version="1.0")
        cached_v2 = CachedEngineAdapter(fake, engine_version="2.0")

        cached_v1.evaluate_position(board, depth=10, time_limit_seconds=0.5)
        cached_v2.evaluate_position(board, depth=10, time_limit_seconds=0.5)

        assert fake.call_count == 2

    def test_engine_errors_and_timeouts_are_not_cached(self) -> None:
        board = chess.Board()
        fake = FakeEngineAdapter(failing_fens={board.fen()})
        cached = CachedEngineAdapter(fake)

        with pytest.raises(RuntimeError):
            cached.evaluate_position(board, depth=10, time_limit_seconds=0.5)

        assert fake.call_count == 1
        # Xóa FEN khỏi failing_fens: lần gọi tiếp theo phải thử lại chứ không trả lỗi cache
        fake.failing_fens.clear()
        fake.default_eval = EngineEvaluation(evaluation=Evaluation(cp=25), depth=10)

        res = cached.evaluate_position(board, depth=10, time_limit_seconds=0.5)
        assert res.evaluation == Evaluation(cp=25)
        assert fake.call_count == 2


class TestWhitePerspectiveConvention:
    """Kiểm tra quy ước evaluation luôn trả về theo White POV."""

    def test_engine_evaluation_in_white_pov_when_black_turn(self) -> None:
        # Bàn cờ tới lượt Đen đi, Đen đang thắng (-300 cp theo White POV)
        board = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
        fake = FakeEngineAdapter(
            default_eval=EngineEvaluation(
                evaluation=Evaluation(cp=-300),
                best_move=chess.Move.from_uci("g8f6"),
                depth=10,
            )
        )
        res = fake.evaluate_position(board, depth=10)
        assert res.evaluation.cp == -300  # Luôn giữ White POV


class TestEnrichedGameAnalyzer:
    """Kiểm tra EnrichedGameAnalyzer kết hợp PGN evals và EngineAdapter."""

    def test_analyzer_uses_engine_to_fill_missing_evals(self) -> None:
        # PGN_PARTIAL_EVALS thiếu eval ở ply 2 (1... e5).
        # Khi có engine: engine sẽ bổ sung eval cho ply 2, giúp phân tích được ply 3 (2. Nf3)
        board_ply2 = chess.Board()
        board_ply2.push_san("e4")
        board_ply2.push_san("e5")

        fake_engine = FakeEngineAdapter(
            evaluations={
                board_ply2.fen(): EngineEvaluation(evaluation=Evaluation(cp=30), depth=10)
            },
            default_eval=EngineEvaluation(evaluation=Evaluation(cp=0), depth=10),
        )
        analyzer = EnrichedGameAnalyzer(engine=fake_engine)
        mistakes = analyzer.analyze_game(201, PGN_PARTIAL_EVALS, "alice")

        # Nước 2. Nf3 giảm từ +30 cp xuống -300 cp -> phát hiện mistake!
        assert len(mistakes) == 1
        assert mistakes[0].ply == 3
        assert mistakes[0].move_san == "Nf3"

    def test_analyzer_does_not_call_engine_if_pgn_has_evals_and_no_mistake(self) -> None:
        # PGN_FULL_EVALS_NO_MISTAKES có đầy đủ eval và không có nước lỗi
        fake_engine = FakeEngineAdapter()
        analyzer = EnrichedGameAnalyzer(engine=fake_engine)
        mistakes = analyzer.analyze_game(202, PGN_FULL_EVALS_NO_MISTAKES, "alice")

        assert len(mistakes) == 0
        assert fake_engine.call_count == 0  # Không gọi engine lần nào!

    def test_analyzer_queries_best_and_refutation_moves_at_correct_positions(self) -> None:
        # Khi xảy ra nước lỗi (PGN_BLUNDER_FORK_TACTIC):
        # 1. Gọi engine tại board_before (trước nước 2. d4) -> lấy best_move
        # 2. Gọi engine tại board_after (sau nước 2. d4) -> lấy refutation_move (ví dụ fork)
        board_before = chess.Board()
        board_before.push_san("e4")
        board_before.push_san("e5")

        board_after = board_before.copy()
        board_after.push_san("d4")

        # Cấu hình fake engine trả best_move trên board_before và refutation_move trên board_after
        best_move_alice = chess.Move.from_uci("g1f3")  # Nf3
        refutation_bob = chess.Move.from_uci("e5d4")    # exd4

        fake_engine = FakeEngineAdapter(
            evaluations={
                board_before.fen(): EngineEvaluation(
                    evaluation=Evaluation(cp=30), best_move=best_move_alice, depth=10
                ),
                board_after.fen(): EngineEvaluation(
                    evaluation=Evaluation(cp=-350), best_move=refutation_bob, depth=10
                ),
            },
            default_eval=EngineEvaluation(evaluation=Evaluation(cp=0), depth=10),
        )

        analyzer = EnrichedGameAnalyzer(engine=fake_engine)
        mistakes = analyzer.analyze_game(203, PGN_BLUNDER_FORK_TACTIC, "alice")

        assert len(mistakes) == 1
        m = mistakes[0]
        assert m.best_move == "g1f3"
        assert m.refutation_move == "e5d4"

    def test_analyzer_without_engine_preserves_seam_3b_behavior(self) -> None:
        # Khi engine là None, hành vi của Seam 3B được bảo toàn hoàn toàn
        analyzer = EnrichedGameAnalyzer(engine=None)
        mistakes = analyzer.analyze_game(203, PGN_BLUNDER_FORK_TACTIC, "alice")

        assert len(mistakes) == 1
        m = mistakes[0]
        assert m.best_move is None
        assert m.refutation_move is None
        assert m.motif == "missedTactic"
        assert m.skill_id == MISSED_TACTIC
