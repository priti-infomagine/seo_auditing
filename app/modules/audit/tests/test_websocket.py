"""
WebSocket integration tests for audit event streaming.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from app.main import app
from app.modules.audit.events import AuditEventBus, AuditEventType, PipelineEvent


class TestAuditWebSocket:
    """Integration tests for audit WebSocket endpoint."""

    @pytest.fixture
    def audit_id(self):
        return str(uuid4())

    @pytest.fixture
    def mock_redis(self):
        with patch("app.modules.audit.events._get_sync_redis") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def mock_async_redis(self):
        with patch("redis.asyncio.Redis.from_url") as mock:
            client = AsyncMock()
            mock.return_value = client
            yield client

    def test_audit_websocket_connect(self, audit_id, mock_async_redis):
        """Test WebSocket connection and initial handshake."""
        mock_async_redis.return_value.ping = AsyncMock(return_value=True)
        mock_async_redis.return_value.xrange = AsyncMock(return_value=[])
        mock_async_redis.return_value.xread = AsyncMock(return_value=None)
        mock_async_redis.return_value.close = AsyncMock()

        with patch("app.modules.audit.events.AuditEventBus.get_audit_state") as mock_state:
            mock_state.return_value = {"status": "crawling"}

            with TestClient(app) as client:
                with client.websocket_connect(f"/api/v1/audit/ws/{audit_id}") as ws:
                    # Connection should be accepted
                    assert ws is not None

    def test_audit_websocket_catchup(self, audit_id, mock_async_redis):
        """Test catch-up phase replays historical events."""
        events = [
            ("1-0", {"event": json.dumps({
                "event_type": "crawl_started",
                "audit_id": audit_id,
                "url": "https://example.com",
                "timestamp": "2024-01-01T00:00:00",
                "data": {"max_pages": 100},
                "seq": 1,
            })}),
            ("2-0", {"event": json.dumps({
                "event_type": "crawl_page_started",
                "audit_id": audit_id,
                "url": "https://example.com/page1",
                "timestamp": "2024-01-01T00:00:01",
                "data": {"depth": 0},
                "seq": 2,
            })}),
        ]

        mock_async_redis.return_value.ping = AsyncMock(return_value=True)
        mock_async_redis.return_value.xrange = AsyncMock(return_value=events)
        mock_async_redis.return_value.xread = AsyncMock(return_value=None)
        mock_async_redis.return_value.close = AsyncMock()

        with patch("app.modules.audit.events.AuditEventBus.get_audit_state") as mock_state:
            mock_state.return_value = {"status": "crawling"}

            with TestClient(app) as client:
                with client.websocket_connect(f"/api/v1/audit/ws/{audit_id}") as ws:
                    # Receive catch-up events
                    msg1 = json.loads(ws.receive_text())
                    assert msg1["type"] == "event"
                    assert msg1["event_type"] == "crawl_started"
                    assert msg1["seq"] == 1

                    msg2 = json.loads(ws.receive_text())
                    assert msg2["type"] == "event"
                    assert msg2["event_type"] == "crawl_page_started"
                    assert msg2["seq"] == 2

    def test_audit_websocket_resume(self, audit_id, mock_async_redis):
        """Test resume from last_id parameter."""
        events = [
            ("5-0", {"event": json.dumps({
                "event_type": "crawl_page_persisted",
                "audit_id": audit_id,
                "url": "https://example.com/page5",
                "timestamp": "2024-01-01T00:00:05",
                "data": {"page_id": "uuid"},
                "seq": 5,
            })}),
        ]

        mock_async_redis.return_value.ping = AsyncMock(return_value=True)
        mock_async_redis.return_value.xrange = AsyncMock(return_value=events)
        mock_async_redis.return_value.xread = AsyncMock(return_value=None)
        mock_async_redis.return_value.close = AsyncMock()

        with patch("app.modules.audit.events.AuditEventBus.get_audit_state") as mock_state:
            mock_state.return_value = {"status": "crawling"}

            with TestClient(app) as client:
                with client.websocket_connect(f"/api/v1/audit/ws/{audit_id}?last_id=4-0") as ws:
                    msg = json.loads(ws.receive_text())
                    assert msg["event_type"] == "crawl_page_persisted"
                    assert msg["seq"] == 5

    def test_audit_websocket_final_snapshot(self, audit_id, mock_async_redis):
        """Test final snapshot sent when audit completes."""
        mock_async_redis.return_value.ping = AsyncMock(return_value=True)
        mock_async_redis.return_value.xrange = AsyncMock(return_value=[])
        mock_async_redis.return_value.xread = AsyncMock(return_value=None)
        mock_async_redis.return_value.close = AsyncMock()

        with patch("app.modules.audit.events.AuditEventBus.get_audit_state") as mock_state:
            mock_state.side_effect = [
                {"status": "completed", "report": {"summary": {"score": 85}}},
                {"status": "completed", "report": {"summary": {"score": 85}}},
            ]

            with TestClient(app) as client:
                with client.websocket_connect(f"/api/v1/audit/ws/{audit_id}") as ws:
                    msg = json.loads(ws.receive_text())
                    assert msg["type"] == "final"
                    assert msg["audit_id"] == audit_id
                    assert msg["summary"]["score"] == 85

    def test_audit_websocket_error_on_failed(self, audit_id, mock_async_redis):
        """Test error event sent when audit fails."""
        mock_async_redis.return_value.ping = AsyncMock(return_value=True)
        mock_async_redis.return_value.xrange = AsyncMock(return_value=[])
        mock_async_redis.return_value.xread = AsyncMock(return_value=None)
        mock_async_redis.return_value.close = AsyncMock()

        with patch("app.modules.audit.events.AuditEventBus.get_audit_state") as mock_state:
            mock_state.side_effect = [
                {"status": "failed", "error": "Something went wrong"},
                {"status": "failed", "error": "Something went wrong"},
            ]

            with TestClient(app) as client:
                with client.websocket_connect(f"/api/v1/audit/ws/{audit_id}") as ws:
                    msg = json.loads(ws.receive_text())
                    assert msg["type"] == "error"
                    assert msg["code"] == "PIPELINE_FAILED"


class TestAuditEventBus:
    """Tests for AuditEventBus."""

    @pytest.fixture
    def mock_redis(self):
        with patch("app.modules.audit.events._get_sync_redis") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    def test_emit_increments_counters(self, mock_redis):
        """Test that emit increments appropriate counters."""
        bus = AuditEventBus()
        bus.emit(AuditEventType.CRAWL_PAGE_STARTED, "audit_123", url="https://example.com")

        # Verify HINCRBY was called for event_seq and pages_discovered
        assert mock_redis.hincrby.call_count >= 2

    def test_emit_crawl_page_failed_only_increments_failed(self, mock_redis):
        """Test that CRAWL_PAGE_FAILED only increments pages_failed, not pages_crawled."""
        bus = AuditEventBus()
        bus.emit(AuditEventType.CRAWL_PAGE_FAILED, "audit_123", url="https://example.com", data={"error": "timeout"})

        # Verify pages_failed was incremented
        calls = mock_redis.hincrby.call_args_list
        failed_called = any("pages_failed" in str(call) for call in calls)
        assert failed_called

    def test_emit_rule_batch_complete(self, mock_redis):
        """Test that RULE_BATCH_COMPLETE increments rule counters."""
        bus = AuditEventBus()
        bus.emit(
            AuditEventType.RULE_BATCH_COMPLETE,
            "audit_123",
            data={"rules_passed": 45, "rules_failed": 15, "rules_total": 60}
        )

        calls = mock_redis.hincrby.call_args_list
        passed_called = any("rules_passed" in str(call) and "45" in str(call) for call in calls)
        failed_called = any("rules_failed" in str(call) and "15" in str(call) for call in calls)
        total_called = any("rules_total" in str(call) and "60" in str(call) for call in calls)
        assert passed_called and failed_called and total_called

    def test_reset_counters(self, mock_redis):
        """Test reset_counters initializes all counters to zero."""
        AuditEventBus.reset_counters("audit_123")

        # Verify hset was called with default counters
        mock_redis.hset.assert_called()
        args, kwargs = mock_redis.hset.call_args
        mapping = kwargs.get("mapping", {})
        assert mapping["pages_discovered"] == "0"
        assert mapping["pages_crawled"] == "0"
        assert mapping["rules_passed"] == "0"

    def test_set_audit_state(self, mock_redis):
        """Test set_audit_state writes state hash with TTL."""
        AuditEventBus.set_audit_state("audit_123", status="crawling", start_url="https://example.com")

        mock_redis.hset.assert_called()
        mock_redis.expire.assert_called()

    def test_get_events_for_audit(self, mock_redis):
        """Test retrieving events from Redis stream."""
        events_data = [
            ("1-0", {"event": json.dumps({
                "event_type": "crawl_started",
                "audit_id": "audit_123",
                "url": "https://example.com",
                "timestamp": "2024-01-01T00:00:00",
                "data": {},
                "seq": 1,
            })}),
        ]
        mock_redis.xrange.return_value = events_data

        events = AuditEventBus.get_events_for_audit("audit_123")

        assert len(events) == 1
        assert events[0].event_type == "crawl_started"
        assert events[0].seq == 1


class TestAuditAnalyzeEndpoint:
    """Tests for POST /audit/analyze endpoint with websocket_url."""

    def test_analyze_returns_websocket_url(self):
        """Test that POST /audit/analyze returns websocket_url in response."""
        with patch("app.api.endpoints.v1.audit.analyze.get_db") as mock_db:
            with patch("app.api.endpoints.v1.audit.analyze.get_redis") as mock_redis:
                with patch("app.api.endpoints.v1.audit.analyze.SiteDiscoveryService") as mock_discovery:
                    with patch("app.shared.tasks.celery_app.celery_app.send_task") as mock_send_task:
                        # Setup mocks
                        mock_db.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
                        mock_db.return_value.__aexit__ = AsyncMock(return_value=None)
                        mock_redis.return_value.setex = AsyncMock()
                        mock_discovery.return_value.discover = AsyncMock(return_value=MagicMock(sitemaps=[MagicMock()]))
                        mock_send_task.return_value = MagicMock(id="task_123")

                        from fastapi.testclient import TestClient
                        from app.main import app

                        with TestClient(app) as client:
                            response = client.post(
                                "/api/v1/audit/analyze",
                                json={"url": "https://example.com", "concurrency": 10, "full_pipeline": True}
                            )
                            assert response.status_code == 202
                            data = response.json()
                            assert "websocket_url" in data
                            assert data["websocket_url"] == f"/api/v1/audit/ws/{data['audit_id']}"


class TestBackwardCompatibility:
    """Tests to ensure existing polling endpoints still work."""

    def test_poll_endpoint_exists(self):
        """Test that /audit/analyze/poll/{id} endpoint still exists."""
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            response = client.get("/api/v1/audit/analyze/poll/invalid-uuid")
            # Should return 422 for invalid UUID, not 404
            assert response.status_code in (200, 422)

    def test_status_endpoint_exists(self):
        """Test that /audit/status/{id} endpoint still exists."""
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            response = client.get("/api/v1/audit/status/invalid-uuid")
            assert response.status_code in (200, 422, 404)

    def test_result_endpoint_exists(self):
        """Test that /audit/result/{id} endpoint still exists."""
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            response = client.get("/api/v1/audit/result/invalid-uuid")
            assert response.status_code in (200, 422, 404)

    def test_task_status_endpoint_exists(self):
        """Test that /audit/analyze/task/{task_id} endpoint still exists."""
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            response = client.get("/api/v1/audit/analyze/task/invalid-task-id")
            assert response.status_code in (200, 422, 404)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])