from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import threading
import time
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from chesscoach.db import Game, LinkedAccount
from chesscoach.games_source import GameSource, RateLimitError, SourceNetworkError

log = logging.getLogger(__name__)


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
    ) -> None:
        self.session_factory = session_factory
        self.max_retries = max_retries
        self.retry_delay_sec = retry_delay_sec
        self._jobs: dict[int, SyncJob] = {}
        self._threads: dict[int, threading.Thread] = {}
        self._lock = threading.Lock()

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

    def _do_sync(self, job: SyncJob, source: GameSource) -> None:
        job.status = "running"
        player_id = job.player_id
        platform = job.platform

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
        latest_played_at: datetime | None = since

        # Lưu từng ván cờ vào DB
        for raw in games:
            try:
                with self.session_factory() as db:
                    exists = db.scalar(
                        select(Game.id).where(
                            Game.player_id == player_id,
                            Game.platform == platform,
                            Game.platform_game_id == raw.game_id,
                        )
                    )
                    if not exists:
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
                        )
                        db.add(game)
                        db.commit()
                        new_count += 1

                if latest_played_at is None or raw.played_at > latest_played_at:
                    latest_played_at = raw.played_at
            except Exception as e:
                log.error("Lỗi khi lưu ván %s: %s", raw.game_id, e)
                job.status = "failed"
                job.error = f"Lỗi khi lưu ván cờ: {e}"
                job.finished_at = datetime.now(timezone.utc)
                return

            job.current += 1

        # Cập nhật mốc đồng bộ thành công vào tài khoản liên kết
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
        job.status = "completed"
        job.finished_at = datetime.now(timezone.utc)
