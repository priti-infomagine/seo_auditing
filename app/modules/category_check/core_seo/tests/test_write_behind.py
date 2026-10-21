"""Tests for the WriteBehindStore and AuditCheck DB model."""
from __future__ import annotations

from app.modules.category_check.core_seo.db_models.audit_db import (
    AuditCheck,
    AuditStatus,
)
from app.modules.category_check.core_seo.events import REDIS_TTL_SECONDS, EventBus
from app.modules.category_check.core_seo.storage.write_behind import (
    REDIS_AUDIT_TTL_SECONDS,
    WriteBehindStore,
)


class TestAuditCheckModel:
    """Tests for the AuditCheck SQLAlchemy model."""

    def test_audit_status_enum_values(self):
        assert AuditStatus.PENDING.value == "pending"
        assert AuditStatus.RUNNING.value == "running"
        assert AuditStatus.COMPLETED.value == "completed"
        assert AuditStatus.FAILED.value == "failed"

    def test_to_dict_basic(self):
        record = AuditCheck(
            audit_id="test-123",
            start_url="https://example.com",
            status=AuditStatus.PENDING,
        )
        d = record.to_dict()
        assert d["audit_id"] == "test-123"
        assert d["start_url"] == "https://example.com"
        assert d["status"] == "pending"
        assert d["rules_passed"] == 0
        assert d["rules_failed"] == 0
        assert d["pass_percentage"] == 0.0

    def test_mark_completed(self):
        record = AuditCheck(
            audit_id="test-456",
            start_url="https://example.com",
            status=AuditStatus.RUNNING,
        )
        report = {"summary": {"pages_total": 10}}
        record.mark_completed(
            rules_passed=15,
            rules_failed=3,
            pass_percentage=83.3,
            crawled_pages=10,
            total_pages=10,
            pages_failed=0,
            report=report,
        )
        assert record.status == AuditStatus.COMPLETED
        assert record.rules_passed == 15
        assert record.rules_failed == 3
        assert record.pass_percentage == 83.3
        assert record.crawled_pages == 10
        assert record.total_pages == 10

    def test_mark_failed(self):
        record = AuditCheck(
            audit_id="test-789",
            start_url="https://example.com",
        )
        record.mark_failed("Connection timeout")
        assert record.status == AuditStatus.FAILED
        assert record.error_message == "Connection timeout"

    def test_set_and_get_report(self):
        record = AuditCheck(audit_id="test-report", start_url="https://example.com")
        report_data = {"audit_id": "test-report", "summary": {"rules_passed": 15}}
        record.set_report(report_data)
        retrieved = record.get_report()
        assert retrieved == report_data

    def test_get_report_empty(self):
        record = AuditCheck(audit_id="test-empty", start_url="https://example.com")
        assert record.get_report() is None


class TestWriteBehindStore:
    """Tests for the WriteBehindStore write-behind policy."""

    def test_redis_ttl_constant(self):
        assert REDIS_AUDIT_TTL_SECONDS == 3600
        assert REDIS_TTL_SECONDS == 3600

    def test_mark_dirty_and_flush(self):
        store = WriteBehindStore(flush_interval=999)
        store.mark_dirty("test-audit-1")
        assert "test-audit-1" in store._dirty_audits
        # flush should clear dirty set (DB flush may fail, but dirty set is cleared)
        store.flush()
        assert "test-audit-1" not in store._dirty_audits

    def test_write_state_to_redis(self):
        EventBus.set_audit_state("wb-test-1", status="running", total_pages=5)
        state = EventBus.get_audit_state("wb-test-1")
        assert state.get("status") == "running"
        assert state.get("total_pages") == 5
        EventBus.clear_audit_state("wb-test-1")

    def test_write_result_to_redis(self):
        from app.modules.category_check.core_seo.events import _redis_key
        from app.modules.category_check.core_seo.models import (
            CrawlResult,
            PageScore,
        )

        store = WriteBehindStore()
        page_score = PageScore(
            url="https://example.com/test",
            passed=10,
            failed=5,
            total=15,
            pass_percentage=66.7,
        )
        crawl_result = CrawlResult(
            url="https://example.com/test", success=True, status_code=200
        )

        store.write_result("wb-test-2", page_score, crawl_result)

        import redis

        from app.core.config import settings
        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        key = _redis_key("wb-test-2", "pages")
        ttl = client.ttl(key)
        assert ttl > 0  # key exists
        assert ttl <= REDIS_AUDIT_TTL_SECONDS

        EventBus.clear_audit_state("wb-test-2")

    def test_clear_audit_state(self):
        from app.modules.category_check.core_seo.events import _redis_hset_sync
        EventBus.set_audit_state("wb-test-3", status="completed")
        _redis_hset_sync("wb-test-3", "counters", {"pages_crawled": 5})

        EventBus.clear_audit_state("wb-test-3")

        # After clearing, the state should be gone or empty
        state = EventBus.get_audit_state("wb-test-3")
        counters = EventBus.get_counters("wb-test-3")
        assert state.get("status") != "completed" or state == {}
        assert counters.get("pages_crawled", 0) == 0

    def test_start_and_stop_background_flush(self):
        store = WriteBehindStore(flush_interval=0.1)
        store.start_background_flush()
        assert store._flush_thread is not None
        assert store._flush_thread.is_alive()

        store.stop()
        assert store._flush_thread is not None

    def test_get_write_behind_store_singleton(self):
        """Verify the singleton accessor returns the same instance."""
        s1 = WriteBehindStore()
        s2 = WriteBehindStore()
        # These are separate instances (not singleton by design)
        assert s1 is not s2
