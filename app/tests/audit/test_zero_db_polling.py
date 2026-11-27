"""
Unit tests for zero-DB polling and cached result retrieval.
"""
import json
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock

from app.main import app
from app.core.redis import get_redis


@pytest.mark.asyncio
async def test_zero_db_polling_endpoint_returns_from_redis():
    """GET /api/v1/audit/analyze/poll/{audit_id} returns cached result directly from Redis."""
    audit_id = str(uuid.uuid4())
    mock_payload = {
        "audit": {"id": audit_id, "url": "https://example.com"},
        "summary": {"score": 92.5, "grade": "A"},
    }

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=lambda key: json.dumps(mock_payload) if "result" in key else None)

    app.dependency_overrides[get_redis] = lambda: mock_redis
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/v1/audit/analyze/poll/{audit_id}?format=full")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "completed"
            assert data["result"]["summary"]["score"] == 92.5
            assert data["result"]["summary"]["grade"] == "A"
    finally:
        app.dependency_overrides.pop(get_redis, None)


@pytest.mark.asyncio
async def test_zero_db_polling_reports_failed_status_before_stale_cached_result():
    audit_id = str(uuid.uuid4())
    stale_result = {
        "audit": {"id": audit_id, "pages": {"analyzed": 6}},
        "summary": {"score": 0, "checks": {"total": 0}},
    }
    failed_status = {
        "audit_id": audit_id,
        "status": "failed",
        "current_stage": "evaluate",
        "error": "Rule result persistence failed",
    }

    async def _get(key):
        if key.endswith(":status:" + audit_id):
            return json.dumps(failed_status)
        if key.endswith(":full"):
            return json.dumps(stale_result)
        return None

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=_get)
    app.dependency_overrides[get_redis] = lambda: mock_redis
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                f"/api/v1/audit/analyze/poll/{audit_id}?format=full"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["stage"] == "evaluate"
        assert "persistence failed" in data["error"]
        assert mock_redis.get.await_count == 1
    finally:
        app.dependency_overrides.pop(get_redis, None)


@pytest.mark.asyncio
async def test_pipeline_status_includes_result_without_db():
    """GET /api/v1/audit/status/{audit_id}?include_result=true returns cached status & result from Redis."""
    audit_id = str(uuid.uuid4())
    mock_status = {
        "audit_id": audit_id,
        "parse_status": "completed",
        "evaluate_status": "completed",
        "score_status": "completed",
        "overall_score": 88.0,
        "grade": "B+",
        "pages_parsed": 5,
    }
    mock_result = {
        "audit": {"id": audit_id},
        "summary": {"score": 88.0, "grade": "B+"},
    }

    mock_redis = AsyncMock()
    def _mock_get(key):
        if "status" in key:
            return json.dumps(mock_status)
        if "result" in key:
            return json.dumps(mock_result)
        return None

    mock_redis.get = AsyncMock(side_effect=_mock_get)

    app.dependency_overrides[get_redis] = lambda: mock_redis
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/v1/audit/status/{audit_id}?include_result=true")
            assert resp.status_code == 200
            data = resp.json()
            assert data["score_status"] == "completed"
            assert data["overall_score"] == 88.0
            assert data["result"] is not None
            assert data["result"]["summary"]["score"] == 88.0
    finally:
        app.dependency_overrides.pop(get_redis, None)
