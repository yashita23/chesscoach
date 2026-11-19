from dataclasses import dataclass
from enum import Enum
from typing import Literal
import chess

from chesscoach.skills import MISSED_TACTIC, skills_of

GamePhase = Literal["opening", "middlegame", "endgame"]

# Hằng số điểm vật chất phi-tốt (non-pawn material)
PIECE_VALUES: dict[chess.PieceType, int] = {
    chess.QUEEN: 9,
    chess.ROOK: 5,
    chess.BISHOP: 3,
    chess.KNIGHT: 3,
    chess.PAWN: 0,
    chess.KING: 0,
}

OPENING_MAX_FULLMOVES = 10
OPENING_MIN_TOTAL_MATERIAL = 40
ENDGAME_MAX_TOTAL_MATERIAL = 16
ENDGAME_MAX_SIDE_MATERIAL_NO_QUEEN = 13


class MotifSource(str, Enum):
    """Nguồn phát hiện motif chiến thuật."""

    OPPONENT_REFUTATION = "opponent_refutation"
    MISSED_BEST_MOVE = "missed_best_move"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class MoveContext:
    """Ngữ cảnh của một nước lỗi để nhận diện motif và phân loại giai đoạn ván.

    Attributes:
        board_before: Thế cờ ngay trước nước đi của người chơi.
        played_move: Nước đi thực tế của người chơi (nước lỗi).
        player_color: Màu quân của người chơi (chess.WHITE hoặc chess.BLACK).
        best_move: Nước đi tối ưu mà người chơi bỏ lỡ (nếu có).
        refutation_move: Nước đi đáp trả tối ưu của đối thủ sau played_move (nếu có).
    """

    board_before: chess.Board
    played_move: chess.Move
    player_color: chess.Color
    best_move: chess.Move | None = None
    refutation_move: chess.Move | None = None


@dataclass(frozen=True)
class MotifResult:
    """Kết quả nhận diện motif chiến thuật.

    Attributes:
        motif: Theme Lichess tương ứng (ví dụ 'fork', 'pin', 'hangingPiece', 'missedTactic').
        skill_id: Kỹ năng trong 20 skills của app (từ skills.py).
        source: Nguồn phát hiện (đối thủ khai thác, nước mình bỏ lỡ, hoặc fallback).
    """

    motif: str
    skill_id: str
    source: MotifSource


def classify_game_phase(board: chess.Board) -> GamePhase:
    """Phân loại giai đoạn ván cờ (opening, middlegame, endgame) dựa trên fullmoves và material phi-tốt."""
    white_material = sum(
        len(board.pieces(pt, chess.WHITE)) * val
        for pt, val in PIECE_VALUES.items()
    )
    black_material = sum(
        len(board.pieces(pt, chess.BLACK)) * val
        for pt, val in PIECE_VALUES.items()
    )
    total_material = white_material + black_material
    has_queen = bool(board.pieces(chess.QUEEN, chess.WHITE) or board.pieces(chess.QUEEN, chess.BLACK))

    # Thứ tự ưu tiên: endgame trước opening
    if (
        (not has_queen and white_material <= ENDGAME_MAX_SIDE_MATERIAL_NO_QUEEN and black_material <= ENDGAME_MAX_SIDE_MATERIAL_NO_QUEEN)
        or total_material <= ENDGAME_MAX_TOTAL_MATERIAL
    ):
        return "endgame"

    if board.fullmove_number <= OPENING_MAX_FULLMOVES and total_material >= OPENING_MIN_TOTAL_MATERIAL:
        return "opening"

    return "middlegame"


def _step_ray(
    board: chess.Board, start_sq: int, df: int, dr: int
) -> tuple[int | None, int | None]:
    """Tìm 2 quân cờ đầu tiên trên tia (df, dr) tính từ start_sq."""
    file = chess.square_file(start_sq)
    rank = chess.square_rank(start_sq)
    first_sq: int | None = None
    second_sq: int | None = None

    while True:
        file += df
        rank += dr
        if not (0 <= file <= 7 and 0 <= rank <= 7):
            break
        sq = chess.square(file, rank)
        if board.piece_at(sq) is not None:
            if first_sq is None:
                first_sq = sq
            elif second_sq is None:
                second_sq = sq
                break

    return first_sq, second_sq


