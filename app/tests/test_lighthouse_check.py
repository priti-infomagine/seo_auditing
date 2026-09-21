"""
Tests for the async Lighthouse check API:

  * HTTP contract: POST /check (202 + ids), GET /status, GET /results, GET /task
  * Worker flow: run_check_async end-to-end (mocked crawl + pagespeed)
  * Validation: device / url / category -> error codes

Celery is mocked (no Redis), DB is the real Postgres via the conftest fixtures.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.database import async_session_factory
from app.shared.tasks.celery_app import celery_app
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.seprate_checks.google_lighthouse_check.model import (
    Device,
    PageStatus,
)
from app.modules.seprate_checks.google_lighthouse_check.pagespeed_client import (
    PagespeedClient,
)
from app.modules.seprate_checks.google_lighthouse_check.repository import (
    LighthousePageResultRepository,
)
from app.modules.seprate_checks.google_lighthouse_check.services import (
    LighthouseCheckService,
)


# ── Celery mocks ─────────────────────────────────────────────────────────


def _fake_send_task(name, args=None, kwargs=None, queue=None, **opts):
    captured.append(
        {
            "name": name,
            "args": list(args or []),
            "kwargs": dict(kwargs or {}),
            "queue": queue,
        }
    )
    return SimpleNamespace(id=f"fake-task-{uuid.uuid4()}", state="PENDING")


def _fake_async_result(task_id):
    return SimpleNamespace(
        id=task_id,
        state="PENDING",
        info={},
        result=None,
    )


captured: list = []


@pytest.fixture
def mock_celery(monkeypatch):
    captured.clear()
    monkeypatch.setattr(celery_app, "send_task", _fake_send_task)
    monkeypatch.setattr(celery_app, "AsyncResult", _fake_async_result)
    return SimpleNamespace(captured=captured)


# ── Helpers ───────────────────────────────────────────────────────────────


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── HTTP endpoint tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_returns_202_with_ids(mock_celery):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/lighthouse/check",
            json={
                "url": "https://example.com/",
                "device": "mobile",
                "category": ["performance", "seo"],
                "max_pages": 5,
            },
        )

    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "queued"
    check_id = data["check_id"]
    uuid.UUID(check_id)  # valid UUID
    assert data["task_id"].startswith("fake-task-")
    assert data["domain"] == "example.com"
    assert data["device"] == "mobile"
    assert data["categories"] == ["performance", "seo"]
    assert data["status_url"] == f"/api/v1/lighthouse/status/{check_id}"
    assert data["result_url"] == f"/api/v1/lighthouse/results/{check_id}"

    # CrawlJob created + persisted with task_id
    async with async_session_factory() as db:
        job = await CrawlJobRepository(db).get_by_id(uuid.UUID(check_id))
        assert job is not None
        assert job.status == "queued"
        assert job.crawl_config["phase"] == "queued"
        assert job.crawl_config["task_id"] == data["task_id"]
        assert job.crawl_config["device"] == "mobile"
        assert job.crawl_config["categories"] == ["performance", "seo"]

    # Task enqueued on the lighthouse queue with correct args
    assert len(mock_celery.captured) == 1
    sent = captured[0]
    assert sent["name"] == "lighthouse.run_check"
    assert sent["queue"] == "lighthouse"
    assert sent["args"][0] == check_id
    assert sent["args"][1] == "https://example.com/"
    assert sent["args"][2] == "mobile"
    assert sent["args"][3] == 5
    assert sent["kwargs"]["category"] == ["performance", "seo"]
    assert sent["kwargs"]["pagespeed_concurrency"] == 5


@pytest.mark.asyncio
async def test_check_default_category(mock_celery):
    """Omitting category defaults to all four Lighthouse categories (the bug fix)."""
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/lighthouse/check",
            json={"url": "https://example.com/", "device": "desktop"},
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["device"] == "desktop"
    assert data["categories"] == [
        "performance",
        "seo",
        "best-practices",
        "accessibility",
    ]
    sent = captured[0]
    assert sent["kwargs"]["category"] == data["categories"]


@pytest.mark.asyncio
async def test_status_queued(mock_celery):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/lighthouse/check",
            json={"url": "https://example.com/", "device": "mobile"},
        )
        check_id = resp.json()["check_id"]
        s = await client.get(f"/api/v1/lighthouse/status/{check_id}")

    assert s.status_code == 200, s.text
    d = s.json()
    assert d["check_id"] == check_id
    assert d["status"] == "queued"
    assert d["phase"] == "queued"
    assert d["domain"] == "example.com"
    assert d["pagespeed_total"] == 0
    assert d["pagespeed_checked"] == 0
    assert d["progress_percent"] == 0
    assert d["result_url"] == f"/api/v1/lighthouse/results/{check_id}"


@pytest.mark.asyncio
async def test_status_not_found(mock_celery):
    async with await _client() as client:
        s = await client.get(f"/api/v1/lighthouse/status/{uuid.uuid4()}")
    assert s.status_code == 404


@pytest.mark.asyncio
async def test_status_invalid_check_id(mock_celery):
    async with await _client() as client:
        s = await client.get("/api/v1/lighthouse/status/not-a-uuid")
    assert s.status_code == 400


@pytest.mark.asyncio
async def test_task_status(mock_celery):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/lighthouse/check",
            json={"url": "https://example.com/", "device": "mobile"},
        )
        task_id = resp.json()["task_id"]
        t = await client.get(f"/api/v1/lighthouse/task/{task_id}")
    assert t.status_code == 200
    assert t.json()["state"] == "PENDING"
    assert t.json()["task_id"] == task_id


@pytest.mark.asyncio
async def test_results_not_found(mock_celery):
    async with await _client() as client:
        r = await client.get(f"/api/v1/lighthouse/results/{uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_results_empty_when_queued(mock_celery):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/lighthouse/check",
            json={"url": "https://example.com/", "device": "mobile"},
        )
        check_id = resp.json()["check_id"]
        r = await client.get(f"/api/v1/lighthouse/results/{check_id}")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_invalid_device_returns_422(mock_celery):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/lighthouse/check",
            json={"url": "https://example.com/", "device": "tablet"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_url_returns_422(mock_celery):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/lighthouse/check",
            json={"url": "not-a-url", "device": "mobile"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_category_returns_422(mock_celery):
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/lighthouse/check",
            json={
                "url": "https://example.com/",
                "device": "mobile",
                "category": ["performance", "bogus"],
            },
        )
    assert resp.status_code == 422


# ── Worker flow (run_check_async) with mocked crawl + pagespeed ────────────


@pytest.mark.asyncio
async def test_run_check_async_end_to_end(_ensure_schema):
    """Crawl → parallel pagespeed → completed, with live progress + persisted rows."""
    check_uuid = uuid.uuid4()

    # Pre-create the tracking CrawlJob exactly as prepare_check would.
    async with async_session_factory() as db:
        job = CrawlJob(
            id=check_uuid,
            user_id=uuid.uuid4(),
            url="https://example.com/",
            domain="example.com",
            status="queued",
            max_pages=10,
            max_depth=3,
            crawl_config={
                "phase": "queued",
                "task_id": None,
                "device": "mobile",
                "categories": ["performance", "seo"],
            },
        )
        await CrawlJobRepository(db).create(job)
        await db.commit()

    service = LighthouseCheckService()

    fake_urls = [
        "https://example.com/",
        "https://example.com/a",
        "https://example.com/b",
    ]

    # 1) Mock the crawl phase -> return discovered URLs without touching the web.
    async def fake_crawl(cid, url, max_pages, categories):
        return list(fake_urls)

    service._crawl_and_collect = fake_crawl

    # 2) Mock the PageSpeed API fetch + parse.  Capture the category handed to
    #    fetch to prove the `category` request field is actually wired through
    #    (it was a dead parameter before this change).
    fetch_categories: list = []

    async def fake_fetch(url, strategy=None, category=None):
        fetch_categories.append(category)
        return {"lighthouseResult": {"categories": {}, "audits": {}}}

    service.pagespeed_client.fetch = fake_fetch

    parse_calls: list = []

    def fake_parse(raw, url, device):
        parse_calls.append(url)
        return {
            "url": url,
            "device": device,
            "performance_score": 85,
            "seo_score": 90,
            "fcp_ms": 2000,
            "lcp_ms": 2500,
            "tbt_ms": 300,
            "cls": 0.1,
        }

    PagespeedClient.parse_result = staticmethod(fake_parse)

    # 3) Capture Celery progress updates.
    progress: list = []

    def fake_update_state(state="PENDING", meta=None):
        progress.append((state, dict(meta or {})))

    # Run the check.
    result = await service.run_check_async(
        check_id=check_uuid,
        url="https://example.com/",
        device="mobile",
        max_pages=10,
        category=["performance", "seo"],
        pagespeed_concurrency=2,
        update_state=fake_update_state,
    )

    # Result summary
    assert result["status"] == "completed"
    assert result["pagespeed_total"] == 3
    assert result["pagespeed_succeeded"] == 3
    assert result["pagespeed_failed"] == 0

    # Category wired through to every fetch call (was a dead parameter before).
    assert len(fetch_categories) == 3
    assert all(c == ["performance", "seo"] for c in fetch_categories)

    # CrawlJob finalized
    async with async_session_factory() as db:
        job = await CrawlJobRepository(db).get_by_id(check_uuid)
        assert job.status == "completed"
        cfg = job.crawl_config
        assert cfg["phase"] == "completed"
        assert cfg["pagespeed_total"] == 3
        assert cfg["pagespeed_succeeded"] == 3
        assert cfg["pagespeed_failed"] == 0
        assert job.completed_at is not None
        assert job.duration_ms is not None

        # Persisted result rows
        counts = await LighthousePageResultRepository(db).get_count_by_check_id(check_uuid)
        assert counts["success"] == 3
        assert counts["failed"] == 0
        assert counts["total"] == 3

        rows = await LighthousePageResultRepository(db).get_by_check_id(check_uuid)
        assert len(rows) == 3
        assert all(r.device == Device.MOBILE for r in rows)
        assert all(r.status == PageStatus.SUCCESS for r in rows)
        assert rows[0].performance_score == 85

    # Progress reported to Celery: 3 PROGRESS + 1 SUCCESS
    states = [s for s, _ in progress]
    assert states.count("PROGRESS") == 3
    assert "SUCCESS" in states
    assert len(parse_calls) == 3


@pytest.mark.asyncio
async def test_run_check_async_pagespeed_failure(_ensure_schema):
    """A failing PageSpeed call records a FAILED row, not a crash."""
    check_uuid = uuid.uuid4()
    async with async_session_factory() as db:
        job = CrawlJob(
            id=check_uuid, user_id=uuid.uuid4(),
            url="https://example.com/", domain="example.com",
            status="queued", max_pages=10, max_depth=3,
            crawl_config={"phase": "queued", "task_id": None, "device": "mobile",
                          "categories": ["performance"]},
        )
        await CrawlJobRepository(db).create(job)
        await db.commit()

    service = LighthouseCheckService()
    fake_urls = ["https://example.com/", "https://example.com/a"]

    async def fake_crawl(cid, url, max_pages, categories):
        return list(fake_urls)

    service._crawl_and_collect = fake_crawl

    async def failing_fetch(url, strategy=None, category=None):
        raise Exception("upstream 5xx")

    service.pagespeed_client.fetch = failing_fetch

    PagespeedClient.parse_result = staticmethod(
        lambda raw, url, device: {"url": url, "device": device}
    )

    progress: list = []
    def upd(state="PENDING", meta=None):
        progress.append((state, dict(meta or {})))

    result = await service.run_check_async(
        check_id=check_uuid, url="https://example.com/",
        device="mobile", max_pages=10, pagespeed_concurrency=2,
        update_state=upd,
    )

    assert result["status"] == "completed"
    assert result["pagespeed_succeeded"] == 0
    assert result["pagespeed_failed"] == 2

    async with async_session_factory() as db:
        counts = await LighthousePageResultRepository(db).get_count_by_check_id(check_uuid)
        assert counts["success"] == 0
        assert counts["failed"] == 2
        rows = await LighthousePageResultRepository(db).get_by_check_id(check_uuid)
        assert all(r.status == PageStatus.FAILED for r in rows)
        assert all(r.reason for r in rows)
    assert "SUCCESS" in [s for s, _ in progress]
