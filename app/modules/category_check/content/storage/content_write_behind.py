"""
Write-behind store for Content audit persistence.

Mirrors core_seo's WriteBehindStore but writes to the content: Redis
namespace and the content_audit_checks DB table.
"""
from __future__ import annotations

import json
import threading
from typing import Any

from app.core.datetime_utils import utc_now
from app.core.logger import logger

from ..db_models.audit_db import ContentAuditCheck, ContentAuditStatus
from ..events import ContentEventBus
from ..models import PageScore

REDIS_CONTENT_TTL_SECONDS: int = 3600


class ContentWriteBehindStore:
    """Buffers content audit state in Redis (content: prefix) and flushes to DB."""

    def __init__(
        self,
        flush_interval: float = 30.0,
        redis_ttl: int = REDIS_CONTENT_TTL_SECONDS,
    ):
        self._flush_interval = flush_interval
        self._redis_ttl = redis_ttl
        self._dirty_audits: set[str] = set()
        self._dirty_lock = threading.Lock()
        self._flush_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @classmethod
    def write_state(
        cls,
        audit_id: str,
        state: dict[str, Any],
    ) -> None:
        ContentEventBus.set_audit_state(audit_id, **state)

    @classmethod
    def write_result(
        cls,
        audit_id: str,
        page_score: PageScore,
        crawl_result: Any,
    ) -> None:
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
            ContentEventBus.set_page_state(audit_id, page_score.url, page_data)
        except Exception as exc:
            logger.debug("ContentWriteBehindStore write_result failed: %s", exc)

    @classmethod
    def get_redis_ttl(cls) -> int:
        return REDIS_CONTENT_TTL_SECONDS

    def flush_audit_to_db(self, audit_id: str) -> bool:
        try:
            from app.shared.tasks.db import run_async
        except ImportError:
            logger.warning("ContentWriteBehindStore: DB flush skipped (no run_async)")
            return False

        async def _do_flush():
            from app.core.database import async_session_factory

            async with async_session_factory() as session:
                try:
                    record = await self._upsert_audit_record(session, audit_id)
                    if record is None:
                        logger.info("ContentWriteBehindStore: no state found for audit %s", audit_id)
                        return False
                    await session.commit()
                    logger.info(
                        "ContentWriteBehindStore: flushed audit %s to DB (status=%s, passed=%s, failed=%s)",
                        audit_id,
                        record.status.value,
                        record.rules_passed,
                        record.rules_failed,
                    )
                    return True
                except Exception as exc:
                    await session.rollback()
                    logger.error("ContentWriteBehindStore: DB flush failed for %s: %s", audit_id, exc)
                    return False

        try:
            return run_async(_do_flush())
        except Exception as exc:
            logger.error("ContentWriteBehindStore: flush error for %s: %s", audit_id, exc)
            return False

    async def _upsert_audit_record(
        self,
        session: Any,
        audit_id: str,
    ) -> ContentAuditCheck | None:
        counters = ContentEventBus.get_counters(audit_id)
        state = ContentEventBus.get_audit_state(audit_id)

        if not state:
            return None

        report_state = state.get("report")
        try:
            report_dict = json.loads(report_state) if isinstance(report_state, str) else report_state
        except (json.JSONDecodeError, TypeError):
            report_dict = None

        result = await session.get(ContentAuditCheck, audit_id)
        if result is None:
            result = ContentAuditCheck(
                audit_id=audit_id,
                start_url=state.get("start_url", ""),
                status=ContentAuditStatus(state.get("status", ContentAuditStatus.RUNNING.value)),
            )
            session.add(result)
        else:
            result.start_url = state.get("start_url", result.start_url)
            if state.get("status"):
                result.status = ContentAuditStatus(state["status"])

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
        with self._dirty_lock:
            self._dirty_audits.add(audit_id)

    def flush(self) -> int:
        with self._dirty_lock:
            dirty = self._dirty_audits.copy()
            self._dirty_audits.clear()

        flushed = 0
        for audit_id in dirty:
            if self.flush_audit_to_db(audit_id):
                flushed += 1
        return flushed

    def start_background_flush(self) -> None:
        if self._flush_thread is not None and self._flush_thread.is_alive():
            return
        self._stop_event.clear()
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            daemon=True,
            name="content-write-behind",
        )
        self._flush_thread.start()

    def _flush_loop(self) -> None:
        while not self._stop_event.wait(self._flush_interval):
            try:
                flushed = self.flush()
                if flushed > 0:
                    logger.info("ContentWriteBehindStore: background flush completed (%d audits)", flushed)
            except Exception as exc:
                logger.warning("ContentWriteBehindStore: background flush error: %s", exc)

    def stop(self) -> None:
        self._stop_event.set()
        if self._flush_thread is not None:
            self._flush_thread.join(timeout=10)
        self.flush()

    def __enter__(self) -> ContentWriteBehindStore:
        self.start_background_flush()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


__all__ = ["REDIS_CONTENT_TTL_SECONDS", "ContentWriteBehindStore"]
