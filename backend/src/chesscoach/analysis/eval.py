from dataclasses import dataclass
import math
import chess

# Hằng số chuẩn Lichess chuyển đổi centipawns sang win percentage
LICHESS_WIN_COEFF = 0.00368208
# Ngưỡng sụt giảm xác suất thắng (điểm phần trăm) để xác định lỗi
BLUNDER_DROP_THRESHOLD = -20.0
# Ngưỡng centipawn thế cờ đã ngã ngũ trước nước đi
DECIDED_CP_THRESHOLD = 1000
# Ngưỡng thời gian đồng hồ tối thiểu (giây) để xét lỗi
CLOCK_MIN_SECONDS = 10.0


@dataclass(frozen=True)
class Evaluation:
    """Điểm đánh giá thế cờ (mặc định theo White POV khi lấy từ PGN/Engine).

    Attributes:
        cp: Điểm lợi thế tính theo centipawn (dương: Trắng ưu thế, âm: Đen ưu thế).
        mate: Số nước dẫn tới chiếu hết (dương: Trắng chiếu hết sau N nước, âm: Đen chiếu hết sau N nước).
    """

    cp: int | None = None
    mate: int | None = None


@dataclass(frozen=True)
class MoveEvaluation:
    """Đánh giá trước và sau một nước đi của người chơi.

    Quy ước về before và after:
    - before: Điểm đánh giá thế cờ ngay trước khi người chơi thực hiện nước đi (theo White POV).
    - after: Điểm đánh giá thế cờ ngay sau nước đi của người chơi (theo White POV).
      Giá trị này phản ánh kết quả đánh giá của engine/minimax cho thế cờ sau nước đi,
      tức đã tính đến nước đáp trả tối ưu nhất của đối thủ.
    - player_color: Màu quân của người chơi (chess.WHITE hoặc chess.BLACK).
    - clock_seconds: Thời gian còn lại trên đồng hồ của người chơi tại nước đi (giây),
      hoặc None nếu PGN không có chú thích [%clk].
    """

    player_color: chess.Color
    before: Evaluation
    after: Evaluation
    clock_seconds: float | None = None


@dataclass(frozen=True)
class MistakeResult:
    """Kết quả phát hiện lỗi của một nước đi.

    Attributes:
        win_before: Xác suất thắng trước nước đi theo Player POV (0.0 đến 100.0).
        win_after: Xác suất thắng sau nước đi theo Player POV (0.0 đến 100.0).
        delta_win: Mức thay đổi xác suất thắng (win_after - win_before) tính theo điểm phần trăm (<= -20).
    """

    win_before: float
    win_after: float
    delta_win: float


BlunderResult = MistakeResult


def to_player_pov(score: Evaluation, player_color: chess.Color) -> Evaluation:
    """Chuẩn hóa điểm đánh giá từ White POV sang Player POV.

    - Nếu người chơi cầm quân Trắng: giữ nguyên dấu.
    - Nếu người chơi cầm quân Đen: đảo dấu cả cp và mate.
    - Bảo toàn các giá trị None.
    """
    if player_color == chess.WHITE:
        return score

    cp = -score.cp if score.cp is not None else None
    mate = -score.mate if score.mate is not None else None
    return Evaluation(cp=cp, mate=mate)


def win_chances(score: Evaluation) -> float:
    """Tính xác suất thắng [0, 100]% từ điểm đánh giá theo chuẩn sigmoid của Lichess.

    Công thức: W(cp) = 100 / (1 + exp(-0.00368208 * cp))
    Đảm bảo ổn định số học, tránh OverflowError với giá trị lớn.
    Xử lý mate trước khi tính sigmoid: mate dương -> 100%, mate âm -> 0%.
    """
    if score.mate is not None:
        if score.mate > 0:
            return 100.0
        if score.mate < 0:
            return 0.0
        return 50.0

    if score.cp is not None:
        x = LICHESS_WIN_COEFF * score.cp
        if x >= 50.0:
            return 100.0
        if x <= -50.0:
            return 0.0
        return 100.0 / (1.0 + math.exp(-x))

    raise ValueError("Evaluation phải chứa ít nhất một trong hai trường cp hoặc mate.")


def detect_mistake(move: MoveEvaluation) -> MistakeResult | None:
    """Phát hiện lỗi khi xác suất thắng của người chơi tụt >= 20 điểm phần trăm.

    Áp dụng các bộ lọc ngoại lệ:
    1. Đồng hồ: Bỏ qua nếu clock_seconds < 10.0 giây (bỏ qua áp lực thời gian/scramble).
       Nếu clock_seconds là None (không có annotation) thì vẫn xét bình thường.
    2. Thế cờ đã ngã ngũ trước nước đi: Bỏ qua nếu thế cờ ngay trước nước đi (before)
       có abs(cp) >= 1000 hoặc có điểm mate.

    Trả về:
        MistakeResult nếu delta_win <= -20.0 điểm phần trăm, ngược lại trả về None.
    """
    # Bộ lọc 1: Áp lực thời gian cạn đồng hồ
    if move.clock_seconds is not None and move.clock_seconds < CLOCK_MIN_SECONDS:
        return None

    # Chuẩn hóa về góc nhìn của người chơi (Player POV)
    before_player = to_player_pov(move.before, move.player_color)

    # Bộ lọc 2: Thế cờ trước nước đi đã ngã ngũ
    if before_player.mate is not None:
        return None
    if before_player.cp is not None and abs(before_player.cp) >= DECIDED_CP_THRESHOLD:
        return None

    after_player = to_player_pov(move.after, move.player_color)

    w_before = win_chances(before_player)
    w_after = win_chances(after_player)
    delta_win = w_after - w_before

    # Điều kiện phát hiện lỗi: mức sụt giảm >= 20 điểm phần trăm (delta_win <= -20)
    if delta_win <= BLUNDER_DROP_THRESHOLD:
        return MistakeResult(win_before=w_before, win_after=w_after, delta_win=delta_win)

    return None


detect_blunder = detect_mistake
