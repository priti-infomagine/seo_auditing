"""
Write-behind store for Core SEO audit persistence.

Architecture:
    Redis is the primary write target (fast, in-memory, with TTL for
    recent data). The DB is updated asynchronously via a write-behind
    policy: changes are buffered in Redis first, then flushed to the
    database in a background loop or on explicit flush.

    This ensures:
      - Real-time audit progress is visible across processes (Redis)
      - DB writes are batched and non-blocking (write-behind)
      - Stale audit data auto-expires from Redis after TTL seconds

Redis TTL:
    All audit-related keys in Redis have a TTL of REDIS_AUDIT_TTL_SECONDS
    (default: 3600 seconds = 1 hour). This ensures stale audit state
    and events don't accumulate indefinitely.
"""
from __future__ import annotations

import json
import threading
from typing import Any

from app.core.datetime_utils import utc_now
from app.core.logger import logger

from ..db_models.audit_db import AuditCheck, AuditStatus
from ..events import EventBus
from ..models import PageScore

# Redis TTL: maximum 1 hour for all audit-related Redis keys.
REDIS_AUDIT_TTL_SECONDS: int = 3600


class WriteBehindStore:
    """Buffers audit state in Redis and flushes to DB asynchronously.

    Write-behind policy:
        - write_state() / write_result() update Redis immediately for
          cross-process real-time visibility (used by web API).
        - A background flush loop periodically syncs dirty audit IDs
          from Redis to the database.
        - flush() can also be called explicitly (e.g., after audit
          completion in the Celery chord callback).

    Thread-safety:
        The flush loop runs in a daemon thread to avoid blocking the
        main event loop. DB sessions are created per-flush to avoid
        connection sharing issues across threads/processes.
    """

    def __init__(
        self,
        flush_interval: float = 30.0,
        redis_ttl: int = REDIS_AUDIT_TTL_SECONDS,
    ):
        self._flush_interval = flush_interval
        self._redis_ttl = redis_ttl
        self._dirty_audits: set[str] = set()
        self._dirty_lock = threading.Lock()
        self._flush_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ── Redis write (immediate, with TTL) ─────────────────────────────────

    @classmethod
    def write_state(
        cls,
        audit_id: str,
        state: dict[str, Any],
    ) -> None:
        """Write audit state to Redis (immediate) with TTL.

        This is the hot path — called during crawling to provide
        real-time progress visibility across processes.
        """
        EventBus.set_audit_state(audit_id, **state)

    @classmethod
    def write_result(
        cls,
        audit_id: str,
        page_score: PageScore,
        crawl_result: Any,
    ) -> None:
        """Buffer a completed page result in Redis.

        The page result is stored as a Redis list entry under
        core_seo:audit:{audit_id}:pages with the configured TTL.
        The DB flush happens asynchronously via the background loop.
        """
        client = _get_sync_redis()
        if client is None:
            return

        page_data = {
            "url": page_score.url,
            "score": page_score.score,
            "overall_score": page_score.overall_score,
            "grade": page_score.grade,
            "passed": page_score.passed,
            "failed": page_score.failed,
            "total_rules": page_score.total_rules,
            "crawl_success": crawl_result.success,
            "status_code": crawl_result.status_code,
            "response_time_ms": crawl_result.response_time_ms,
            "timestamp": utc_now().isoformat(),
        }

        try:
            from ..events import _redis_key
            key = _redis_key(audit_id, "pages")
            client.lpush(key, json.dumps(page_data, default=str))
            client.expire(key, REDIS_AUDIT_TTL_SECONDS)
        except Exception as exc:
            logger.debug("WriteBehindStore write_result failed: %s", exc)

    @classmethod
    def get_redis_ttl(cls) -> int:
        """Return the current Redis TTL for audit keys."""
        return REDIS_AUDIT_TTL_SECONDS

    # ── DB operations (write-behind, deferred) ────────────────────────────

    def _get_db_session(self) -> Any:
        """Create a new SQLAlchemy async session.

        Uses a fresh session per flush to avoid thread-safety issues
        with SQLAlchemy's async engine across worker processes.
        """
        try:
            from app.core.database import async_session_factory
            from app.shared.tasks.db import run_async

            return async_session_factory(), run_async
        except Exception as exc:
            logger.error("WriteBehindStore: cannot init DB session: %s", exc)
            return None, None

    async def _upsert_audit_record(
        self,
        session: Any,
        audit_id: str,
    ) -> AuditCheck | None:
        """Upsert an AuditCheck record from Redis state, return the ORM object."""
        counters = EventBus.get_counters(audit_id)
        state = EventBus.get_audit_state(audit_id)

        if not state:
            return None

        report_state = state.get("report")
        try:
            report_dict = json.loads(report_state) if isinstance(report_state, str) else report_state
        except (json.JSONDecodeError, TypeError):
            report_dict = None

        result = await session.get(AuditCheck, audit_id)
        if result is None:
            result = AuditCheck(
                audit_id=audit_id,
                start_url=state.get("start_url", ""),
                status=AuditStatus(state.get("status", AuditStatus.RUNNING.value)),
            )
            session.add(result)
        else:
            result.start_url = state.get("start_url", result.start_url)
            if state.get("status"):
                result.status = AuditStatus(state["status"])

        result.total_pages = counters.get("pages_discovered", state.get("total_pages", 0))
        result.crawled_pages = counters.get("pages_crawled", state.get("crawled_pages", 0))
        result.pages_failed = counters.get("pages_failed", 0)

        if state.get("overall_score") is not None:
            result.overall_score = float(state["overall_score"])
        if state.get("grade"):
            result.grade = state["grade"]

        if state.get("status") == "completed" and report_dict:
            result.mark_completed(
                overall_score=float(state.get("overall_score", 0.0)),
                grade=state.get("grade", "F"),
                crawled_pages=result.crawled_pages,
                total_pages=result.total_pages,
                pages_failed=result.pages_failed,
                report=report_dict,
            )

        return result

    def flush_audit_to_db(self, audit_id: str) -> bool:
        """Flush a single audit's Redis state to the database synchronously.

        Uses the shared Celery worker event loop if available, otherwise
        falls back to a fresh asyncio.run(). Returns True on success.
        """
        _, run_async = self._get_db_session()
        if run_async is None:
            logger.warning("WriteBehindStore: DB flush skipped (no DB session)")
            return False

        async def _do_flush():
            from app.core.database import async_session_factory

            async with async_session_factory() as session:
                try:
                    record = await self._upsert_audit_record(session, audit_id)
                    if record is None:
                        logger.info("WriteBehindStore: no state found for audit %s in Redis", audit_id)
                        return False
                    await session.commit()
                    logger.info(
                        "WriteBehindStore: flushed audit %s to DB (status=%s, score=%s)",
                        audit_id,
                        record.status.value,
                        record.overall_score,
                    )
                    return True
                except Exception as exc:
                    await session.rollback()
                    logger.error("WriteBehindStore: DB flush failed for %s: %s", audit_id, exc)
                    return False

        try:
            return run_async(_do_flush())
        except Exception as exc:
            logger.error("WriteBehindStore: flush error for %s: %s", audit_id, exc)
            return False

    def mark_dirty(self, audit_id: str) -> None:
        """Mark an audit_id as needing a DB flush."""
        with self._dirty_lock:
            self._dirty_audits.add(audit_id)

    def flush(self) -> int:
        """Flush all dirty audits to the database synchronously.

        Called by:
            - Background flush loop (periodically)
            - Explicit call after audit completion
            - Shutdown hook (best-effort final flush)

        Returns the number of audits successfully flushed.
        """
        with self._dirty_lock:
            dirty = self._dirty_audits.copy()
            self._dirty_audits.clear()

        flushed = 0
        for audit_id in dirty:
            if self.flush_audit_to_db(audit_id):
                flushed += 1
        return flushed

    # ── Background flush loop ─────────────────────────────────────────────

    def start_background_flush(self) -> None:
        """Start a daemon thread that periodically flushes dirty audits to DB."""
        if self._flush_thread is not None and self._flush_thread.is_alive():
            return

        self._stop_event.clear()
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            daemon=True,
            name="core_seo-write-behind",
        )
        self._flush_thread.start()
        logger.info(
            "WriteBehindStore: background flush started (interval=%ss)",
            self._flush_interval,
        )

    def _flush_loop(self) -> None:
        """Background thread: flush dirty audits periodically."""
        while not self._stop_event.wait(self._flush_interval):
            try:
                flushed = self.flush()
                if flushed > 0:
                    logger.info("WriteBehindStore: background flush completed (%d audits)", flushed)
            except Exception as exc:
                logger.warning("WriteBehindStore: background flush error: %s", exc)

    def stop(self) -> None:
        """Stop the background flush thread and do a final sync flush."""
        self._stop_event.set()
        if self._flush_thread is not None:
            self._flush_thread.join(timeout=10)
        # Final best-effort flush
        self.flush()
        logger.info("WriteBehindStore: background flush stopped")

    # ── Context manager support ───────────────────────────────────────────

    def __enter__(self) -> WriteBehindStore:
        self.start_background_flush()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.stop()


# ── Module-level shared instance ────────────────────────────────────

_default_store: WriteBehindStore | None = None
_store_lock = threading.Lock()


def get_write_behind_store() -> WriteBehindStore:
    """Get or create the singleton WriteBehindStore instance."""
    global _default_store
    if _default_store is None:
        with _store_lock:
            if _default_store is None:
                _default_store = WriteBehindStore()
    return _default_store


# ── Redis helpers ───────────────────────────────────────────────────

def _get_sync_redis() -> Any:
    """Return a synchronous Redis client or None if unavailable."""
    try:
        from redis import Redis as SyncRedis

        from app.core.config import settings

        return SyncRedis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=3,
            socket_connect_timeout=3,
        )
    except Exception:
        return None


__all__ = [
    "REDIS_AUDIT_TTL_SECONDS",
    "WriteBehindStore",
    "get_write_behind_store",
]
