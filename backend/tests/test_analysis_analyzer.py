import pytest

from chesscoach.analysis.analyzer import (
    FakeGameAnalyzer,
    GameAnalyzer,
    GameMistake,
    PgnGameAnalyzer,
)
from chesscoach.skills import MISSED_TACTIC

PGN_WHITE_BLUNDER = """[Event "Rated blitz game"]
[Site "https://lichess.org/g1"]
[White "Alice"]
[Black "Bob"]
[Result "0-1"]

1. e4 { [%eval 0.25] [%clk 0:03:00] } 1... e5 { [%eval 0.30] [%clk 0:02:55] } 2. Qh5 { [%eval -3.00] [%clk 0:02:50] } 2... Nf6 { [%eval -2.90] [%clk 0:02:40] } 0-1
"""

PGN_WHITE_DROP_UNDER_20 = """[Event "Rated blitz game"]
[Site "https://lichess.org/g2"]
[White "Alice"]
[Black "Bob"]
[Result "*"]

1. e4 { [%eval 0.25] [%clk 0:03:00] } 1... e5 { [%eval 0.30] [%clk 0:02:55] } 2. Nf3 { [%eval -0.40] [%clk 0:02:50] } *
"""

PGN_CLOCK_UNDER_10S = """[Event "Rated blitz game"]
[Site "https://lichess.org/g3"]
[White "Alice"]
[Black "Bob"]
[Result "0-1"]

1. e4 { [%eval 0.25] [%clk 0:03:00] } 1... e5 { [%eval 0.30] [%clk 0:02:55] } 2. Qh5 { [%eval -3.00] [%clk 0:00:08] } 0-1
"""

PGN_BLACK_BLUNDER = """[Event "Rated rapid game"]
[Site "https://lichess.org/g4"]
[White "Charlie"]
[Black "Alice"]
[Result "1-0"]

1. e4 { [%eval 0.25] [%clk 0:10:00] } 1... f6 { [%eval 3.50] [%clk 0:09:50] } 1-0
"""

PGN_OPPONENT_BLUNDER = """[Event "Rated blitz game"]
[Site "https://lichess.org/g5"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 { [%eval 0.25] [%clk 0:03:00] } 1... f6 { [%eval 3.50] [%clk 0:02:55] } 2. d4 { [%eval 3.40] [%clk 0:02:50] } 1-0
"""

PGN_NO_EVALS = """[Event "Rated blitz game"]
[Site "https://lichess.org/g6"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 1... e5 2. Nf3 1-0
"""


class TestAnalyzerProtocol:
    """Kiểm tra sự tuân thủ giao diện GameAnalyzer."""

    def test_analyzer_protocol_conformance(self) -> None:
        def check_analyzer(analyzer: GameAnalyzer) -> None:
            pass

        check_analyzer(PgnGameAnalyzer())
        check_analyzer(FakeGameAnalyzer())


