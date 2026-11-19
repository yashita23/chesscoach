from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import threading
import time
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from chesscoach.analysis.analyzer import GameAnalyzer, GameMistake
from chesscoach.analysis.storage import mark_analysis_failed, save_game_mistakes
from chesscoach.db import Game, LinkedAccount
from chesscoach.games_source import GameSource, RateLimitError, SourceNetworkError

log = logging.getLogger(__name__)

# Registry lưu RLock theo từng engine để đồng bộ hóa SQLite in-memory / StaticPool
_engine_locks: dict[int, threading.RLock] = {}
_registry_lock = threading.Lock()


def get_engine_lock(session_factory: sessionmaker[Session]) -> threading.RLock:
    """Lấy hoặc tạo RLock dùng chung cho tất cả Session/SyncEngine kết nối tới cùng một Engine."""
    bind = getattr(session_factory, "kw", {}).get("bind") or getattr(session_factory, "bind", None)
    key = id(bind) if bind is not None else id(session_factory)
    with _registry_lock:
        if key not in _engine_locks:
            _engine_locks[key] = threading.RLock()
        return _engine_locks[key]


class AlreadySyncingError(Exception):
    """Người chơi đang có một tiến trình đồng bộ ván đang chạy."""


class AccountNotLinkedError(Exception):
    """Chưa liên kết tài khoản trên nền tảng này."""


@dataclass
class SyncJob:
    """Tiến trình đồng bộ ván của người chơi."""

    player_id: int
    platform: str
    status: str = "pending"  # "idle", "pending", "running", "completed", "failed"
    current: int = 0
    total: int = 0
    new_games_count: int = 0
    analyzed_games_count: int = 0
    error: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


