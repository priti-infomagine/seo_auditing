"""Tests for the asynchronous Sitemap check router (HTTP API)."""
from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.main import app
from app.modules.seprate_checks.sitemap_check.model import (
    SitemapCheck,
    SitemapCheckStatus,
    SitemapOverallStatus,
    SitemapSeverity,
)
from app.shared.tasks.celery_app import celery_app


captured_tasks: list = []


def _fake_send_task(name, args=None, kwargs=None, queue=None, **opts):
    captured_tasks.append(
        {
            "name": name,
            "args": list(args or []),
            "kwargs": dict(kwargs or {}),
            "queue": queue,
        }
    )
    return SimpleNamespace(id=f"fake-sitemap-task-{uuid.uuid4()}")


@pytest.fixture(autouse=True)
def mock_celery(monkeypatch):
    captured_tasks.clear()
    monkeypatch.setattr(celery_app, "send_task", _fake_send_task)
    return SimpleNamespace(captured=captured_tasks)


@pytest.mark.asyncio
async def test_router_check_queues_task(db_session, mock_celery):
    """POST /check → 202 Accepted, creates DB record and enqueues Celery task."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/sitemap/check",
            json={"url": "https://example.com"},
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["domain"] == "example.com"
    check_id = data["check_id"]
    assert check_id

    # Verify task was dispatched to crawler queue
    assert len(mock_celery.captured) == 1
    sent = mock_celery.captured[0]
    assert sent["name"] == "sitemap.run_check"
    assert sent["queue"] == "crawler"
    assert sent["args"][0] == check_id


@pytest.mark.asyncio
async def test_router_check_invalid_url(db_session):
    """POST /check with empty url → 422 Validation Error."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/v1/sitemap/check",
            json={"url": ""},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_router_status_queued(db_session):
    """GET /status/{check_id} returns queued state."""
    check = SitemapCheck(
        url="https://example.com",
        domain="example.com",
        status=SitemapCheckStatus.QUEUED,
        progress={"phase": "queued", "message": "In queue"},
    )
    db_session.add(check)
    await db_session.commit()
    await db_session.refresh(check)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(f"/api/v1/sitemap/status/{check.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert data["progress"]["phase"] == "queued"
    assert "data" not in data


@pytest.mark.asyncio
async def test_router_status_completed_without_result_payload(db_session):
    """GET /status/{check_id} returns status only after completion."""
    check = SitemapCheck(
        url="https://example.com",
        domain="example.com",
        status=SitemapCheckStatus.COMPLETED,
        overall_status=SitemapOverallStatus.PASS,
        severity=SitemapSeverity.NONE,
        summary={
            "total_sitemaps": 1,
            "sitemap_indexes": 0,
            "url_sitemaps": 1,
            "total_urls_declared": 25,
            "total_issues": 0,
        },
        sitemaps=[
            {
                "url": "https://example.com/sitemap.xml",
                "is_index": False,
                "status_code": 200,
                "content_type": "application/xml",
                "entry_count": 25,
                "content_length": 1500,
                "response_time_ms": 110,
                "issues": [],
                "recommendations": [],
            }
        ],
        findings=[],
        recommendations=[],
        report_markdown="# Sitemap Audit Report",
        cost_seconds=1.23,
    )
    db_session.add(check)
    await db_session.commit()
    await db_session.refresh(check)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(f"/api/v1/sitemap/status/{check.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["domain"] == "example.com"
    assert "data" not in data


@pytest.mark.asyncio
async def test_router_result_endpoint(db_session):
    """GET /result/{check_id} returns 200 when completed, 400 when still queued."""
    check = SitemapCheck(
        url="https://example.com",
        domain="example.com",
        status=SitemapCheckStatus.PROCESSING,
    )
    db_session.add(check)
    await db_session.commit()
    await db_session.refresh(check)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res_processing = await ac.get(f"/api/v1/sitemap/result/{check.id}")
        assert res_processing.status_code == 400

    # Mark completed
    check.status = SitemapCheckStatus.COMPLETED
    check.overall_status = SitemapOverallStatus.PASS
    check.severity = SitemapSeverity.NONE
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        res_completed = await ac.get(f"/api/v1/sitemap/result/{check.id}")
        assert res_completed.status_code == 200
        assert res_completed.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_router_status_not_found(db_session):
    """GET /status/{random_uuid} → 404."""
    random_id = uuid.uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get(f"/api/v1/sitemap/status/{random_id}")

    assert response.status_code == 404
