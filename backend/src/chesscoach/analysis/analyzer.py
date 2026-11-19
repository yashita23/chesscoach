from dataclasses import dataclass
from typing import Protocol
import chess

from chesscoach.analysis.eval import detect_mistake
from chesscoach.analysis.motifs import MoveContext, classify_game_phase, detect_motif
from chesscoach.analysis.parser import parse_game_evaluations


@dataclass(frozen=True)
class GameMistake:
    """Đối tượng bộ nhớ đại diện cho một lỗi được phát hiện trong ván cờ.

    (Chưa phải SQLAlchemy model; độc lập với database persistence).
    """

    game_id: int
    ply: int
    move_number: int
    move_san: str
    move_uci: str
    fen: str
    win_before: float
    win_after: float
    win_loss: float
    skill_id: str
    motif: str
    game_phase: str
    best_move: str | None = None
    refutation_move: str | None = None


class GameAnalyzer(Protocol):
    """Giao diện bộ phân tích ván cờ."""

    def analyze_game(
        self,
        game_id: int,
        pgn: str,
        player_username: str,
    ) -> list[GameMistake]:
        """Phân tích một ván cờ và trả về danh sách các lỗi của người chơi."""
        ...


class PgnGameAnalyzer:
    """Bộ phân tích ván cờ dựa trên đánh giá có sẵn trong PGN (Lichess evals).

    Quy tắc quan trọng:
    - Không tự suy diễn hay đoán mò best_move / refutation_move từ %eval.
    - Truyền best_move=None, refutation_move=None vào detect_motif()
      để Seam 2 áp dụng fallback chuẩn về 'missed_tactic'.
    """

    def analyze_game(
        self,
        game_id: int,
        pgn: str,
        player_username: str,
    ) -> list[GameMistake]:
        parsed_items = parse_game_evaluations(pgn, player_username)
        mistakes: list[GameMistake] = []

        for item in parsed_items:
            # 1. Phát hiện lỗi qua Seam 1 (chuẩn hóa POV, áp dụng bộ lọc clock và thế cờ ngã ngũ)
            mistake_res = detect_mistake(item.evaluation)
            if mistake_res is None:
                continue

            # 2. Nhận diện motif qua Seam 2 (không tự suy diễn best_move/refutation_move)
            context = MoveContext(
                board_before=item.board_before,
                played_move=item.move,
                player_color=item.evaluation.player_color,
                best_move=None,
                refutation_move=None,
            )
            motif_res = detect_motif(context)

            # 3. Phân loại giai đoạn ván cờ trên board_before qua Seam 2
            game_phase = classify_game_phase(item.board_before)

            # win_loss là số dương (win_before - win_after >= 20.0)
            win_loss = mistake_res.win_before - mistake_res.win_after

            mistakes.append(
                GameMistake(
                    game_id=game_id,
                    ply=item.ply,
                    move_number=item.move_number,
                    move_san=item.san,
                    move_uci=item.move.uci(),
                    fen=item.board_before.fen(),
                    win_before=mistake_res.win_before,
                    win_after=mistake_res.win_after,
                    win_loss=win_loss,
                    skill_id=motif_res.skill_id,
                    motif=motif_res.motif,
                    game_phase=game_phase,
                    best_move=None,
                    refutation_move=None,
                )
            )

        # Sắp xếp theo ply tăng dần
        mistakes.sort(key=lambda m: m.ply)
        return mistakes


class FakeGameAnalyzer:
    """Test double của GameAnalyzer phục vụ kiểm thử tích hợp không mock nội bộ.

    Hỗ trợ:
    - Cấu hình sẵn danh sách GameMistake theo game_id.
    - Mô phỏng lỗi phân tích (failing_game_ids).
    - Không phụ thuộc engine, PGN hay database.
    - Không làm rò rỉ trạng thái nội bộ (trả về bản sao).
    """

    def __init__(
        self,
        configured_mistakes: dict[int, list[GameMistake]] | None = None,
        default_mistakes: list[GameMistake] | None = None,
        failing_game_ids: set[int] | None = None,
    ) -> None:
        self.configured_mistakes = {
            k: list(v) for k, v in (configured_mistakes or {}).items()
        }
        self.default_mistakes = list(default_mistakes or [])
        self.failing_game_ids = set(failing_game_ids or ())
        self.call_count: int = 0

    def analyze_game(
        self,
        game_id: int,
        pgn: str,
        player_username: str,
    ) -> list[GameMistake]:
        self.call_count += 1
        if game_id in self.failing_game_ids:
            raise RuntimeError(f"Simulated analysis failure for game {game_id}")

        if game_id in self.configured_mistakes:
            return list(self.configured_mistakes[game_id])
        return list(self.default_mistakes)
