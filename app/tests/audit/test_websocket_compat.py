"""
Backward compatibility tests for audit polling endpoints.

Ensures all existing polling endpoints work identically after WebSocket changes.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app


class TestAuditPollingEndpoints:
    """Tests for audit polling endpoints backward compatibility."""

    @pytest.fixture
    def audit_id(self):
        return str(uuid4())

    @pytest.fixture
    def mock_redis(self):
        with patch("app.api.endpoints.v1.audit.analyze.get_redis") as mock:
            client = AsyncMock()
            mock.return_value = client
            yield client

    def test_poll_endpoint_returns_queued_when_no_cache(self, audit_id, mock_redis):
        """Test poll endpoint returns 'queued_or_crawling' when no cache."""
        mock_redis.get.return_value = None

        with patch("pathlib.Path.glob", return_value=[]):
            with TestClient(app) as client:
                response = client.get(f"/api/v1/audit/analyze/poll/{audit_id}")
                assert response.status_code == 200
                data = response.json()
                assert data["audit_id"] == audit_id
                assert data["status"] == "queued_or_crawling"
                assert "message" in data

    def test_poll_endpoint_returns_cached_result(self, audit_id, mock_redis):
        """Test poll endpoint returns cached result from Redis."""
        cached_result = {
            "audit_id": audit_id,
            "summary": {"score": 85, "grade": "B"},
            "pages": [],
        }
        mock_redis.get.return_value = json.dumps(cached_result)

        with TestClient(app) as client:
            response = client.get(f"/api/v1/audit/analyze/poll/{audit_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["audit_id"] == audit_id
            assert data["status"] == "completed"
            assert data["result"]["summary"]["score"] == 85

    def test_poll_endpoint_returns_disk_result(self, audit_id, mock_redis):
        """Test poll endpoint falls back to disk file."""
        mock_redis.get.return_value = None

        disk_result = {
            "audit_id": audit_id,
            "summary": {"score": 90, "grade": "A"},
            "pages": [],
        }

        with patch("pathlib.Path.glob") as mock_glob:
            mock_file = MagicMock()
            mock_file.is_file.return_value = True
            mock_file.read_text.return_value = json.dumps(disk_result)
            mock_glob.return_value = [mock_file]

            with TestClient(app) as client:
                response = client.get(f"/api/v1/audit/analyze/poll/{audit_id}")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "completed"
                assert data["result"]["summary"]["score"] == 90

    def test_task_status_endpoint_returns_state(self, audit_id):
        """Test task status endpoint returns Celery task state."""
        with patch("app.api.endpoints.v1.audit.analyze.celery_app.AsyncResult") as mock_async:
            mock_result = MagicMock()
            mock_result.state = "PROGRESS"
            mock_result.info = {"current": 5, "total": 100, "percent": 5}
            mock_async.return_value = mock_result

            with TestClient(app) as client:
                response = client.get(f"/api/v1/audit/analyze/task/{audit_id}")
                assert response.status_code == 200
                data = response.json()
                assert data["task_id"] == audit_id
                assert data["state"] == "PROGRESS"
                assert data["meta"]["current"] == 5

    def test_task_status_endpoint_returns_result_on_success(self, audit_id):
        """Test task status endpoint returns result on success."""
        with patch("app.api.endpoints.v1.audit.analyze.celery_app.AsyncResult") as mock_async:
            with patch("app.api.endpoints.v1.audit.analyze.get_redis") as mock_redis:
                mock_result = MagicMock()
                mock_result.state = "SUCCESS"
                mock_result.result = {"audit_id": audit_id, "pages_crawled": 50}
                mock_async.return_value = mock_result
                mock_redis.return_value.get = AsyncMock(return_value=None)

                with patch("pathlib.Path.glob", return_value=[]):
                    with TestClient(app) as client:
                        response = client.get(f"/api/v1/audit/analyze/task/{audit_id}")
                        assert response.status_code == 200
                        data = response.json()
                        assert data["state"] == "SUCCESS"
                        assert data["result"]["pages_crawled"] == 50


class TestAuditStatusEndpoint:
    """Tests for /audit/status/{id} endpoint."""

    def test_status_endpoint_returns_cached_status(self, audit_id):
        """Test status endpoint returns cached status from Redis."""
        with patch("app.api.endpoints.v1.audit.results.get_redis") as mock_redis:
            cached_status = {
                "audit_id": audit_id,
                "parse_status": "completed",
                "evaluate_status": "completed",
                "score_status": "completed",
                "overall_score": 85,
                "grade": "B",
                "pages_parsed": 50,
            }
            mock_redis.return_value.get = AsyncMock(return_value=json.dumps(cached_status))

            with TestClient(app) as client:
                response = client.get(f"/api/v1/audit/status/{audit_id}")
                assert response.status_code == 200
                data = response.json()
                assert data["audit_id"] == audit_id
                assert data["overall_score"] == 85


class TestAuditResultEndpoint:
    """Tests for /audit/result/{id} endpoint."""

    def test_result_endpoint_returns_full_result(self, audit_id):
        """Test result endpoint returns full audit result."""
        with patch("app.api.endpoints.v1.audit.results.get_redis") as mock_redis:
            with patch("app.modules.audit.services.audit_response_builder.AuditResponseBuilder.build") as mock_build:
                mock_redis.return_value.get = AsyncMock(return_value=None)
                mock_build.return_value = {
                    "audit_id": audit_id,
                    "summary": {"score": 85, "grade": "B"},
                    "pages": [],
                }

                with TestClient(app) as client:
                    response = client.get(f"/api/v1/audit/result/{audit_id}")
                    assert response.status_code == 200
                    data = response.json()
                    assert data["audit_id"] == audit_id
                    assert data["summary"]["score"] == 85


class TestHealthEndpoint:
    """Tests for audit health check endpoint."""

    def test_health_check(self):
        """Test audit health check endpoint."""
        with TestClient(app) as client:
            response = client.get("/api/v1/audit/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "audit-analyze"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])