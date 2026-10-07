"""Tests for the redirect check API router endpoints."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.seprate_checks.redirect_check.router import router
from app.modules.seprate_checks.redirect_check.schema import (
    RedirectCheckRequest,
)


def _create_app():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/redirect-check")
    return app


@pytest.fixture
def mock_celery(monkeypatch):
    """Mock celery_app.send_task to avoid requiring a running worker."""
    fake_task = SimpleNamespace(id="test-task-id")
    AsyncMock(return_value=fake_task) if False else None

    def fake_send_task(name, args, queue):
        fake_send_task.called_with = (name, args, queue)
        return SimpleNamespace(id=f"task-{args[0][:8]}")

    fake_celery = SimpleNamespace(send_task=fake_send_task)
    monkeypatch.setattr(
        "app.modules.seprate_checks.redirect_check.router.celery_app", fake_celery
    )
    return fake_send_task


@pytest.fixture
def mock_db(monkeypatch):
    """Mock the DB session used by StreamingAuditService."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.add = AsyncMock()
    return mock_session


@pytest.mark.asyncio
async def test_post_check_returns_202_with_audit_id(mock_celery, monkeypatch):
    app = _create_app()

    created_run = SimpleNamespace(
        id=uuid4(),
        domain="example.com",
        status="queued",
        max_pages=500,
        config={},
        created_at=None,
        updated_at=None,
    )

    async def fake_create_run(*args, **kwargs):
        return created_run

    async def fake_update_run(*args, **kwargs):
        return created_run

    with patch.multiple(
        "app.modules.streaming_audit.services.streaming_audit_service.StreamingAuditService",
        create_run=AsyncMock(return_value=created_run),
        get_run=AsyncMock(return_value=created_run),
        update_run=AsyncMock(return_value=created_run),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/redirect-check/check",
                json={"domain": "https://example.com", "max_urls": 100},
            )

    assert response.status_code == 202
    payload = response.json()
    assert payload["domain"] == "https://example.com"
    assert payload["max_urls"] == 100
    assert payload["status"] == "queued"
    assert "redirect_check.run_domain_check" in str(mock_celery.called_with)
    assert "/api/v1/redirect-check/status/" in payload["status_url"]
    assert "/api/v1/redirect-check/stream/" in payload["stream_url"]


@pytest.mark.asyncio
async def test_post_check_validates_domain():
    app = _create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/redirect-check/check",
            json={"domain": "", "max_urls": 100},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_check_rejects_oversized_max_urls():
    app = _create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/redirect-check/check",
            json={"domain": "https://example.com", "max_urls": 1000},
        )

    assert response.status_code == 422


def test_redirect_check_request_normalizes_domain():
    req = RedirectCheckRequest(domain="example.com", max_urls=50)
    assert req.domain == "https://example.com"
    assert req.max_urls == 50


def test_redirect_check_request_defaults():
    req = RedirectCheckRequest(domain="https://example.com")
    assert req.max_urls == 500


@pytest.mark.asyncio
async def test_status_endpoint_returns_404_for_unknown_id():
    app = _create_app()

    async def fake_get_run(audit_id):
        return None

    with patch(
        "app.modules.streaming_audit.services.streaming_audit_service.StreamingAuditService.get_run",
        AsyncMock(return_value=None),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/redirect-check/status/3bbd47f4-7ae7-4bd2-aaba-1d6173f60b0a"
            )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_result_endpoint_returns_400_when_not_completed():
    app = _create_app()

    run = SimpleNamespace(
        id="3bbd47f4-7ae7-4bd2-aaba-1d6173f60b0a",
        domain="example.com",
        status="processing",
        final_summary=None,
        updated_at=None,
        completed_count=0,
        failed_count=0,
    )

    with patch(
        "app.modules.streaming_audit.services.streaming_audit_service.StreamingAuditService.get_run",
        AsyncMock(return_value=run),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/redirect-check/result/3bbd47f4-7ae7-4bd2-aaba-1d6173f60b0a"
            )

    assert response.status_code == 400
    assert "not completed" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_result_endpoint_returns_results_when_completed():
    app = _create_app()

    run = SimpleNamespace(
        id="3bbd47f4-7ae7-4bd2-aaba-1d6173f60b0a",
        domain="example.com",
        status="completed",
        final_summary={
            "total_checked": 2,
            "redirect_results": [
                {
                    "url": "https://example.com/old",
                    "redirect_count": 1,
                    "final_url": "https://example.com/new",
                    "final_status": 200,
                    "is_redirect": True,
                    "is_internal_redirect": True,
                    "is_external_redirect": False,
                    "error": None,
                },
                {
                    "url": "https://example.com/page",
                    "redirect_count": 0,
                    "final_url": "https://example.com/page",
                    "final_status": 200,
                    "is_redirect": False,
                    "is_internal_redirect": False,
                    "is_external_redirect": False,
                    "error": None,
                },
            ],
            "summary": {
                "total_urls": 2,
                "redirects_found": 1,
                "redirect_chains": 1,
                "broken": 0,
                "internal_redirects": 1,
                "external_redirects": 0,
                "loops": 0,
                "meta_refresh": 0,
                "insecure": 0,
                "by_status_class": {"ok": 2, "redirect": 0, "broken": 0, "unverified": 0},
            },
            "findings": [
                {
                    "code": "redirect_internal",
                    "severity": "low",
                    "status": "warning",
                    "message": "Internal redirect for https://example.com/old",
                    "evidence": "https://example.com/old -> https://example.com/new",
                    "target_url": "https://example.com/old",
                    "redirect_count": 1,
                    "final_status": 200,
                },
            ],
            "recommendations": [],
            "overall_status": "warning",
            "severity": "low",
            "cost_seconds": 1.5,
        },
        updated_at=None,
        completed_count=2,
        failed_count=0,
    )

    with patch(
        "app.modules.streaming_audit.services.streaming_audit_service.StreamingAuditService.get_run",
        AsyncMock(return_value=run),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/redirect-check/result/3bbd47f4-7ae7-4bd2-aaba-1d6173f60b0a"
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_checked"] == 2
    assert payload["overall_status"] == "warning"
    assert len(payload["results"]) == 2
    assert payload["results"][0]["redirect_count"] == 1
    assert payload["results"][0]["is_redirect"] is True
