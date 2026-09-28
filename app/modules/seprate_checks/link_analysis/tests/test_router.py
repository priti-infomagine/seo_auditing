"""Tests for the link analysis router (two-endpoint API)."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.modules.seprate_checks.link_analysis.model import (
    LinkAnalysisCheck,
    LinkAnalysisCheckStatus,
)
from app.modules.seprate_checks.link_analysis.schema import (
    LinkAnalysisQueuedResponse,
    LinkAnalysisCheckResponse,
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
    return SimpleNamespace(id=f"fake-link-analysis-task-{uuid.uuid4()}")


@pytest.fixture(autouse=True)
def mock_celery(monkeypatch):
    captured_tasks.clear()
    monkeypatch.setattr(celery_app, "send_task", _fake_send_task)
    return SimpleNamespace(captured=captured_tasks)


class TestPostCheck:
    @pytest.mark.asyncio
    async def test_check_queues_task(self, db_session, mock_redis):
        app_mock = None
        from app.main import app

        with patch("app.modules.seprate_checks.link_analysis.router.get_redis") as mock_get_redis:
            mock_get_redis.return_value = mock_redis
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/api/v1/link-analysis/check",
                    json={"url": "https://example.com"},
                )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "queued"
        assert data["domain"] == "example.com"
        assert data["check_id"]

        assert len(captured_tasks) == 1
        sent = captured_tasks[0]
        assert sent["name"] == "link_analysis.run_check"
        assert sent["queue"] == "crawler"
        assert sent["args"][0] == data["check_id"]

    @pytest.mark.asyncio
    async def test_check_invalid_url(self, db_session, mock_redis):
        from app.main import app

        with patch("app.modules.seprate_checks.link_analysis.router.get_redis") as mock_get_redis:
            mock_get_redis.return_value = mock_redis
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/api/v1/link-analysis/check",
                    json={"url": ""},
                )

        assert response.status_code in (400, 422)


class TestGetCheck:
    @pytest.mark.asyncio
    async def test_get_check_queued(self, db_session, mock_redis):
        from app.main import app

        check = LinkAnalysisCheck(
            url="https://example.com",
            domain="example.com",
            status=LinkAnalysisCheckStatus.QUEUED,
            progress={"phase": "queued", "message": "In queue"},
        )
        db_session.add(check)
        await db_session.commit()
        await db_session.refresh(check)

        with patch("app.modules.seprate_checks.link_analysis.router.get_redis") as mock_get_redis:
            mock_get_redis.return_value = mock_redis
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(f"/api/v1/link-analysis/check/{check.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["progress"]["phase"] == "queued"

    @pytest.mark.asyncio
    async def test_get_check_not_found(self, db_session, mock_redis):
        from app.main import app

        with patch("app.modules.seprate_checks.link_analysis.router.get_redis") as mock_get_redis:
            mock_get_redis.return_value = mock_redis
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(f"/api/v1/link-analysis/check/{uuid.uuid4()}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_check_invalid_id(self, db_session, mock_redis):
        from app.main import app

        with patch("app.modules.seprate_checks.link_analysis.router.get_redis") as mock_get_redis:
            mock_get_redis.return_value = mock_redis
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get("/api/v1/link-analysis/check/not-a-uuid")

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_check_failed(self, db_session, mock_redis):
        from app.main import app

        check = LinkAnalysisCheck(
            url="https://example.com",
            domain="example.com",
            status=LinkAnalysisCheckStatus.FAILED,
            error="Something went wrong",
            progress={"phase": "failed"},
        )
        db_session.add(check)
        await db_session.commit()
        await db_session.refresh(check)

        with patch("app.modules.seprate_checks.link_analysis.router.get_redis") as mock_get_redis:
            mock_get_redis.return_value = mock_redis
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(f"/api/v1/link-analysis/check/{check.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error"] == "Something went wrong"