class TestPgnGameAnalyzerPipeline:
    """Kiểm tra luồng phân tích ván cờ với PgnGameAnalyzer."""

    def test_pipeline_detects_mistake_when_win_loss_ge_20(self) -> None:
        analyzer = PgnGameAnalyzer()
        mistakes = analyzer.analyze_game(101, PGN_WHITE_BLUNDER, "alice")
        assert len(mistakes) == 1
        m = mistakes[0]
        assert m.game_id == 101
        assert m.ply == 3
        assert m.move_number == 2
        assert m.move_san == "Qh5"
        assert m.move_uci == "d1h5"
        assert m.win_loss >= 20.0
        assert m.win_before > m.win_after

    def test_pipeline_ignores_drop_under_20(self) -> None:
        analyzer = PgnGameAnalyzer()
        mistakes = analyzer.analyze_game(102, PGN_WHITE_DROP_UNDER_20, "alice")
        assert len(mistakes) == 0

    def test_pipeline_filters_out_clock_under_10s(self) -> None:
        analyzer = PgnGameAnalyzer()
        mistakes = analyzer.analyze_game(103, PGN_CLOCK_UNDER_10S, "alice")
        # Nước 2. Qh5 mất > 20% win rate nhưng clock 8s -> lọc bỏ
        assert len(mistakes) == 0

    def test_pipeline_handles_black_player_perspective(self) -> None:
        analyzer = PgnGameAnalyzer()
        # Alice cầm Đen đi 1... f6? làm win rate của Đen giảm mạnh
        mistakes = analyzer.analyze_game(104, PGN_BLACK_BLUNDER, "alice")
        assert len(mistakes) == 1
        m = mistakes[0]
        assert m.ply == 2
        assert m.move_number == 1
        assert m.move_san == "f6"
        assert m.win_loss >= 20.0
        # Xác nhận win_before và win_after đều được tính theo Player POV (Black POV)
        assert m.win_before > m.win_after
        assert m.win_before < 50.0  # Đen hơi bị ép nhẹ sau 1. e4 (~47.7%)
        assert m.win_after < 30.0   # Đen thua sâu sau 1... f6 (~21.5%)
        assert m.win_loss == pytest.approx(m.win_before - m.win_after, abs=0.01)

    def test_pipeline_skips_opponent_blunders(self) -> None:
        analyzer = PgnGameAnalyzer()
        # Alice cầm Trắng, Bob đi 1... f6? biếu cờ -> Alice không bị tính lỗi
        mistakes = analyzer.analyze_game(105, PGN_OPPONENT_BLUNDER, "alice")
        assert len(mistakes) == 0

    def test_pipeline_fallback_to_missed_tactic_when_no_best_move(self) -> None:
        analyzer = PgnGameAnalyzer()
        mistakes = analyzer.analyze_game(101, PGN_WHITE_BLUNDER, "alice")
        assert len(mistakes) == 1
        m = mistakes[0]
        # PgnGameAnalyzer không tự suy diễn best_move, truyền None -> fallback missed_tactic
        assert m.motif == "missedTactic"
        assert m.skill_id == MISSED_TACTIC
        assert m.best_move is None
        assert m.refutation_move is None

    def test_pipeline_game_phase_evaluated_on_board_before(self) -> None:
        analyzer = PgnGameAnalyzer()
        mistakes = analyzer.analyze_game(101, PGN_WHITE_BLUNDER, "alice")
        assert len(mistakes) == 1
        # Nước 2. Qh5 ở đầu ván (fullmove 2, material đầy đủ) -> "opening"
        assert mistakes[0].game_phase == "opening"

    def test_pipeline_metadata_san_uci_fen_ply_move_number(self) -> None:
        analyzer = PgnGameAnalyzer()
        mistakes = analyzer.analyze_game(101, PGN_WHITE_BLUNDER, "alice")
        assert len(mistakes) == 1
        m = mistakes[0]
        assert m.ply == 3
        assert m.move_number == 2
        assert m.move_san == "Qh5"
        assert m.move_uci == "d1h5"
        assert "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR" in m.fen

    def test_game_with_no_mistakes_returns_empty_list(self) -> None:
        analyzer = PgnGameAnalyzer()
        # Ván không có nước nào giảm >= 20%
        mistakes = analyzer.analyze_game(102, PGN_WHITE_DROP_UNDER_20, "alice")
        assert mistakes == []

    def test_pgn_without_evals_returns_empty_list(self) -> None:
        analyzer = PgnGameAnalyzer()
        # PGN không có comment eval
        mistakes = analyzer.analyze_game(106, PGN_NO_EVALS, "alice")
        assert mistakes == []

    def test_player_username_not_in_headers_raises_value_error(self) -> None:
        analyzer = PgnGameAnalyzer()
        with pytest.raises(ValueError, match="headers"):
            analyzer.analyze_game(101, PGN_WHITE_BLUNDER, "charlie")


class TestFakeGameAnalyzer:
    """Kiểm tra hoạt động của test double FakeGameAnalyzer."""

    def test_fake_analyzer_returns_configured_mistakes(self) -> None:
        fake_mistake = GameMistake(
            game_id=999,
            ply=5,
            move_number=3,
            move_san="Bc4",
            move_uci="f1c4",
            fen="test_fen",
            win_before=60.0,
            win_after=25.0,
            win_loss=35.0,
            skill_id="fork",
            motif="fork",
            game_phase="opening",
        )
        fake_analyzer = FakeGameAnalyzer(configured_mistakes={999: [fake_mistake]})
        results = fake_analyzer.analyze_game(999, "dummy_pgn", "alice")
        assert len(results) == 1
        assert results[0] == fake_mistake

        # Game không được cấu hình trả về []
        assert fake_analyzer.analyze_game(888, "dummy_pgn", "alice") == []

    def test_fake_analyzer_simulates_failure_for_game_id(self) -> None:
        fake_analyzer = FakeGameAnalyzer(failing_game_ids={555})
        with pytest.raises(RuntimeError, match="555"):
            fake_analyzer.analyze_game(555, "dummy_pgn", "alice")