def _detect_motifs_on_move(
    board_start: chess.Board, move: chess.Move, source: MotifSource
) -> MotifResult | None:
    """Nhận diện motif từ một nước đi trên bàn cờ xuất phát."""
    active_color = board_start.turn
    victim_color = not active_color

    board_end = board_start.copy()
    board_end.push(move)

    # 1. Mate in 1
    if board_end.is_checkmate():
        skills = skills_of(["mateIn1"])
        return MotifResult(motif="mateIn1", skill_id=next(iter(skills)), source=source)

    # 2. Hanging piece (ăn quân đối phương không có bảo vệ)
    captured = board_start.piece_at(move.to_square)
    if captured is not None and captured.color == victim_color:
        # Nếu quân bị ăn không hề được bảo vệ trên board_start
        if not board_start.is_attacked_by(victim_color, move.to_square):
            skills = skills_of(["hangingPiece"])
            return MotifResult(motif="hangingPiece", skill_id=next(iter(skills)), source=source)

    # 3. Discovered attack (nước đi mở đường cho quân trượt phía sau tấn công mục tiêu quan trọng)
    sliders = (
        board_start.pieces(chess.BISHOP, active_color)
        | board_start.pieces(chess.ROOK, active_color)
        | board_start.pieces(chess.QUEEN, active_color)
    )
    for slider_sq in sliders:
        if slider_sq == move.from_square:
            continue
        attacks_before = board_start.attacks(slider_sq)
        attacks_after = board_end.attacks(slider_sq)
        new_attacks = attacks_after - attacks_before
        for tgt_sq in new_attacks:
            tgt = board_end.piece_at(tgt_sq)
            if tgt is not None and tgt.color == victim_color:
                if tgt.piece_type in (
                    chess.QUEEN,
                    chess.ROOK,
                    chess.BISHOP,
                    chess.KNIGHT,
                    chess.KING,
                ):
                    skills = skills_of(["discoveredAttack"])
                    return MotifResult(
                        motif="discoveredAttack", skill_id=next(iter(skills)), source=source
                    )

    # 4. Pin & Skewer
    # Kiểm tra quân vừa di chuyển có tạo ra đòn ghim hoặc xiên quân không
    moved_piece = board_end.piece_at(move.to_square)
    if moved_piece is not None and moved_piece.piece_type in (
        chess.BISHOP,
        chess.ROOK,
        chess.QUEEN,
    ):
        to_sq = move.to_square
        directions: list[tuple[int, int]] = []
        if moved_piece.piece_type in (chess.BISHOP, chess.QUEEN):
            directions.extend([(1, 1), (1, -1), (-1, 1), (-1, -1)])
        if moved_piece.piece_type in (chess.ROOK, chess.QUEEN):
            directions.extend([(1, 0), (-1, 0), (0, 1), (0, -1)])

        for df, dr in directions:
            sq1, sq2 = _step_ray(board_end, to_sq, df, dr)
            if sq1 is None or sq2 is None:
                continue
            p1 = board_end.piece_at(sq1)
            p2 = board_end.piece_at(sq2)
            if p1 is None or p2 is None:
                continue
            if p1.color != victim_color or p2.color != victim_color:
                continue

            # Absolute Pin: p2 là Vua, p1 bị ghim
            if p2.piece_type == chess.KING:
                skills = skills_of(["pin"])
                return MotifResult(motif="pin", skill_id=next(iter(skills)), source=source)

            # Skewer: p1 là Vua (hoặc quân giá trị cao hơn p2), p2 bị lộ phía sau
            if p1.piece_type == chess.KING and p2.piece_type in (
                chess.QUEEN,
                chess.ROOK,
                chess.BISHOP,
                chess.KNIGHT,
            ):
                skills = skills_of(["skewer"])
                return MotifResult(motif="skewer", skill_id=next(iter(skills)), source=source)

            val1 = PIECE_VALUES[p1.piece_type]
            val2 = PIECE_VALUES[p2.piece_type]

            # Relative Pin: p1 có giá trị thấp hơn p2 (ví dụ Mã trước Hậu/Xe)
            if val1 < val2 and val2 >= 5:
                skills = skills_of(["pin"])
                return MotifResult(motif="pin", skill_id=next(iter(skills)), source=source)

            # Skewer: p1 có giá trị cao hơn p2 (ví dụ Hậu trước Xe, Xe trước Mã)
            if val1 > val2 and val2 >= 3:
                skills = skills_of(["skewer"])
                return MotifResult(motif="skewer", skill_id=next(iter(skills)), source=source)

    # 5. Fork (đòn đôi: 1 quân tấn công >= 2 mục tiêu có ý nghĩa chiến thuật)
    to_sq = move.to_square
    attacker = board_end.piece_at(to_sq)
    if attacker is not None:
        attacked = board_end.attacks(to_sq)
        valid_targets: list[int] = []
        attacker_val = PIECE_VALUES[attacker.piece_type]

        for sq in attacked:
            target = board_end.piece_at(sq)
            if target is None or target.color != victim_color:
                continue
            target_val = PIECE_VALUES[target.piece_type]
            # Mục tiêu 1: Vua đối phương
            if target.piece_type == chess.KING:
                valid_targets.append(sq)
            # Mục tiêu 2: Quân có giá trị cao hơn quân tấn công
            elif target_val > attacker_val:
                valid_targets.append(sq)
            # Mục tiêu 3: Quân không được bảo vệ
            elif not board_end.is_attacked_by(victim_color, sq):
                valid_targets.append(sq)

        if len(valid_targets) >= 2:
            skills = skills_of(["fork"])
            return MotifResult(motif="fork", skill_id=next(iter(skills)), source=source)

    return None


