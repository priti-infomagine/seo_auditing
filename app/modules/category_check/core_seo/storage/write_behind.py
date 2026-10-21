"""
Write-behind store for Core SEO audit persistence.

Architecture:
    Redis is the primary write target (fast, in-memory, with TTL for
    recent data). The DB is updated asynchronously via a write-behind
    policy: changes are buffered in Redis first, then flushed to the
    database in a background loop or on explicit flush.

Redis TTL:
    All audit-related keys in Redis have a TTL of REDIS_AUDIT_TTL_SECONDS
    (default: 3600 seconds = 1 hour).
"""
from __future__ import annotations

import json
import threading
from typing import Any

from app.core.datetime_utils import utc_now
from app.core.logger import logger

from ..db_models.audit_db import AuditCheck, AuditStatus
from ..events import EventBus, _redis_key, REDIS_TTL_SECONDS
from ..models import PageScore

REDIS_AUDIT_TTL_SECONDS: int = REDIS_TTL_SECONDS


class WriteBehindStore:
    """Buffers audit state in Redis and flushes to DB asynchronously.

    Write-behind policy:
        - write_state() / write_result() sync state to Redis immediately for
          cross-process real-time visibility.
        - flush() syncs dirty audit IDs from Redis to the database.
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

    # ── Redis write (immediate, with TTL) ─────────────────────────────

    @classmethod
    def write_state(
        cls,
        audit_id: str,
        state: dict[str, Any],
    ) -> None:
        """Write audit state to Redis (immediate) with TTL."""
        EventBus.set_audit_state(audit_id, **state)

    @classmethod
    def write_result(
        cls,
        audit_id: str,
        page_score: PageScore,
        crawl_result: Any,
    ) -> None:
        """Buffer a completed page result in Redis pages hash.

        The page result is stored as a JSON string under
        core_seo:audit:{audit_id}:pages with the URL as the hash field key.
        """
        page_data = {
            "url": page_score.url,
            "passed": page_score.passed,
            "failed": page_score.failed,
            "total": page_score.total,
            "pass_percentage": page_score.pass_percentage,
            "crawl_success": crawl_result.success if crawl_result else False,
            "status_code": crawl_result.status_code if crawl_result else 0,
            "response_time_ms": crawl_result.response_time_ms if crawl_result else 0,
            "timestamp": utc_now().isoformat(),
            "rule_results": [
                {
                    "rule_id": r.rule_id,
                    "name": r.name,
                    "passed": r.passed,
                    "severity": r.severity,
                    "message": r.message,
                    "recommendation": r.recommendation,
                    "details": r.details or {},
                }
                for r in page_score.rule_results
            ],
        }

        try:
            EventBus.set_page_state(audit_id, page_score.url, page_data)
        except Exception as exc:
            logger.debug("WriteBehindStore write_result failed: %s", exc)

    @classmethod
    def get_redis_ttl(cls) -> int:
        """Return the current Redis TTL for audit keys."""
        return REDIS_AUDIT_TTL_SECONDS

    # ── DB operations (write-behind, deferred) ──────────────────────────

    def flush_audit_to_db(self, audit_id: str) -> bool:
        """Flush a single audit's Redis state to the database synchronously.

        Returns True on success.
        """
        try:
            from app.shared.tasks.db import run_async
        except ImportError:
            logger.warning("WriteBehindStore: DB flush skipped (no run_async)")
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
                        "WriteBehindStore: flushed audit %s to DB (status=%s, passed=%s, failed=%s)",
                        audit_id,
                        record.status.value,
                        record.rules_passed,
                        record.rules_failed,
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
        result.rules_passed = counters.get("rules_passed", 0)
        result.rules_failed = counters.get("rules_failed", 0)
        total_rules = counters.get("rules_total", 0)
        result.pass_percentage = round(
            result.rules_passed / total_rules * 100, 1
        ) if total_rules else 0.0

        if state.get("status") == "completed" and report_dict:
            result.mark_completed(
                rules_passed=result.rules_passed,
                rules_failed=result.rules_failed,
                pass_percentage=result.pass_percentage,
                crawled_pages=result.crawled_pages,
                total_pages=result.total_pages,
                pages_failed=result.pages_failed,
                report=report_dict,
            )

        return result

    def mark_dirty(self, audit_id: str) -> None:
        """Mark an audit_id as needing a DB flush."""
        with self._dirty_lock:
            self._dirty_audits.add(audit_id)

    def flush(self) -> int:
        """Flush all dirty audits to the database synchronously.

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

    # ── Background flush loop ─────────────────────────────────────────

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
        self.flush()
        logger.info("WriteBehindStore: background flush stopped")

    # ── Context manager support ───────────────────────────────────────

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


# ── Module-level shared instance ────────────────────────────────────────

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


__all__ = [
    "REDIS_AUDIT_TTL_SECONDS",
    "WriteBehindStore",
    "get_write_behind_store",
]
