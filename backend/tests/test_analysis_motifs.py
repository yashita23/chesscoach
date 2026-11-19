import chess
import pytest

from chesscoach.analysis.motifs import (
    MotifResult,
    MotifSource,
    MoveContext,
    classify_game_phase,
    detect_motif,
)
from chesscoach.skills import MISSED_TACTIC, SKILLS_BY_ID, skills_of


class TestInputValidation:
    """Nhóm 1 — Kiểm tra tính hợp lệ của dữ liệu đầu vào trong MoveContext."""

    def test_turn_mismatch_raises_error(self) -> None:
        # Bàn cờ đang là lượt Trắng đi (turn=WHITE), nhưng player_color lại là BLACK
        board = chess.Board()
        assert board.turn == chess.WHITE
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e2e4"),
            player_color=chess.BLACK,
        )
        with pytest.raises(ValueError, match="turn"):
            detect_motif(ctx)

    def test_illegal_played_move_raises_error(self) -> None:
        board = chess.Board()
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e2e5"),  # Nước không hợp lệ từ vị trí ban đầu
            player_color=chess.WHITE,
        )
        with pytest.raises(ValueError, match="played_move"):
            detect_motif(ctx)

    def test_illegal_best_move_raises_error(self) -> None:
        board = chess.Board()
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e2e4"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("e7e5"),  # best_move không hợp lệ cho Trắng
        )
        with pytest.raises(ValueError, match="best_move"):
            detect_motif(ctx)

    def test_illegal_refutation_move_raises_error(self) -> None:
        board = chess.Board()
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e2e4"),
            player_color=chess.WHITE,
            refutation_move=chess.Move.from_uci("a1a8"),  # Nước đối thủ không hợp lệ sau 1. e4
        )
        with pytest.raises(ValueError, match="refutation_move"):
            detect_motif(ctx)