def detect_motif(context: MoveContext) -> MotifResult:
    """Nhận diện motif chiến thuật từ nước đáp trả của đối thủ hoặc nước tốt nhất bỏ lỡ.

    Xác thực dữ liệu đầu vào:
    - board_before.turn phải khớp với player_color.
    - played_move phải hợp lệ trên board_before.
    - best_move (nếu có) phải hợp lệ trên board_before.
    - refutation_move (nếu có) phải hợp lệ trên thế cờ sau played_move.

    Thứ tự ưu tiên:
    1. OPPONENT_REFUTATION: Đòn chiến thuật đối thủ tung ra qua refutation_move.
    2. MISSED_BEST_MOVE: Đòn chiến thuật người chơi bỏ lỡ qua best_move.
    3. FALLBACK: Không phát hiện được đòn cụ thể -> MISSED_TACTIC ('missed_tactic').
    """
    # Validation 1: Kiểm tra lượt đi khớp với màu quân người chơi
    if context.board_before.turn != context.player_color:
        raise ValueError(
            f"board_before.turn ({context.board_before.turn}) không khớp với player_color ({context.player_color})"
        )

    # Validation 2: played_move phải hợp lệ trên board_before
    if context.played_move not in context.board_before.legal_moves:
        raise ValueError(
            f"played_move {context.played_move} không hợp lệ trên board_before"
        )

    # Validation 3: best_move phải hợp lệ trên board_before
    if context.best_move is not None and context.best_move not in context.board_before.legal_moves:
        raise ValueError(
            f"best_move {context.best_move} không hợp lệ trên board_before"
        )

    # Validation 4: refutation_move phải hợp lệ trên thế cờ sau played_move
    board_after_played = context.board_before.copy()
    board_after_played.push(context.played_move)

    if (
        context.refutation_move is not None
        and context.refutation_move not in board_after_played.legal_moves
    ):
        raise ValueError(
            f"refutation_move {context.refutation_move} không hợp lệ sau played_move"
        )

    # 1. Ưu tiên 1: OPPONENT_REFUTATION
    if context.refutation_move is not None:
        res = _detect_motifs_on_move(
            board_after_played, context.refutation_move, MotifSource.OPPONENT_REFUTATION
        )
        if res is not None:
            return res

    # 2. Ưu tiên 2: MISSED_BEST_MOVE
    if context.best_move is not None:
        res = _detect_motifs_on_move(
            context.board_before, context.best_move, MotifSource.MISSED_BEST_MOVE
        )
        if res is not None:
            return res

    # 3. Fallback: không tìm thấy motif cụ thể
    return MotifResult(
        motif="missedTactic",
        skill_id=MISSED_TACTIC,
        source=MotifSource.FALLBACK,
    )
