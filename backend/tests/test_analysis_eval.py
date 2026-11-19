import math
import chess
import pytest

from chesscoach.analysis.eval import (
    BlunderResult,
    Evaluation,
    MistakeResult,
    MoveEvaluation,
    detect_blunder,
    detect_mistake,
    to_player_pov,
    win_chances,
)


class TestWinChances:
    """Nhóm A — Win% conversion từ centipawns và mate."""

    def test_cp_zero_is_fifty_percent(self) -> None:
        assert win_chances(Evaluation(cp=0)) == pytest.approx(50.0, abs=0.01)

    def test_cp_plus_200_is_around_67_point_6_percent(self) -> None:
        # W(200) = 100 / (1 + exp(-0.00368208 * 200)) = 67.61...
        expected = 100.0 / (1.0 + math.exp(-0.00368208 * 200))
        assert win_chances(Evaluation(cp=200)) == pytest.approx(expected, abs=0.05)

    def test_cp_minus_200_is_around_32_point_4_percent(self) -> None:
        # W(-200) = 100 / (1 + exp(-0.00368208 * -200)) = 32.38...
        expected = 100.0 / (1.0 + math.exp(-0.00368208 * -200))
        assert win_chances(Evaluation(cp=-200)) == pytest.approx(expected, abs=0.05)

    def test_positive_mate_is_one_hundred_percent(self) -> None:
        assert win_chances(Evaluation(mate=1)) == 100.0
        assert win_chances(Evaluation(mate=5)) == 100.0

    def test_negative_mate_is_zero_percent(self) -> None:
        assert win_chances(Evaluation(mate=-1)) == 0.0
        assert win_chances(Evaluation(mate=-3)) == 0.0

    def test_numerical_stability_with_large_values(self) -> None:
        # Tránh OverflowError khi cp rất lớn
        assert win_chances(Evaluation(cp=100_000)) == pytest.approx(100.0, abs=0.01)
        assert win_chances(Evaluation(cp=-100_000)) == pytest.approx(0.0, abs=0.01)


class TestPlayerPerspective:
    """Nhóm B — Player perspective normalization (to_player_pov)."""

    def test_white_perspective_remains_unchanged(self) -> None:
        score = Evaluation(cp=250)
        assert to_player_pov(score, chess.WHITE) == Evaluation(cp=250)

        score_mate = Evaluation(mate=2)
        assert to_player_pov(score_mate, chess.WHITE) == Evaluation(mate=2)

    def test_black_perspective_inverts_sign(self) -> None:
        # White POV: -300 (White is losing) -> Black POV: +300 (Black is winning)
        score = Evaluation(cp=-300)
        assert to_player_pov(score, chess.BLACK) == Evaluation(cp=300)

        # White POV: +200 -> Black POV: -200
        score2 = Evaluation(cp=200)
        assert to_player_pov(score2, chess.BLACK) == Evaluation(cp=-200)

        # White POV: mate -1 (White being mated) -> Black POV: mate 1
        score_mate = Evaluation(mate=-1)
        assert to_player_pov(score_mate, chess.BLACK) == Evaluation(mate=1)

    def test_none_fields_are_preserved(self) -> None:
        assert to_player_pov(Evaluation(cp=None, mate=None), chess.BLACK) == Evaluation(cp=None, mate=None)


