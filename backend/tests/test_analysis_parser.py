import chess
import chess.pgn
import pytest

from chesscoach.analysis.eval import Evaluation
from chesscoach.analysis.parser import (
    NEUTRAL_BASELINE_EVAL,
    ParsedMoveItem,
    extract_player_color,
    parse_clock_string,
    parse_eval_string,
    parse_game_evaluations,
)

SAMPLE_PGN_WHITE = """[Event "Rated blitz game"]
[Site "https://lichess.org/test1"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 { [%eval 0.25] [%clk 0:02:55] } 1... e5 { [%eval 0.30] [%clk 0:02:50] } 2. Nf3 { [%eval 0.40] [%clk 0:02:45] } 2... Nc6 { [%eval 0.35] [%clk 0:02:40] } 1-0
"""

SAMPLE_PGN_BLACK = """[Event "Rated rapid game"]
[Site "https://lichess.org/test2"]
[White "Charlie"]
[Black "Alice"]
[Result "0-1"]

1. d4 { [%eval 0.20] [%clk 0:10:00] } 1... d5 { [%eval 0.15] [%clk 0:09:50] } 2. c4 { [%eval 0.25] [%clk 0:09:40] } 2... e6 { [%eval 0.10] [%clk 0:09:35] } 0-1
"""

SAMPLE_PGN_MISSING_EVALS = """[Event "Rated blitz game"]
[Site "https://lichess.org/test3"]
[White "Alice"]
[Black "Bob"]
[Result "*"]

1. e4 { [%eval 0.25] } 1... e5 2. Nf3 { [%eval 0.40] } 2... Nc6 { [%eval 0.35] } *
"""

SAMPLE_PGN_MATE = """[Event "Rated blitz game"]
[Site "https://lichess.org/test4"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]

1. e4 { [%eval 0.2] } 1... e5 { [%eval 0.3] } 2. Qh5 { [%eval #2] } 1-0
"""


class TestEvalStringParsing:
    """Kiểm tra hàm parse_eval_string."""

    def test_parse_centipawns_positive_and_negative(self) -> None:
        assert parse_eval_string("0.0") == Evaluation(cp=0, mate=None)
        assert parse_eval_string("0.2") == Evaluation(cp=20, mate=None)
        assert parse_eval_string("0.25") == Evaluation(cp=25, mate=None)
        assert parse_eval_string("-1.55") == Evaluation(cp=-155, mate=None)
        assert parse_eval_string("+3.2") == Evaluation(cp=320, mate=None)

    def test_parse_mate_positive_and_negative(self) -> None:
        assert parse_eval_string("#3") == Evaluation(cp=None, mate=3)
        assert parse_eval_string("#-2") == Evaluation(cp=None, mate=-2)
        assert parse_eval_string("#+1") == Evaluation(cp=None, mate=1)


class TestClockStringParsing:
    """Kiểm tra hàm parse_clock_string."""

    def test_parse_clock_formats(self) -> None:
        assert parse_clock_string("0:02:45") == 165.0
        assert parse_clock_string("0:00:08") == 8.0
        assert parse_clock_string("1:00:00") == 3600.0
        assert parse_clock_string("0:00:09.9") == 9.9
        assert parse_clock_string("08") == 8.0
        assert parse_clock_string("") is None


class TestPlayerIdentification:
    """Kiểm tra hàm extract_player_color."""

    def test_extract_player_color_white_case_insensitive(self) -> None:
        headers = chess.pgn.Headers()
        headers["White"] = "Alice"
        headers["Black"] = "Bob"
        assert extract_player_color(headers, "alice") == chess.WHITE
        assert extract_player_color(headers, "ALICE") == chess.WHITE

    def test_extract_player_color_black_case_insensitive(self) -> None:
        headers = chess.pgn.Headers()
        headers["White"] = "Alice"
        headers["Black"] = "Bob"
        assert extract_player_color(headers, "bob") == chess.BLACK
        assert extract_player_color(headers, "BOB") == chess.BLACK

    def test_player_username_not_in_game_headers_raises_value_error(self) -> None:
        headers = chess.pgn.Headers()
        headers["White"] = "Alice"
        headers["Black"] = "Bob"
        with pytest.raises(ValueError, match="headers"):
            extract_player_color(headers, "charlie")


