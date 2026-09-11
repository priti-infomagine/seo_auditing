"""
Integration tests for POST /audit/analyze and related endpoints.
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from types import SimpleNamespace
from typing import Any, Dict, Optional

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.shared.tasks.celery_app import celery_app
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.page_network_data import PageNetworkData
from app.modules.crawler.models.page_seo_data import PageSEOData
from app.modules.crawler.models.page_snapshots import PageSnapshot
from app.modules.audit.services.analysis_scorer_service import AnalysisScorerService
from app.modules.audit.services.db_parser_service import DBParserService
from app.modules.audit.services.rule_evaluator_service import RuleEvaluatorService


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <title>{title}</title>
  <meta name="description" content="{description}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{url}">
</head>
<body>
  <h1>{title}</h1>
  <p>Some body text with enough words to produce a word count greater than ten
  for the content quality checks and to make the page non-trivial.</p>
  <a href="https://example.com/other">Internal link</a>
  <img src="https://example.com/img.png" alt="An image with alt text">
</body>
</html>"""


_captured_user_id: Optional[uuid.UUID] = None
_captured_send_tasks: list = []


def _fake_send_task(name, args=None, kwargs=None, queue=None, **opts):
    global _captured_user_id
    _captured_send_tasks.append({
        "name": name,
        "args": list(args or []),
        "queue": queue,
    })
    if args and len(args) >= 3:
        try:
            _captured_user_id = uuid.UUID(args[2])
        except (ValueError, TypeError):
            _captured_user_id = None
    return SimpleNamespace(id=str(uuid.uuid4()), state="PENDING")


def _fake_async_result(task_id):
    return SimpleNamespace(
        id=task_id,
        state="SUCCESS",
        info={"stage": "crawling"},
        result={"status": "completed"},
    )


@pytest.fixture
def mock_celery(monkeypatch):
    _captured_send_tasks.clear()
    monkeypatch.setattr(celery_app, "send_task", _fake_send_task)
    monkeypatch.setattr(celery_app, "AsyncResult", _fake_async_result)
    return SimpleNamespace(captured_tasks=_captured_send_tasks)


async def _seed_crawl(db: AsyncSession, audit_id: uuid.UUID, n_pages: int):
    pages = []
    for i in range(n_pages):
        url = f"https://example.com/page{i + 1}"
        norm = url
        page = CrawlPage(
            crawl_id=audit_id,
            url=url,
            normalized_url=norm,
            url_hash=hashlib.sha256(norm.encode()).hexdigest(),
            scheme="https",
            host="example.com",
            path=f"/page{i + 1}",
            depth=0,
            status_code=200,
            is_crawled=True,
            is_success=True,
            is_internal=True,
        )
        db.add(page)
        pages.append(page)
    await db.flush()

    for i, page in enumerate(pages):
        html = HTML_TEMPLATE.format(
            title=f"Test Page {i + 1}",
            description=(
                "A test meta description for SEO auditing purposes that is "
                "long enough."
            ),
            url=page.normalized_url,
        )
        db.add(PageSnapshot(page_id=page.id, content=html, compressed=False))
        db.add(PageSEOData(
            page_id=page.id,
            title=f"Test Page {i + 1}",
            title_length=len(f"Test Page {i + 1}"),
            meta_description=(
                "A test meta description for SEO auditing purposes that is "
                "long enough."
            ),
            meta_description_length=80,
            canonical=page.normalized_url,
            robots_meta="index,follow",
            language="en",
            word_count=30,
        ))
        db.add(PageNetworkData(
            page_id=page.id,
            status_code=200,
            content_type="text/html",
            response_time_ms=120,
        ))
    await db.commit()
    return pages


async def _run_pipeline(audit_id: uuid.UUID, session_factory):
    async with session_factory() as db:
        await DBParserService(db).parse_crawl(audit_id)
        await db.commit()
    async with session_factory() as db:
        await RuleEvaluatorService(db).evaluate_crawl(audit_id)
        await db.commit()
    async with session_factory() as db:
        result = await AnalysisScorerService(db).score_project(audit_id)
        await db.commit()
    return result


async def _poll_task_until_terminal(client, task_id, timeout=30.0):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        resp = await client.get(f"/api/v1/audit/analyze/task/{task_id}")
        assert resp.status_code == 200, resp.text
        if resp.json()["state"] in ("SUCCESS", "FAILURE"):
            return resp.json()["state"]
        await asyncio.sleep(0.2)
    return "TIMEOUT"


@pytest.mark.asyncio
async def test_audit_analyze_queued_returns_202(mock_celery):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )

    assert response.status_code == 202, response.text
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "queued"
    for key in ("audit_id", "crawl_id", "task_id"):
        assert data[key]
    assert data["task_status_url"].endswith(f"/task/{data['task_id']}")
    assert data["crawl_status_url"].endswith(f"/{data['audit_id']}")
    assert data["result_url"].endswith(f"/{data['audit_id']}")
    assert data["full_pipeline"] is True


@pytest.mark.asyncio
async def test_audit_analyze_full_pipeline_shape(mock_celery, _ensure_schema):
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        assert response.status_code == 202, response.text
        posted = response.json()
        audit_id = uuid.UUID(posted["audit_id"])
        task_id = posted["task_id"]

        async with session_factory() as db:
            await _seed_crawl(db, audit_id, n_pages=2)

        unified = await _run_pipeline(audit_id, session_factory)

        async with session_factory() as db:
            crawl_job = await db.get(CrawlJob, audit_id)
            if crawl_job:
                crawl_job.status = "completed"
                await db.commit()

        state = await _poll_task_until_terminal(client, task_id)
        assert state == "SUCCESS"

        result_resp = await client.get(
            f"/api/v1/audit/result/{audit_id}"
        )
        assert result_resp.status_code == 200, result_resp.text
        data = result_resp.json()

    audit = data["audit"]
    assert audit["domain"] == "example.com"


@pytest.mark.asyncio
async def test_audit_analyze_invalid_url_returns_422(mock_celery):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": ""},
        )
    assert response.status_code == 422
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_audit_analyze_multi_page_crawl(mock_celery, _ensure_schema):
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/", "max_pages": 100, "max_depth": 2},
        )
        assert response.status_code == 202, response.text
        posted = response.json()
        audit_id = uuid.UUID(posted["audit_id"])
        task_id = posted["task_id"]

        async with session_factory() as db:
            await _seed_crawl(db, audit_id, n_pages=3)

        await _run_pipeline(audit_id, session_factory)
        state = await _poll_task_until_terminal(client, task_id)
        assert state == "SUCCESS"

        result_resp = await client.get(
            f"/api/v1/audit/result/{audit_id}"
        )
        assert result_resp.status_code == 200, result_resp.text
        data = result_resp.json()

    assert data["audit"]["crawl_stats"]["pages_discovered"] >= 3
    assert data["audit"]["pages"]["crawled"] >= 3


@pytest.mark.asyncio
async def test_audit_analyze_full_pipeline_false(mock_celery):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/", "full_pipeline": False},
        )
    assert response.status_code == 202, response.text
    data = response.json()
    assert data["full_pipeline"] is False


@pytest.mark.asyncio
async def test_public_status_by_project(mock_celery, _ensure_schema):
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        assert response.status_code == 202
        audit_id = uuid.UUID(response.json()["audit_id"])

        status_resp = await client.get(f"/api/v1/audit/status/{audit_id}")
        assert status_resp.status_code == 200, status_resp.text
        data = status_resp.json()
        assert data["audit_id"] == str(audit_id)
        assert "parse_status" in data
        assert "evaluate_status" in data
        assert "score_status" in data
