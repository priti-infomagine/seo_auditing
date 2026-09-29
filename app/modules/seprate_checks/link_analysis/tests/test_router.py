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
    async def test_check_with_custom_max_pages(self, db_session, mock_redis):
        from app.main import app

        with patch("app.modules.seprate_checks.link_analysis.router.get_redis") as mock_get_redis:
            mock_get_redis.return_value = mock_redis
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.post(
                    "/api/v1/link-analysis/check",
                    json={"url": "https://example.com", "max_pages": 50},
                )

        assert response.status_code == 202
        data = response.json()
        assert data["max_pages"] == 50
        sent = captured_tasks[-1]
        assert sent["kwargs"].get("max_pages") == 50

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

    @pytest.mark.asyncio
    async def test_get_check_completed_with_filters(self, db_session, mock_redis):
        from app.main import app
        from app.modules.seprate_checks.link_analysis.model import LinkFinding

        check = LinkAnalysisCheck(
            url="https://example.com",
            domain="example.com",
            status=LinkAnalysisCheckStatus.COMPLETED,
            overall_status="warning",
            severity="medium",
            cost_seconds=1.2,
            summary={
                "pages_crawled": 2,
                "broken_links": 1,
                "pages": [
                    {
                        "url": "https://example.com/",
                        "status_code": 200,
                        "depth": 0,
                        "inbound_internal_links": 2,
                        "outbound_internal_links": 1,
                        "outbound_external_links": 1,
                        "is_orphan": False,
                        "is_dead_end": False,
                        "issues": [],
                    },
                    {
                        "url": "https://example.com/orphan-page",
                        "status_code": 200,
                        "depth": 2,
                        "inbound_internal_links": 0,
                        "outbound_internal_links": 0,
                        "outbound_external_links": 0,
                        "is_orphan": True,
                        "is_dead_end": True,
                        "issues": ["Page has issue: Orphan"],
                    },
                ],
            },
        )
        db_session.add(check)
        await db_session.commit()
        await db_session.refresh(check)

        f1 = LinkFinding(
            check_id=check.id,
            category="standard",
            type="broken_internal",
            severity="high",
            target_url="https://example.com/missing-page",
            status_code=404,
            evidence={"sources": [{"source_url": "https://example.com/", "anchor_text": "Missing"}]},
            recommendation={"action": "Fix broken link"},
        )
        f2 = LinkFinding(
            check_id=check.id,
            category="optimization",
            type="deep_page",
            severity="low",
            target_url="https://example.com/deep/page",
            status_code=200,
            evidence={"sources": []},
            recommendation={"action": "Move page closer to root"},
        )
        db_session.add_all([f1, f2])
        await db_session.commit()

        with patch("app.modules.seprate_checks.link_analysis.router.get_redis") as mock_get_redis:
            mock_get_redis.return_value = mock_redis
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                # 1. Unfiltered request
                r_all = await ac.get(f"/api/v1/link-analysis/check/{check.id}")
                assert r_all.status_code == 200
                d_all = r_all.json()
                assert d_all["status"] == "completed"
                assert len(d_all["findings"]) == 2
                assert d_all["total_findings"] == 2
                assert len(d_all["pages"]) == 2

                # 2. Filter by type alias (?type=broken_internal)
                r_type = await ac.get(f"/api/v1/link-analysis/check/{check.id}?type=broken_internal")
                assert r_type.status_code == 200
                d_type = r_type.json()
                assert len(d_type["findings"]) == 1
                assert d_type["total_findings"] == 1
                assert d_type["findings"][0]["type"] == "broken_internal"

                # 3. Filter by category (?category=optimization)
                r_cat = await ac.get(f"/api/v1/link-analysis/check/{check.id}?category=optimization")
                assert r_cat.status_code == 200
                d_cat = r_cat.json()
                assert len(d_cat["findings"]) == 1
                assert d_cat["total_findings"] == 1
                assert d_cat["findings"][0]["type"] == "deep_page"

                # 4. Filter by severity (?severity=high)
                r_sev = await ac.get(f"/api/v1/link-analysis/check/{check.id}?severity=high")
                assert r_sev.status_code == 200
                d_sev = r_sev.json()
                assert len(d_sev["findings"]) == 1
                assert d_sev["total_findings"] == 1

                # 5. Filter by search (?search=missing)
                r_srch = await ac.get(f"/api/v1/link-analysis/check/{check.id}?search=missing")
                assert r_srch.status_code == 200
                d_srch = r_srch.json()
                assert len(d_srch["findings"]) == 1
                assert d_srch["total_findings"] == 1

                # 6. Filter pages (?is_orphan=true)
                r_orphan = await ac.get(f"/api/v1/link-analysis/check/{check.id}?is_orphan=true")
                assert r_orphan.status_code == 200
                d_orphan = r_orphan.json()
                assert len(d_orphan["pages"]) == 1
                assert d_orphan["pages"][0]["url"] == "https://example.com/orphan-page"

