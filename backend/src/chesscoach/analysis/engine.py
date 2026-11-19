from dataclasses import dataclass
from typing import Protocol
import chess

from chesscoach.analysis.analyzer import GameMistake, PgnGameAnalyzer
from chesscoach.analysis.eval import Evaluation, MoveEvaluation, detect_mistake
from chesscoach.analysis.motifs import MoveContext, classify_game_phase, detect_motif
from chesscoach.analysis.parser import (
    NEUTRAL_BASELINE_EVAL,
    parse_raw_game_moves,
)


@dataclass(frozen=True)
class EngineEvaluation:
    """Kết quả đánh giá thế cờ từ engine cờ vua (luôn chuẩn hóa theo White POV).

    Attributes:
        evaluation: Điểm đánh giá (cp hoặc mate theo White POV).
        best_move: Nước đi tối ưu engine tìm được cho bên đang tới lượt.
        depth: Độ sâu thực tế engine đạt được.
    """

    evaluation: Evaluation
    best_move: chess.Move | None = None
    depth: int = 10


class EngineAdapter(Protocol):
    """Giao diện bộ adapter kết nối engine cờ vua."""

    engine_name: str
    engine_version: str

    def evaluate_position(
        self,
        board: chess.Board,
        depth: int = 10,
        time_limit_seconds: float = 0.5,
    ) -> EngineEvaluation:
        """Đánh giá thế cờ theo White POV và tìm nước đi tối ưu."""
        ...


class CachedEngineAdapter:
    """Bộ bọc EngineAdapter với bộ nhớ đệm cache_key = (fen, depth, time_limit, name, version).

    Không lưu cache khi engine gặp lỗi hoặc timeout.
    """

    def __init__(
        self,
        engine: EngineAdapter,
        engine_name: str | None = None,
        engine_version: str | None = None,
    ) -> None:
        self.engine = engine
        self.engine_name: str = str(engine_name or getattr(engine, "engine_name", "engine"))
        self.engine_version: str = str(engine_version or getattr(engine, "engine_version", "1.0"))
        self._cache: dict[tuple[str, int, float, str, str], EngineEvaluation] = {}

    def evaluate_position(
        self,
        board: chess.Board,
        depth: int = 10,
        time_limit_seconds: float = 0.5,
    ) -> EngineEvaluation:
        key = (
            board.fen(),
            depth,
            time_limit_seconds,
            self.engine_name,
            self.engine_version,
        )
        if key in self._cache:
            return self._cache[key]

        # Gọi engine. Nếu gặp lỗi hoặc timeout, không bắt và không lưu cache
        result = self.engine.evaluate_position(
            board, depth=depth, time_limit_seconds=time_limit_seconds
        )
        self._cache[key] = result
        return result


class FakeEngineAdapter:
    """Test double của EngineAdapter phục vụ kiểm thử đơn vị và tích hợp.

    Hỗ trợ:
    - Cấu hình sẵn EngineEvaluation theo FEN.
    - Đếm số lần gọi (call_count).
    - Mô phỏng timeout hoặc lỗi ném ngoại lệ.
    """

    def __init__(
        self,
        evaluations: dict[str, EngineEvaluation] | None = None,
        default_eval: EngineEvaluation | None = None,
        failing_fens: set[str] | None = None,
        engine_name: str = "fake_engine",
        engine_version: str = "1.0",
    ) -> None:
        self.evaluations = dict(evaluations or {})
        self.default_eval = default_eval
        self.failing_fens = set(failing_fens or ())
        self.engine_name = engine_name
        self.engine_version = engine_version
        self.call_count = 0

    def evaluate_position(
        self,
        board: chess.Board,
        depth: int = 10,
        time_limit_seconds: float = 0.5,
    ) -> EngineEvaluation:
        self.call_count += 1
        fen = board.fen()
        if fen in self.failing_fens:
            raise RuntimeError(f"Simulated engine failure for FEN {fen}")

        if fen in self.evaluations:
            return self.evaluations[fen]

        if self.default_eval is not None:
            return self.default_eval

        return EngineEvaluation(
            evaluation=Evaluation(cp=0),
            best_move=next(iter(board.legal_moves), None),
            depth=depth,
        )