class TestGameEvaluationsParsing:
    """Kiểm tra hàm parse_game_evaluations."""

    def test_initial_position_uses_neutral_baseline(self) -> None:
        # Nước đầu tiên của Trắng (ply 1, 1. e4) phải dùng NEUTRAL_BASELINE_EVAL (cp=0, mate=None)
        items = parse_game_evaluations(SAMPLE_PGN_WHITE, "alice")
        assert len(items) >= 1
        first_move = items[0]
        assert first_move.ply == 1
        assert first_move.move_number == 1
        assert first_move.san == "e4"
        assert first_move.evaluation.before == NEUTRAL_BASELINE_EVAL
        assert first_move.evaluation.before.cp == 0
        assert first_move.evaluation.after == Evaluation(cp=25)

    def test_clock_is_attached_to_correct_player_move(self) -> None:
        items = parse_game_evaluations(SAMPLE_PGN_WHITE, "alice")
        # Alice đi ply 1 (1. e4 [%clk 0:02:55]) và ply 3 (2. Nf3 [%clk 0:02:45])
        assert len(items) == 2
        assert items[0].evaluation.clock_seconds == 175.0
        assert items[1].evaluation.clock_seconds == 165.0

    def test_skips_opponent_moves(self) -> None:
        # Alice cầm Đen trong SAMPLE_PGN_BLACK, chỉ rút trích plies 2 (1... d5) và 4 (2... e6)
        items = parse_game_evaluations(SAMPLE_PGN_BLACK, "alice")
        assert len(items) == 2
        assert items[0].ply == 2
        assert items[0].san == "d5"
        assert items[1].ply == 4
        assert items[1].san == "e6"
        # Eval before của ply 2 là eval của ply 1 (1. d4 [%eval 0.20])
        assert items[0].evaluation.before == Evaluation(cp=20)
        assert items[0].evaluation.after == Evaluation(cp=15)

    def test_missing_before_eval_skips_move(self) -> None:
        # Trong SAMPLE_PGN_MISSING_EVALS:
        # ply 1 (1. e4 [%eval 0.25]): before=cp 0, after=cp 25 -> hợp lệ
        # ply 2 (1... e5): không có eval
        # ply 3 (2. Nf3 [%eval 0.40]): before là ply 2 (thiếu eval!) -> phải bỏ qua ply 3!
        items = parse_game_evaluations(SAMPLE_PGN_MISSING_EVALS, "alice")
        assert len(items) == 1
        assert items[0].ply == 1
        # ply 3 không được tạo vì thiếu before eval

    def test_missing_after_eval_skips_move(self) -> None:
        pgn = """[White "Alice"]
[Black "Bob"]

1. e4 1... e5 1-0
"""
        items = parse_game_evaluations(pgn, "alice")
        # Nước 1. e4 không có eval -> bỏ qua
        assert len(items) == 0

    def test_mate_eval_parsed_correctly_in_game(self) -> None:
        items = parse_game_evaluations(SAMPLE_PGN_MATE, "alice")
        assert len(items) == 2
        assert items[1].san == "Qh5"
        assert items[1].evaluation.after == Evaluation(mate=2)

    def test_missing_clock_returns_none(self) -> None:
        pgn = """[White "Alice"]
[Black "Bob"]

1. e4 { [%eval 0.2] } 1... e5 { [%eval 0.3] } 1-0
"""
        items = parse_game_evaluations(pgn, "alice")
        assert len(items) == 1
        assert items[0].evaluation.clock_seconds is None

    def test_invalid_clock_string_returns_none(self) -> None:
        assert parse_clock_string("invalid:clock:text") is None
        assert parse_clock_string("abc") is None

    def test_board_before_is_correct(self) -> None:
        items = parse_game_evaluations(SAMPLE_PGN_WHITE, "alice")
        # Nước 1. e4: board_before là vị trí ban đầu (starting board)
        assert items[0].board_before.fen() == chess.Board().fen()
        # Nước 2. Nf3: board_before là sau 1. e4 e5
        expected_board = chess.Board()
        expected_board.push_san("e4")
        expected_board.push_san("e5")
        assert items[1].board_before.fen() == expected_board.fen()

    def test_ply_and_move_number_are_correct(self) -> None:
        items = parse_game_evaluations(SAMPLE_PGN_WHITE, "alice")
        # Alice đi ply 1 (move 1) và ply 3 (move 2)
        assert items[0].ply == 1
        assert items[0].move_number == 1
        assert items[1].ply == 3
        assert items[1].move_number == 2

    def test_ambiguous_username_match_raises_value_error(self) -> None:
        headers = chess.pgn.Headers()
        headers["White"] = "Alice"
        headers["Black"] = "Alice"
        with pytest.raises(ValueError, match="trùng với cả hai bên"):
            extract_player_color(headers, "alice")