class TestBlunderThreshold:
    """Nhóm C — Blunder / Mistake detection threshold (delta_win <= -20)."""

    def test_drop_under_twenty_points_is_not_a_mistake(self) -> None:
        # Before: 75% -> After: 56% (delta = -19 percentage points)
        # Using cp: let before be ~300 (75.05%), after ~65 (55.97%), delta ~ -19.08
        # We can construct MoveEvaluation where delta_win = -19
        # W(cp=298) ~= 75.0%
        # Let's verify with explicit values
        move = MoveEvaluation(
            player_color=chess.WHITE,
            before=Evaluation(cp=298),
            after=Evaluation(cp=68),  # W(68) ~= 56.2%, delta ~= -18.8%
            clock_seconds=60.0,
        )
        assert detect_mistake(move) is None

    def test_drop_exactly_twenty_points_is_a_mistake(self) -> None:
        # We find cp_before and cp_after such that delta_win is <= -20.0
        # W(0) = 50.0%. For W to be 30.0%:
        # 100 / (1 + exp(-k * cp)) = 30 => exp(-k * cp) = 7/3 => -k * cp = ln(7/3)
        # cp = -ln(7/3) / 0.00368208 ~= -230.11
        move = MoveEvaluation(
            player_color=chess.WHITE,
            before=Evaluation(cp=0),      # 50.0%
            after=Evaluation(cp=-231),    # 29.93%, drop = -20.07 points
            clock_seconds=45.0,
        )
        res = detect_mistake(move)
        assert res is not None
        assert isinstance(res, MistakeResult)
        assert res.delta_win <= -20.0
        assert res.win_before == pytest.approx(50.0, abs=0.1)
        assert res.win_after == pytest.approx(29.93, abs=0.1)

    def test_drop_thirty_five_points_is_a_mistake(self) -> None:
        # Before: cp=100 (59.1%) -> After: cp=-300 (24.8%), delta ~= -34.3%
        move = MoveEvaluation(
            player_color=chess.WHITE,
            before=Evaluation(cp=100),
            after=Evaluation(cp=-300),
            clock_seconds=30.0,
        )
        res = detect_mistake(move)
        assert res is not None
        assert res.delta_win <= -30.0

    def test_black_player_mistake_detected_correctly(self) -> None:
        # Black is winning before: White POV cp = -200 (Black POV +200, win% ~67.6%)
        # After blunder: White POV cp = +150 (Black POV -150, win% ~36.5%)
        # Delta for Black: 36.5% - 67.6% = -31.1% <= -20% -> Mistake!
        move = MoveEvaluation(
            player_color=chess.BLACK,
            before=Evaluation(cp=-200),
            after=Evaluation(cp=150),
            clock_seconds=120.0,
        )
        res = detect_mistake(move)
        assert res is not None
        assert res.delta_win <= -20.0

    def test_win_chances_increase_is_not_a_mistake(self) -> None:
        move = MoveEvaluation(
            player_color=chess.WHITE,
            before=Evaluation(cp=0),
            after=Evaluation(cp=150),
            clock_seconds=60.0,
        )
        assert detect_mistake(move) is None


class TestExceptionFilters:
    """Nhóm D — Exception filters (clock < 10s, already decided position)."""

    def test_clock_eight_seconds_is_filtered_out(self) -> None:
        move = MoveEvaluation(
            player_color=chess.WHITE,
            before=Evaluation(cp=100),
            after=Evaluation(cp=-300),  # Blunder drop > 30%
            clock_seconds=8.0,
        )
        assert detect_mistake(move) is None

    def test_clock_nine_point_ninety_nine_seconds_is_filtered_out(self) -> None:
        move = MoveEvaluation(
            player_color=chess.WHITE,
            before=Evaluation(cp=100),
            after=Evaluation(cp=-300),
            clock_seconds=9.99,
        )
        assert detect_mistake(move) is None

    def test_clock_ten_seconds_is_not_filtered_by_clock(self) -> None:
        move = MoveEvaluation(
            player_color=chess.WHITE,
            before=Evaluation(cp=100),
            after=Evaluation(cp=-300),
            clock_seconds=10.0,
        )
        assert detect_mistake(move) is not None

    def test_missing_clock_is_not_filtered(self) -> None:
        move = MoveEvaluation(
            player_color=chess.WHITE,
            before=Evaluation(cp=100),
            after=Evaluation(cp=-300),
            clock_seconds=None,
        )
        assert detect_mistake(move) is not None

    def test_position_already_decided_with_cp_1000_is_filtered_out(self) -> None:
        # Before move cp was +1000 (already winning) -> drops to +500: filtered out!
        move = MoveEvaluation(
            player_color=chess.WHITE,
            before=Evaluation(cp=1000),
            after=Evaluation(cp=500),
            clock_seconds=60.0,
        )
        assert detect_mistake(move) is None

    def test_position_already_decided_with_cp_minus_1200_is_filtered_out(self) -> None:
        # Before move player was already crushed: cp = -1200
        move = MoveEvaluation(
            player_color=chess.WHITE,
            before=Evaluation(cp=-1200),
            after=Evaluation(cp=-2000),
            clock_seconds=60.0,
        )
        assert detect_mistake(move) is None

    def test_position_already_decided_with_mate_score_is_filtered_out(self) -> None:
        # Before move there was already a forced mate
        move_winning_mate = MoveEvaluation(
            player_color=chess.WHITE,
            before=Evaluation(mate=2),
            after=Evaluation(cp=200),
            clock_seconds=60.0,
        )
        assert detect_mistake(move_winning_mate) is None

        move_losing_mate = MoveEvaluation(
            player_color=chess.WHITE,
            before=Evaluation(mate=-2),
            after=Evaluation(mate=-1),
            clock_seconds=60.0,
        )
        assert detect_mistake(move_losing_mate) is None