class TestMotifDetection:
    """Nhóm 2 — Nhận diện các motif chiến thuật cơ bản và phân biệt trường hợp sai."""

    def test_detect_fork_valid(self) -> None:
        # Trắng cầm quân, nước bỏ lỡ best_move là Nf7+ fork Vua e8 và Xe h8
        # FEN: 4k2r/8/8/8/5N2/8/8/4K3 w k - 0 1
        board = chess.Board("4k2r/8/8/8/5N2/8/8/4K3 w k - 0 1")
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e1e2"),  # Nước lỗi
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("f4g6"),    # f4g6 hoặc f4e6... để fork: Nf6+ hoặc fork e8/h8
        )
        # Giả sử best_move là Ne6 hoặc Ng6 fork xe và vua
        # Dùng FEN chuẩn fork: Trắng Mã f4, Đen Vua e8, Xe h8. Mã nhảy g6 tấn công cả e8 và h8 (hoặc g6 tấn công h8)
        # Tốt hơn: Trắng Mã d5, Đen Vua e7, Hậu c7. Nd5-c7 hoặc Nd5-f6:
        # FEN: 4k3/2q5/8/3N4/8/8/8/4K3 w - - 0 1 -> Mã c7 fork Vua e8 và Hậu c7 (ăn hậu)
        # FEN fork vua và xe: Mã c7 chiếu vua e8 và bắt xe a8:
        # FEN: r3k3/8/8/3N4/8/8/8/4K3 w q - 0 1 -> Mã c7+ fork vua e8 và xe a8
        board_fork = chess.Board("r3k3/8/8/3N4/8/8/8/4K3 w q - 0 1")
        ctx_fork = MoveContext(
            board_before=board_fork,
            played_move=chess.Move.from_uci("e1e2"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("d5c7"),  # Fork King e8 and Rook a8
        )
        result = detect_motif(ctx_fork)
        assert result.motif == "fork"
        assert result.skill_id == "fork"
        assert result.source == MotifSource.MISSED_BEST_MOVE

    def test_reject_false_fork_single_target(self) -> None:
        # Mã chỉ tấn công 1 quân, không phải fork
        board = chess.Board("4k3/8/8/3N4/8/8/8/4K3 w - - 0 1")
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e1e2"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("d5f6"),  # Chỉ chiếu vua, không tấn công quân thứ 2
        )
        result = detect_motif(ctx)
        assert result.motif != "fork"

    def test_detect_hanging_piece(self) -> None:
        # Đen để xe a8 không ai bảo vệ. Trắng bỏ lỡ nước ăn xe treo
        # FEN: r3k3/8/8/8/8/8/8/R3K3 w Qq - 0 1 (Trắng xe a1 ăn xe a8 không bảo vệ)
        board = chess.Board("r3k3/8/8/8/8/8/8/R3K3 w - - 0 1")
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e1e2"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("a1a8"),
        )
        result = detect_motif(ctx)
        assert result.motif == "hangingPiece"
        assert result.skill_id == "hanging_piece"

    def test_reject_hanging_piece_when_defended(self) -> None:
        # Quân bị tấn công nhưng được bảo vệ bởi quân khác có giá trị tương đương hoặc thấp hơn
        # FEN: r2k4/8/8/8/8/8/8/R2K4 w - - 0 1 (Xe a8 được Vua d8 bảo vệ hoặc xe khác bảo vệ)
        # Đen: Xe a8 được Xe b8 bảo vệ: r1r1k3/8/8/8/8/8/8/R3K3 w - - 0 1
        board = chess.Board("r1r1k3/8/8/8/8/8/8/R3K3 w - - 0 1")
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e1e2"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("a1b1"),  # Nước bình thường
        )
        result = detect_motif(ctx)
        assert result.motif != "hangingPiece"

    def test_detect_absolute_pin(self) -> None:
        # Tượng ghim Mã vào Vua (Absolute pin)
        # Trắng Tượng b5 ghim Mã c6 vào Vua e8
        # FEN: 4k3/8/2n5/1B6/8/8/8/4K3 w - - 0 1
        board = chess.Board("4k3/8/2n5/1B6/8/8/8/4K3 w - - 0 1")
        # Nước tốt nhất là tấn công quân bị ghim hoặc Đen bị ghim
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e1e2"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("b5c6"),  # Ăn quân bị ghim
        )
        # Hoặc nước đi tạo ra đòn ghim: Tượng e2 lên b5 ghim mã c6 vào vua e8
        board2 = chess.Board("4k3/8/2n5/8/8/8/4B3/4K3 w - - 0 1")
        ctx2 = MoveContext(
            board_before=board2,
            played_move=chess.Move.from_uci("e1d1"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("e2b5"),  # Tạo pin
        )
        result = detect_motif(ctx2)
        assert result.motif == "pin"
        assert result.skill_id == "pin"

    def test_detect_relative_pin(self) -> None:
        # Tượng ghim Mã vào Hậu (Relative pin)
        # Trắng Tượng g5 ghim Mã f6 vào Hậu d8
        # FEN: 3qkb1r/8/5n2/8/8/8/8/4K1B1 w k - 0 1
        # Trắng Tượng h4 lên g5 ghim f6 vào d8
        board = chess.Board("3qkb1r/8/5n2/8/7B/8/8/4K3 w k - 0 1")
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e1e2"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("h4g5"),  # Tạo ghim relative vào Hậu
        )
        result = detect_motif(ctx)
        assert result.motif == "pin"
        assert result.skill_id == "pin"

    def test_detect_skewer(self) -> None:
        # Xe trắng trên a1 lên a8 xiên Vua đen trên e8, Xe đen trên h8 phía sau trên cùng hàng 8
        # FEN: 4k2r/8/8/8/8/8/8/R3K3 w - - 0 1 -> Ra1-a8+ chiếu King e8, lộ Xe h8
        board = chess.Board("4k2r/8/8/8/8/8/8/R3K3 w - - 0 1")
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e1e2"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("a1a8"),  # Skewer: King e8 moves, Rook h8 falls
        )
        result = detect_motif(ctx)
        assert result.motif == "skewer"
        assert result.skill_id == "skewer"

    def test_detect_discovered_attack(self) -> None:
        # Mã trên d5 di chuyển mở đường cho Xe trên d1 tấn công Hậu đen trên d8
        # FEN: 3q4/8/8/3N4/8/8/8/3RK3 w - - 0 1
        # Nước di chuyển Mã d5 (d5f4) mở đường d-file cho Xe d1 tấn công Hậu d8
        board = chess.Board("3q4/8/8/3N4/8/8/8/3RK3 w - - 0 1")
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e1e2"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("d5f4"),  # Mở đường Xe d1 tấn công Hậu d8
        )
        result = detect_motif(ctx)
        assert result.motif == "discoveredAttack"
        assert result.skill_id == "discovered_attack"

    def test_detect_mate_in_1(self) -> None:
        # Hậu chiếu hết hàng cuối hoặc chiếu hết trực tiếp
        # FEN: 6k1/5ppp/8/8/8/8/8/4K1Q1 w - - 0 1 -> Qg1-a7 hoặc back rank
        # FEN Scholar's mate: 4k3/4Qppp/8/8/8/8/8/4K3 w - - 0 1 (hoặc Qf7#)
        board = chess.Board("r1bqkb1r/pppp1ppp/2n5/4p3/2B1n3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 0 1")
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("c4d5"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("f3f7"),  # Mate in 1
        )
        result = detect_motif(ctx)
        assert result.motif == "mateIn1"
        assert result.skill_id == "mate_in_1"


