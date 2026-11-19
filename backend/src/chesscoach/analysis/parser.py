from dataclasses import dataclass
import io
import re
import chess
import chess.pgn

from chesscoach.analysis.eval import Evaluation, MoveEvaluation

# Baseline trung lập quy ước cho thế cờ xuất phát trước nước đầu tiên (0 centipawns)
NEUTRAL_BASELINE_EVAL = Evaluation(cp=0, mate=None)


@dataclass(frozen=True)
class ParsedMoveItem:
    """Một nước đi của người chơi đã được bóc tách đánh giá từ PGN.

    Attributes:
        ply: Chỉ số nửa nước (1-based, ví dụ 1 cho 1. e4, 2 cho 1... e5).
        move_number: Số thứ tự nước đi (fullmove number: 1, 2, 3...).
        move: Đối tượng chess.Move.
        san: Ký hiệu SAN của nước đi (ví dụ 'Nf6', 'e4').
        board_before: Thế cờ FEN ngay trước nước đi của người chơi.
        evaluation: Đánh giá trước/sau theo White POV và clock (từ Seam 1).
    """

    ply: int
    move_number: int
    move: chess.Move
    san: str
    board_before: chess.Board
    evaluation: MoveEvaluation


@dataclass(frozen=True)
class RawParsedMove:
    """Toàn bộ thông tin một nước đi trong ván cờ, giữ lại kể cả khi thiếu evaluation."""

    ply: int
    move_number: int
    move: chess.Move
    san: str
    board_before: chess.Board
    player_color: chess.Color
    is_player_move: bool
    evaluation_before: Evaluation | None
    evaluation_after: Evaluation | None
    clock_seconds: float | None


def parse_eval_string(eval_str: str) -> Evaluation:
    """Chuyển đổi chuỗi từ [%eval ...] thành Evaluation(cp, mate).

    - Chuỗi dạng '#3' -> Evaluation(mate=3)
    - Chuỗi dạng '#-2' -> Evaluation(mate=-2)
    - Chuỗi dạng '0.2' -> Evaluation(cp=20)
    - Chuỗi dạng '-1.55' -> Evaluation(cp=-155)
    """
    cleaned = eval_str.strip()
    if cleaned.startswith("#"):
        mate_str = cleaned[1:]
        if mate_str.startswith("+"):
            mate_str = mate_str[1:]
        return Evaluation(cp=None, mate=int(mate_str))

    cp = int(round(float(cleaned) * 100))
    return Evaluation(cp=cp, mate=None)


def parse_clock_string(clk_str: str) -> float | None:
    """Chuyển đổi chuỗi từ [%clk ...] thành số giây (float).

    Định dạng thường gặp: 'h:m:s' hoặc 'm:s', ví dụ '0:02:45' -> 165.0 giây.
    Trả về None nếu chuỗi rỗng hoặc sai định dạng.
    """
    cleaned = clk_str.strip()
    if not cleaned:
        return None

    parts = cleaned.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 1:
            return float(parts[0])
    except (ValueError, TypeError):
        return None

    return None


def extract_player_color(headers: chess.pgn.Headers, player_username: str) -> chess.Color:
    """Xác định màu quân của người chơi từ headers của ván đấu (so sánh không phân biệt hoa thường).

    Ném ValueError nếu player_username không trùng với White hoặc Black,
    hoặc nếu username trùng với cả 2 bên (không xác định được).
    """
    white_user = headers.get("White", "").strip().lower()
    black_user = headers.get("Black", "").strip().lower()
    target_user = player_username.strip().lower()

    if white_user == target_user and black_user == target_user:
        raise ValueError(
            f"Tên người chơi '{player_username}' trùng với cả hai bên Trắng và Đen"
        )

    if white_user == target_user:
        return chess.WHITE
    if black_user == target_user:
        return chess.BLACK

    raise ValueError(
        f"Không tìm thấy người chơi '{player_username}' trong headers ván đấu (White: {headers.get('White')}, Black: {headers.get('Black')})"
    )


def parse_raw_game_moves(
    pgn_text: str,
    player_username: str,
) -> list[RawParsedMove]:
    """Phân tích chuỗi PGN và rút trích toàn bộ nước đi của ván cờ, giữ lại các node thiếu eval."""
    sio = io.StringIO(pgn_text.strip())
    game = chess.pgn.read_game(sio)
    if game is None:
        return []

    player_color = extract_player_color(game.headers, player_username)

    raw_moves: list[RawParsedMove] = []
    board = game.board()
    prev_node_eval: Evaluation | None = NEUTRAL_BASELINE_EVAL

    for node in game.mainline():
        move = node.move
        san = board.san(move)
        board_before = board.copy()

        curr_eval: Evaluation | None = None
        ev = node.eval()
        if ev is not None:
            w_ev = ev.pov(chess.WHITE)
            curr_eval = Evaluation(cp=w_ev.score(), mate=w_ev.mate())
        elif "[%eval" in node.comment:
            m = re.search(r"\[%eval\s+([^\]]+)\]", node.comment)
            if m:
                try:
                    curr_eval = parse_eval_string(m.group(1))
                except Exception:
                    curr_eval = None

        clock_sec = node.clock()
        if clock_sec is None and "[%clk" in node.comment:
            m_clk = re.search(r"\[%clk\s+([^\]]+)\]", node.comment)
            if m_clk:
                clock_sec = parse_clock_string(m_clk.group(1))

        is_player = (board.turn == player_color)
        ply = node.ply()
        move_number = (ply + 1) // 2

        raw_moves.append(
            RawParsedMove(
                ply=ply,
                move_number=move_number,
                move=move,
                san=san,
                board_before=board_before,
                player_color=player_color,
                is_player_move=is_player,
                evaluation_before=prev_node_eval,
                evaluation_after=curr_eval,
                clock_seconds=clock_sec,
            )
        )

        board.push(move)
        prev_node_eval = curr_eval

    return raw_moves


def parse_game_evaluations(
    pgn_text: str,
    player_username: str,
) -> list[ParsedMoveItem]:
    """Phân tích chuỗi PGN và rút trích các nước đi của người chơi kèm đánh giá.

    Quy tắc:
    1. Xác định màu quân người chơi từ header.
    2. Chỉ duyệt các nước đi của người chơi (bỏ qua nước của đối thủ).
    3. Đánh giá thế cờ:
       - before: Đánh giá của thế cờ trước nước đi (White POV).
         Với ply 1 (White 1. e4): lấy NEUTRAL_BASELINE_EVAL (cp=0, mate=None).
         Với ply i > 1: lấy eval từ comment của ply i-1.
       - after: Đánh giá từ comment của ply i (White POV).
       - Bỏ qua nước đi nếu thiếu một trong hai giá trị before hoặc after.
    4. Đồng hồ: Rút trích từ [%clk ...] trong comment của ply i.
    """
    raw_moves = parse_raw_game_moves(pgn_text, player_username)
    items: list[ParsedMoveItem] = []

    for rm in raw_moves:
        if (
            rm.is_player_move
            and rm.evaluation_before is not None
            and rm.evaluation_after is not None
        ):
            move_eval = MoveEvaluation(
                player_color=rm.player_color,
                before=rm.evaluation_before,
                after=rm.evaluation_after,
                clock_seconds=rm.clock_seconds,
            )
            items.append(
                ParsedMoveItem(
                    ply=rm.ply,
                    move_number=rm.move_number,
                    move=rm.move,
                    san=rm.san,
                    board_before=rm.board_before,
                    evaluation=move_eval,
                )
            )

    return items