class SyncEngine:
    """Quản lý các job nền đồng bộ ván từ tài khoản liên kết (Lichess/Chess.com)."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        max_retries: int = 2,
        retry_delay_sec: float = 1.0,
        analyzer: GameAnalyzer | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.max_retries = max_retries
        self.retry_delay_sec = retry_delay_sec
        self.analyzer = analyzer
        self._jobs: dict[int, SyncJob] = {}
        self._threads: dict[int, threading.Thread] = {}
        self._lock = threading.Lock()
        self._db_lock = get_engine_lock(session_factory)

    def get_status(self, player_id: int) -> SyncJob:
        with self._lock:
            job = self._jobs.get(player_id)
            if job is not None:
                return job
            return SyncJob(player_id=player_id, platform="", status="idle")

    def start_sync(self, player_id: int, platform: str, source: GameSource) -> SyncJob:
        """Bắt đầu đồng bộ ván cho người chơi trong luồng nền.

        Mỗi người chơi chỉ có tối đa một job tại một thời điểm.
        """
        with self._lock:
            existing = self._jobs.get(player_id)
            if existing is not None and existing.status in ("pending", "running"):
                raise AlreadySyncingError("Bạn đang có một tiến trình đồng bộ ván đang chạy")

            job = SyncJob(player_id=player_id, platform=platform, status="pending")
            self._jobs[player_id] = job

            thread = threading.Thread(
                target=self._run_sync,
                args=(job, source),
                name=f"sync-{player_id}-{platform}",
                daemon=True,
            )
            self._threads[player_id] = thread
            thread.start()
            return job

    def wait_for_job(self, player_id: int, timeout: float = 10.0) -> None:
        """Chờ job của người chơi hoàn thành (dùng trong test)."""
        with self._lock:
            thread = self._threads.get(player_id)
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def _run_sync(self, job: SyncJob, source: GameSource) -> None:
        try:
            self._do_sync(job, source)
        except Exception as e:
            log.exception("Lỗi trong luồng đồng bộ ván: %s", e)
            job.status = "failed"
            job.error = f"Lỗi đồng bộ: {e}"
            job.finished_at = datetime.now(timezone.utc)

    def _claim_game_for_analysis(self, game_id: int) -> bool:
        """Atomic claim ván cờ trước khi chạy analyzer.

        Thực thi transaction UPDATE hoàn chỉnh và commit trước khi nhả lock.
        """
        with self._db_lock:
            with self.session_factory() as session:
                with session.begin():
                    res = session.execute(
                        update(Game)
                        .where(
                            Game.id == game_id,
                            Game.analysis_status.in_(["pending", "failed"]),
                        )
                        .values(analysis_status="analyzing")
                    )
                    rowcount = getattr(res, "rowcount", 0)
                    return bool(rowcount > 0)

    def _do_sync(self, job: SyncJob, source: GameSource) -> None:
        job.status = "running"
        player_id = job.player_id
        platform = job.platform

        with self._db_lock:
            with self.session_factory() as db:
                account = db.scalars(
                    select(LinkedAccount).where(
                        LinkedAccount.player_id == player_id,
                        LinkedAccount.platform == platform,
                    )
                ).one_or_none()

                if account is None:
                    job.status = "failed"
                    job.error = f"Chưa liên kết tài khoản {platform}"
                    job.finished_at = datetime.now(timezone.utc)
                    return

                username = account.username
                since = account.last_game_at
                if since is not None and since.tzinfo is None:
                    since = since.replace(tzinfo=timezone.utc)
                account_id = account.id

        # Tải danh sách ván với cơ chế retry khi gặp lỗi 429
        games = None
        for attempt in range(self.max_retries):
            try:
                games = source.fetch_games(username=username, since=since)
                break
            except RateLimitError as e:
                log.warning("Lichess 429 rate limit (lần %d/%d): %s", attempt + 1, self.max_retries, e)
                if attempt + 1 < self.max_retries:
                    time.sleep(self.retry_delay_sec)
                else:
                    job.status = "failed"
                    job.error = str(e) or "Lichess: Quá nhiều yêu cầu (HTTP 429). Vui lòng thử lại sau."
                    job.finished_at = datetime.now(timezone.utc)
                    return
            except (SourceNetworkError, Exception) as e:
                log.warning("Lỗi khi tải ván từ nguồn: %s", e)
                job.status = "failed"
                job.error = str(e)
                job.finished_at = datetime.now(timezone.utc)
                return

        if games is None:
            job.status = "failed"
            job.error = "Không nhận được dữ liệu ván từ nguồn"
            job.finished_at = datetime.now(timezone.utc)
            return

        job.total = len(games)
        new_count = 0
        analyzed_count = 0
        latest_played_at: datetime | None = since

        # Lưu từng ván cờ vào DB và phân tích nếu có analyzer
        for raw in games:
            game_id: int | None = None
            need_analysis = False
            try:
                with self._db_lock:
                    with self.session_factory() as db:
                        existing_game = db.scalar(
                            select(Game).where(
                                Game.player_id == player_id,
                                Game.platform == platform,
                                Game.platform_game_id == raw.game_id,
                            )
                        )
                        if existing_game is None:
                            has_evals = bool(raw.evals and raw.evals.get("has_evals"))
                            game = Game(
                                player_id=player_id,
                                account_id=account_id,
                                platform=platform,
                                platform_game_id=raw.game_id,
                                perf_type=raw.perf_type,
                                played_at=raw.played_at,
                                pgn=raw.pgn,
                                has_evals=has_evals,
                                analysis_status="pending",
                            )
                            db.add(game)
                            db.commit()
                            game_id = game.id
                            new_count += 1
                            need_analysis = True
                        else:
                            game_id = existing_game.id
                            need_analysis = existing_game.analysis_status in ("pending", "failed")

                if latest_played_at is None or raw.played_at > latest_played_at:
                    latest_played_at = raw.played_at
            except Exception as e:
                log.error("Lỗi khi lưu ván %s: %s", raw.game_id, e)
                job.status = "failed"
                job.error = f"Lỗi khi lưu ván cờ: {e}"
                job.finished_at = datetime.now(timezone.utc)
                return

            # Phân tích ván cờ nếu có analyzer và ván chưa completed
            if self.analyzer is not None and need_analysis and game_id is not None:
                if self._claim_game_for_analysis(game_id):
                    analysis_ok = False
                    mistakes: list[GameMistake] = []
                    try:
                        mistakes = self.analyzer.analyze_game(
                            game_id=game_id,
                            pgn=raw.pgn,
                            player_username=username,
                        )
                        analysis_ok = True
                    except Exception as e:
                        log.warning("Lỗi khi phân tích ván %s (id=%s): %s", raw.game_id, game_id, e)
                        try:
                            with self._db_lock:
                                mark_analysis_failed(self.session_factory, game_id, error=str(e))
                        except Exception as mark_err:
                            log.error("Lỗi khi đánh dấu ván failed: %s", mark_err)

                    if analysis_ok:
                        try:
                            with self._db_lock:
                                save_game_mistakes(self.session_factory, game_id, player_id, mistakes)
                            analyzed_count += 1
                        except Exception as storage_err:
                            log.error("Lỗi khi lưu mistakes ván %s vào CSDL: %s", raw.game_id, storage_err)
                            # Rollback trạng thái analyzing về pending để có thể retry
                            try:
                                with self._db_lock:
                                    with self.session_factory() as session:
                                        with session.begin():
                                            session.execute(
                                                update(Game)
                                                .where(Game.id == game_id, Game.analysis_status == "analyzing")
                                                .values(analysis_status="pending")
                                            )
                            except Exception:
                                pass

            job.current += 1

        # Cập nhật mốc đồng bộ thành công vào tài khoản liên kết
        with self._db_lock:
            with self.session_factory() as db:
                values: dict[str, Any] = {"last_synced_at": datetime.now(timezone.utc)}
                if latest_played_at is not None:
                    values["last_game_at"] = latest_played_at
                db.execute(
                    update(LinkedAccount)
                    .where(LinkedAccount.id == account_id)
                    .values(**values)
                )
                db.commit()

        job.new_games_count = new_count
        job.analyzed_games_count = analyzed_count
        job.status = "completed"
        job.finished_at = datetime.now(timezone.utc)

    def analyze_unprocessed_games(
        self,
        player_id: int,
        limit: int | None = None,
        include_stuck_analyzing: bool = False,
    ) -> int:
        """Phân tích các ván của người chơi đang ở trạng thái pending hoặc failed.

        Trả về số ván cờ phân tích thành công (chuyển sang completed).
        """
        if self.analyzer is None:
            return 0

        with self._db_lock:
            with self.session_factory() as session:
                # Nếu cho phép thu hồi ván bị kẹt ở analyzing (do worker crash):
                if include_stuck_analyzing:
                    session.execute(
                        update(Game)
                        .where(Game.player_id == player_id, Game.analysis_status == "analyzing")
                        .values(analysis_status="pending")
                    )
                    session.commit()

                # Lấy map username theo platform
                accounts = {
                    acc.platform: acc.username
                    for acc in session.scalars(
                        select(LinkedAccount).where(LinkedAccount.player_id == player_id)
                    ).all()
                }

                # Lấy danh sách ván pending/failed sắp xếp theo played_at ASC, id ASC
                query = (
                    select(Game.id, Game.platform, Game.pgn)
                    .where(
                        Game.player_id == player_id,
                        Game.analysis_status.in_(["pending", "failed"]),
                    )
                    .order_by(Game.played_at.asc(), Game.id.asc())
                )
                if limit is not None and limit > 0:
                    query = query.limit(limit)

                candidates = session.execute(query).all()

        success_count = 0
        for game_id, platform, pgn in candidates:
            username = accounts.get(platform, "")
            if not self._claim_game_for_analysis(game_id):
                continue

            analysis_ok = False
            mistakes: list[GameMistake] = []
            try:
                mistakes = self.analyzer.analyze_game(
                    game_id=game_id,
                    pgn=pgn,
                    player_username=username,
                )
                analysis_ok = True
            except Exception as e:
                log.warning("Lỗi phân tích ván id=%s: %s", game_id, e)
                try:
                    with self._db_lock:
                        mark_analysis_failed(self.session_factory, game_id, error=str(e))
                except Exception:
                    pass

            if analysis_ok:
                try:
                    with self._db_lock:
                        save_game_mistakes(self.session_factory, game_id, player_id, mistakes)
                    success_count += 1
                except Exception as storage_err:
                    log.error("Lỗi khi lưu mistakes ván id=%s: %s", game_id, storage_err)
                    try:
                        with self._db_lock:
                            with self.session_factory() as session:
                                with session.begin():
                                    session.execute(
                                        update(Game)
                                        .where(Game.id == game_id, Game.analysis_status == "analyzing")
                                        .values(analysis_status="pending")
                                    )
                    except Exception:
                        pass

        return success_count