class TestPriorityAndFallback:
    """Nhóm 3 — Ưu tiên refutation_move, best_move và fallback."""

    def test_refutation_fork_takes_priority_over_missed_pin(self) -> None:
        # Người chơi đi nước lỗi, đối thủ tung đòn refutation fork; đồng thời người chơi bỏ lỡ nước pin
        # Ưu tiên phải là OPPONENT_REFUTATION fork
        # Bàn cờ trước nước đi của Trắng: Mã đen ở d4, Xe trắng a1, Vua trắng e1
        board = chess.Board("r3k3/8/8/8/3n4/8/8/R3K3 w Qq - 0 1")
        # Trắng đi e1d2 (bỏ lỡ nước xiên/ăn xe a1a8)
        # Đen đáp trả bằng d4b3+ fork Vua d2 và Xe a1
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e1d2"),
            player_color=chess.WHITE,
            refutation_move=chess.Move.from_uci("d4b3"),  # Black knight forks King d2 and Rook a1
            best_move=chess.Move.from_uci("a1a8"),        # White missed skewer/hanging piece
        )
        result = detect_motif(ctx)
        assert result.source == MotifSource.OPPONENT_REFUTATION
        assert result.motif == "fork"
        assert result.skill_id == "fork"

    def test_missed_move_used_when_no_refutation_motif(self) -> None:
        # Không có refutation_move (hoặc refutation không có motif), nhưng best_move có fork
        board = chess.Board("r3k3/8/8/3N4/8/8/8/4K3 w q - 0 1")
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e1e2"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("d5c7"),  # Fork
            refutation_move=None,
        )
        result = detect_motif(ctx)
        assert result.source == MotifSource.MISSED_BEST_MOVE
        assert result.motif == "fork"
        assert result.skill_id == "fork"

    def test_fallback_to_missed_tactic_when_no_motif_found(self) -> None:
        # Cả refutation lẫn best_move đều không thuộc motif cụ thể nào
        board = chess.Board("8/8/8/8/8/4k3/4p3/4K3 w - - 0 1")
        # Thế cờ hòa/đơn giản, không có đòn chiến thuật nào
        board_quiet = chess.Board("8/8/4k3/8/8/4K3/8/8 w - - 0 1")
        ctx = MoveContext(
            board_before=board_quiet,
            played_move=chess.Move.from_uci("e3e4"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("e3d4"),
        )
        result = detect_motif(ctx)
        assert result.source == MotifSource.FALLBACK
        assert result.skill_id == MISSED_TACTIC
        assert result.motif == "missedTactic"

    def test_skill_mapping_always_in_twenty_skills(self) -> None:
        # Mọi motif được trả về đều có skill_id nằm trong 20 skills của app
        board = chess.Board("r3k3/8/8/3N4/8/8/8/4K3 w q - 0 1")
        ctx = MoveContext(
            board_before=board,
            played_move=chess.Move.from_uci("e1e2"),
            player_color=chess.WHITE,
            best_move=chess.Move.from_uci("d5c7"),
        )
        result = detect_motif(ctx)
        assert result.skill_id in SKILLS_BY_ID


class TestGamePhaseClassification:
    """Nhóm 4 — Phân loại giai đoạn ván cờ (opening, middlegame, endgame)."""

    def test_phase_opening_at_fullmove_10_material_40(self) -> None:
        # Thế cờ ban đầu: fullmove=1, total material = 62 (>= 40)
        board = chess.Board()
        board.fullmove_number = 10
        assert classify_game_phase(board) == "opening"

    def test_phase_not_opening_at_fullmove_11(self) -> None:
        # Fullmove=11, total material = 62 -> Không còn là opening nữa, chuyển sang middlegame
        board = chess.Board()
        board.fullmove_number = 11
        assert classify_game_phase(board) == "middlegame"

    def test_phase_endgame_at_total_material_16(self) -> None:
        # Tổng material phi-tốt <= 16 (ví dụ mỗi bên 1 Xe = 10 điểm, hoặc 1 Hậu + 1 Tượng = 12 điểm)
        # FEN: Trắng Vua e1, Hậu d1 (9 điểm). Đen Vua e8, Xe a8 (5 điểm). Tổng = 14 <= 16
        board = chess.Board("r3k3/8/8/8/8/8/8/3QK3 w - - 0 20")
        assert classify_game_phase(board) == "endgame"

    def test_phase_endgame_no_queens_and_material_13_each(self) -> None:
        # Không có Hậu, Trắng có Xe (5) + Tượng (3) + Mã (3) = 11 <= 13; Đen tương tự
        # FEN: r1b1k3/8/8/8/8/8/8/R1B1K3 w - - 0 25
        board = chess.Board("r1b1k3/8/8/8/8/8/8/R1B1K3 w - - 0 25")
        assert classify_game_phase(board) == "endgame"

    def test_phase_middlegame_asymmetric_material(self) -> None:
        # Trắng còn Hậu (9) + Xe (5) + Tượng (3) + Mã (3) = 20 điểm.
        # Đen còn 1 Xe (5 điểm). Tổng material = 25 (> 16), có Hậu, fullmove=15
        board = chess.Board("r3k3/8/8/8/8/8/8/RNBQK3 w - - 0 15")
        assert classify_game_phase(board) == "middlegame"

    def test_phase_endgame_only_pawns_and_kings(self) -> None:
        # Thế cờ tàn cuộc tốt (material phi-tốt = 0)
        board = chess.Board("4k3/4p3/8/8/8/8/4P3/4K3 w - - 0 30")
        assert classify_game_phase(board) == "endgame"