class EnrichedGameAnalyzer:
    """Bộ phân tích ván cờ kết hợp PGN evals và EngineAdapter.

    Chính sách:
    1. Ưu tiên PGN eval: Nếu node đã có eval hợp lệ trong PGN thì không gọi engine.
    2. Bổ sung node thiếu: Gọi engine đánh giá các node thiếu trong PGN.
    3. Tìm best_move / refutation_move: Chỉ gọi engine tại vị trí xảy ra mistake
       (board_before tìm best_move, board_after tìm refutation_move).
    4. Không có engine: Giữ nguyên hành vi an toàn của Seam 3B.
    """

    def __init__(
        self,
        engine: EngineAdapter | None = None,
        depth: int = 10,
        time_limit_seconds: float = 0.5,
    ) -> None:
        self.engine = engine
        self.depth = depth
        self.time_limit_seconds = time_limit_seconds

    def analyze_game(
        self,
        game_id: int,
        pgn: str,
        player_username: str,
    ) -> list[GameMistake]:
        # Khi không cấu hình engine, giữ nguyên 100% hành vi an toàn của Seam 3B
        if self.engine is None:
            return PgnGameAnalyzer().analyze_game(game_id, pgn, player_username)

        raw_moves = parse_raw_game_moves(pgn, player_username)
        if not raw_moves:
            return []

        # Lưu trữ eval của từng node theo ply (0 là thế cờ xuất phát ban đầu)
        node_evals: dict[int, Evaluation] = {0: NEUTRAL_BASELINE_EVAL}
        for rm in raw_moves:
            if rm.evaluation_after is not None:
                node_evals[rm.ply] = rm.evaluation_after

        mistakes: list[GameMistake] = []

        for rm in raw_moves:
            # 1. Bổ sung eval_before nếu thiếu
            eval_before = node_evals.get(rm.ply - 1)
            if eval_before is None:
                engine_res = self.engine.evaluate_position(
                    rm.board_before,
                    depth=self.depth,
                    time_limit_seconds=self.time_limit_seconds,
                )
                eval_before = engine_res.evaluation
                node_evals[rm.ply - 1] = eval_before

            # 2. Bổ sung eval_after nếu thiếu
            eval_after = node_evals.get(rm.ply)
            if eval_after is None:
                b_after = rm.board_before.copy()
                b_after.push(rm.move)
                engine_res = self.engine.evaluate_position(
                    b_after,
                    depth=self.depth,
                    time_limit_seconds=self.time_limit_seconds,
                )
                eval_after = engine_res.evaluation
                node_evals[rm.ply] = eval_after

            # 3. Chỉ xét các nước đi của người chơi
            if not rm.is_player_move:
                continue

            move_eval = MoveEvaluation(
                player_color=rm.player_color,
                before=eval_before,
                after=eval_after,
                clock_seconds=rm.clock_seconds,
            )
            mistake_res = detect_mistake(move_eval)
            if mistake_res is None:
                continue

            # 4. Khi xác nhận mistake, truy vấn engine tìm best_move và refutation_move
            # - best_move tại board_before (nước tối ưu người chơi nên đi)
            eng_before = self.engine.evaluate_position(
                rm.board_before,
                depth=self.depth,
                time_limit_seconds=self.time_limit_seconds,
            )
            best_move = eng_before.best_move

            # - refutation_move tại board_after (nước đối thủ trừng phạt)
            b_after = rm.board_before.copy()
            b_after.push(rm.move)
            eng_after = self.engine.evaluate_position(
                b_after,
                depth=self.depth,
                time_limit_seconds=self.time_limit_seconds,
            )
            refutation_move = eng_after.best_move
            if refutation_move is not None and refutation_move not in b_after.legal_moves:
                refutation_move = None

            # 5. Nhận diện motif và phân loại giai đoạn ván cờ
            context = MoveContext(
                board_before=rm.board_before,
                played_move=rm.move,
                player_color=rm.player_color,
                best_move=best_move,
                refutation_move=refutation_move,
            )
            motif_res = detect_motif(context)
            game_phase = classify_game_phase(rm.board_before)
            win_loss = mistake_res.win_before - mistake_res.win_after

            mistakes.append(
                GameMistake(
                    game_id=game_id,
                    ply=rm.ply,
                    move_number=rm.move_number,
                    move_san=rm.san,
                    move_uci=rm.move.uci(),
                    fen=rm.board_before.fen(),
                    win_before=mistake_res.win_before,
                    win_after=mistake_res.win_after,
                    win_loss=win_loss,
                    skill_id=motif_res.skill_id,
                    motif=motif_res.motif,
                    game_phase=game_phase,
                    best_move=best_move.uci() if best_move else None,
                    refutation_move=refutation_move.uci() if refutation_move else None,
                )
            )

        mistakes.sort(key=lambda m: m.ply)
        return mistakes
