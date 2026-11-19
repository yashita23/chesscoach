"""Module persistence cho kết quả phân tích ván cờ (Seam 3D).

Triển khai lưu trữ kết quả phân tích theo chiến lược Transactional Replace:
- Toàn bộ dữ liệu được validate chặt chẽ trước khi thao tác CSDL.
- Xóa các mistake cũ của ván và ghi mistake mới trong cùng một transaction.
- Nếu gặp lỗi ở bất kỳ bước nào, transaction tự động rollback, bảo toàn 100% dữ liệu cũ.
- Danh sách lỗi rỗng ([]) được xử lý hợp lệ như ván không có lỗi (đánh dấu completed).
- Cung cấp hàm riêng mark_analysis_failed() để đánh dấu phân tích thất bại mà không làm mất dữ liệu cũ.
"""

from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from chesscoach.analysis.analyzer import GameMistake
from chesscoach.db import Game, GameMistakeRecord
from chesscoach.skills import SKILLS


VALID_SKILL_IDS: frozenset[str] = frozenset(s.id for s in SKILLS)
VALID_GAME_PHASES: frozenset[str] = frozenset({"opening", "middlegame", "endgame"})


class AnalysisValidationError(ValueError):
    """Lỗi tính hợp lệ của dữ liệu phân tích ván cờ trước khi lưu DB."""

    pass


def _execute_save(
    session: Session,
    game_id: int,
    player_id: int,
    mistakes: Sequence[GameMistake],
) -> list[GameMistakeRecord]:
    # 1. Validation trước khi thực hiện bất kỳ thao tác CSDL nào
    game = session.get(Game, game_id)
    if game is None:
        raise AnalysisValidationError(f"Game id {game_id} không tồn tại")
    if game.player_id != player_id:
        raise AnalysisValidationError(
            f"player_id {player_id} không khớp với người chơi sở hữu ván cờ ({game.player_id})"
        )

    for m in mistakes:
        if m.skill_id not in VALID_SKILL_IDS:
            raise AnalysisValidationError(f"skill_id '{m.skill_id}' không hợp lệ")
        if m.game_phase not in VALID_GAME_PHASES:
            raise AnalysisValidationError(f"game_phase '{m.game_phase}' không hợp lệ")
        if m.ply < 1:
            raise AnalysisValidationError(f"ply phải >= 1 (nhận {m.ply})")
        if not (0.0 <= m.win_before <= 100.0) or not (0.0 <= m.win_after <= 100.0):
            raise AnalysisValidationError(
                f"win_before ({m.win_before}) và win_after ({m.win_after}) phải trong khoảng [0, 100]"
            )
        if abs(m.win_loss - (m.win_before - m.win_after)) > 0.01:
            raise AnalysisValidationError(
                f"win_loss ({m.win_loss}) không khớp win_before - win_after ({m.win_before - m.win_after:.1f})"
            )

    # 2. Xóa các mistakes cũ của game_id
    session.execute(
        delete(GameMistakeRecord).where(GameMistakeRecord.game_id == game_id)
    )

    # 3. Ghi danh sách mistakes mới (nếu có), sắp xếp theo ply tăng dần
    records: list[GameMistakeRecord] = []
    sorted_mistakes = sorted(mistakes, key=lambda x: x.ply)
    for m in sorted_mistakes:
        record = GameMistakeRecord(
            game_id=game_id,
            player_id=player_id,
            ply=m.ply,
            move_number=m.move_number,
            move_san=m.move_san,
            move_uci=m.move_uci,
            fen=m.fen,
            win_before=m.win_before,
            win_after=m.win_after,
            win_loss=m.win_loss,
            skill_id=m.skill_id,
            motif=m.motif,
            game_phase=m.game_phase,
            best_move=m.best_move,
            refutation_move=m.refutation_move,
        )
        session.add(record)
        records.append(record)

    # 4. Cập nhật trạng thái ván cờ sang completed và thời điểm analyzed_at
    game.analysis_status = "completed"
    game.analyzed_at = datetime.now(timezone.utc)

    # Flush để kích hoạt DDL constraints ngay trong transaction/savepoint này
    session.flush()

    return records


def save_game_mistakes(
    db: Session | sessionmaker[Session],
    game_id: int,
    player_id: int,
    mistakes: Sequence[GameMistake],
) -> list[GameMistakeRecord]:
    """Lưu danh sách lỗi theo chiến lược Transactional Replace nguyên tử."""
    if isinstance(db, sessionmaker):
        with db() as session:
            with session.begin():
                return _execute_save(session, game_id, player_id, mistakes)
    else:
        if db.in_transaction():
            with db.begin_nested():
                return _execute_save(db, game_id, player_id, mistakes)
        else:
            with db.begin():
                return _execute_save(db, game_id, player_id, mistakes)


def get_game_mistakes(
    db: Session | sessionmaker[Session],
    game_id: int,
) -> list[GameMistakeRecord]:
    """Lấy danh sách lỗi của ván cờ, sắp xếp tăng dần theo ply."""

    def _fetch(session: Session) -> list[GameMistakeRecord]:
        return list(
            session.scalars(
                select(GameMistakeRecord)
                .where(GameMistakeRecord.game_id == game_id)
                .order_by(GameMistakeRecord.ply.asc())
            ).all()
        )

    if isinstance(db, sessionmaker):
        with db() as session:
            return _fetch(session)
    return _fetch(db)


def mark_analysis_failed(
    db: Session | sessionmaker[Session],
    game_id: int,
    error: str | None = None,
) -> None:
    """Đánh dấu ván cờ phân tích thất bại mà không làm ảnh hưởng mistakes cũ."""

    def _mark(session: Session) -> None:
        game = session.get(Game, game_id)
        if game is not None:
            game.analysis_status = "failed"
            game.analyzed_at = datetime.now(timezone.utc)
            session.flush()

    if isinstance(db, sessionmaker):
        with db() as session:
            with session.begin():
                _mark(session)
    else:
        if db.in_transaction():
            with db.begin_nested():
                _mark(db)
        else:
            with db.begin():
                _mark(db)
