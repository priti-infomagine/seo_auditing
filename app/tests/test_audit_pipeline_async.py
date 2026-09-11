"""
End-to-end integration tests for the async SEO audit pipeline.

Covers the core endpoints and their full lifecycle:

  1. POST /audit/analyze               -> 202 + { audit_id, crawl_id, task_id, urls }
  2. GET  /audit/status/{audit_id}     -> { parse_status, evaluate_status, score_status }
  3. GET  /audit/result/{audit_id}     -> 200 (full audit payload after the pipeline finishes)
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
from app.core.security import get_current_user
from app.shared.tasks.celery_app import celery_app
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.page_network_data import PageNetworkData
from app.modules.crawler.models.page_seo_data import PageSEOData
from app.modules.crawler.models.page_snapshots import PageSnapshot
from app.modules.audit.services.analysis_scorer_service import AnalysisScorerService
from app.modules.audit.services.db_parser_service import DBParserService
from app.modules.audit.services.rule_evaluator_service import RuleEvaluatorService


# --------------------------------------------------------------------- fixtures


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
        state="PENDING",
        info={"stage": "crawling"},
        result=None,
    )


@pytest.fixture
def mock_celery(monkeypatch):
    _captured_send_tasks.clear()
    monkeypatch.setattr(celery_app, "send_task", _fake_send_task)
    monkeypatch.setattr(celery_app, "AsyncResult", _fake_async_result)
    return SimpleNamespace(captured_tasks=_captured_send_tasks)


@pytest.fixture
def captured_send_tasks():
    return _captured_send_tasks


async def _seed_crawl(
    db: AsyncSession,
    audit_id: uuid.UUID,
    n_pages: int = 2,
) -> list:
    """Seed a minimal but realistic crawl (pages + snapshots + SEO + network)."""
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


async def _run_pipeline(
    audit_id: uuid.UUID,
    session_factory,
) -> Dict[str, Any]:
    """Drive the parse -> evaluate -> score pipeline inline (no worker)."""
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


# =====================================================================
# 1. POST /audit/analyze — task queued but no worker
# =====================================================================


@pytest.mark.asyncio
async def test_post_analyze_queued_when_no_worker(mock_celery):
    import time
    started = time.perf_counter()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0, f"POST /audit/analyze took {elapsed:.2f}s; expected < 5s"
    assert response.status_code == 202, response.text
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "queued"
    assert data["url"] == "https://example.com/"
    assert data["domain"] == "example.com"
    assert data["full_pipeline"] is True

    for key in ("audit_id", "crawl_id", "task_id"):
        assert data[key], f"{key!r} is empty"
    uuid.UUID(data["audit_id"])
    uuid.UUID(data["crawl_id"])
    assert isinstance(data["task_id"], str) and data["task_id"]

    assert data["task_status_url"].endswith(f"/task/{data['task_id']}")
    assert data["crawl_status_url"].endswith(f"/{data['audit_id']}")
    assert data["pipeline_status_url"].endswith(f"/{data['audit_id']}")
    assert data["result_url"].endswith(f"/{data['audit_id']}")


@pytest.mark.asyncio
async def test_post_analyze_enqueues_crawler_task_only(
    mock_celery, captured_send_tasks
):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/", "full_pipeline": True},
        )

    assert len(captured_send_tasks) == 1, captured_send_tasks
    task = captured_send_tasks[0]
    assert task["name"] == "crawler.crawl_website"
    assert task["queue"] == "crawler"
    assert len(task["args"]) == 3


@pytest.mark.asyncio
async def test_post_analyze_format_compact_echoed_into_urls(mock_celery):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r1 = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        r2 = await client.post(
            "/api/v1/audit/analyze?format=full",
            json={"url": "https://example.com/"},
        )
        r3 = await client.post(
            "/api/v1/audit/analyze?format=compact",
            json={"url": "https://example.com/"},
        )

    for resp in (r1, r2, r3):
        assert resp.status_code == 202

    d1, d2, d3 = r1.json(), r2.json(), r3.json()

    for key in ("result_url", "result_project_url"):
        assert "format=" not in d1[key], (key, d1[key])
        assert "format=" not in d2[key], (key, d2[key])

    assert d3["result_url"].endswith("format=compact")
    assert d3["result_project_url"].endswith("format=compact")


@pytest.mark.asyncio
async def test_post_analyze_invalid_url_returns_422(mock_celery):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": ""},
        )
    assert response.status_code == 422
    assert "detail" in response.json()


# =====================================================================
# 2. GET /audit/status/{audit_id} — before any pipeline stage
# =====================================================================


@pytest.mark.asyncio
async def test_status_returns_202_pending_when_no_worker_and_no_data(
    mock_celery, _ensure_schema
):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        posted = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        audit_id = uuid.UUID(posted.json()["audit_id"])

        status_resp = await client.get(f"/api/v1/audit/status/{audit_id}")
    assert status_resp.status_code == 200, status_resp.text
    data = status_resp.json()
    assert data["audit_id"] == str(audit_id)
    for stage in ("parse_status", "evaluate_status", "score_status"):
        assert stage in data, f"missing {stage}"
    assert data["parse_status"] in {"missing", "pending"}
    assert data["evaluate_status"] in {"missing", "pending"}
    assert data["score_status"] in {"missing"}


@pytest.mark.asyncio
async def test_status_progresses_after_pipeline_runs(
    mock_celery, _ensure_schema
):
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        posted = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        audit_id = uuid.UUID(posted.json()["audit_id"])

        async with session_factory() as db:
            await _seed_crawl(db, audit_id, n_pages=2)
        await _run_pipeline(audit_id, session_factory)

        status_resp = await client.get(f"/api/v1/audit/status/{audit_id}")

    assert status_resp.status_code == 200, status_resp.text
    data = status_resp.json()
    assert data["parse_status"] == "completed"
    assert data["evaluate_status"] == "completed"
    assert data["score_status"] == "completed"
    assert 0 <= float(data["overall_score"]) <= 100
    assert data["grade"]
    assert data["pages_parsed"] >= 2
    assert data["rules_evaluated"] >= 1


# =====================================================================
# 3. GET /audit/result/{audit_id} — the contract
# =====================================================================


@pytest.mark.asyncio
async def test_result_returns_200_after_pipeline_finishes(
    mock_celery, _ensure_schema
):
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        posted = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        audit_id = uuid.UUID(posted.json()["audit_id"])

        async with session_factory() as db:
            await _seed_crawl(db, audit_id, n_pages=2)
        await _run_pipeline(audit_id, session_factory)

        async with session_factory() as db:
            job = await db.get(CrawlJob, audit_id)
            if job:
                job.status = "completed"
                await db.commit()

        result_resp = await client.get(
            f"/api/v1/audit/result/{audit_id}"
        )
    assert result_resp.status_code == 200, result_resp.text
    data = result_resp.json()
    assert data["audit"]["domain"] == "example.com"
    assert data["audit"]["url"] == "https://example.com/"
    for key in ("audit", "summary", "categories", "issues"):
        assert key in data, f"missing top-level key {key!r}"
    assert 0 <= data["summary"]["score"] <= 100


@pytest.mark.asyncio
async def test_result_format_compact_returns_overview(
    mock_celery, _ensure_schema
):
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        posted = await client.post(
            "/api/v1/audit/analyze?format=compact",
            json={"url": "https://example.com/"},
        )
        audit_id = uuid.UUID(posted.json()["audit_id"])

        async with session_factory() as db:
            await _seed_crawl(db, audit_id, n_pages=2)
        await _run_pipeline(audit_id, session_factory)

        async with session_factory() as db:
            job = await db.get(CrawlJob, audit_id)
            if job:
                job.status = "completed"
                await db.commit()

        result_resp = await client.get(
            f"/api/v1/audit/result/{audit_id}?format=compact"
        )
    assert result_resp.status_code == 200, result_resp.text
    data = result_resp.json()
    for key in ("audit", "summary", "categories", "top_issues"):
        assert key in data, f"missing compact top-level key {key!r}"


# =====================================================================
# 4. Full lifecycle: POST -> status -> result
# =====================================================================


@pytest.mark.asyncio
async def test_full_lifecycle_no_worker_does_not_break_clients(
    mock_celery, _ensure_schema
):
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        posted = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        assert posted.status_code == 202
        posted_data = posted.json()
        audit_id = uuid.UUID(posted_data["audit_id"])
        task_id = posted_data["task_id"]

        status_resp = await client.get(f"/api/v1/audit/status/{audit_id}")
        assert status_resp.status_code == 200
        status = status_resp.json()
        assert status["parse_status"] in {"missing", "pending"}
        assert status["evaluate_status"] in {"missing", "pending"}
        assert status["score_status"] == "missing"

        task_resp = await client.get(f"/api/v1/audit/analyze/task/{task_id}")
        assert task_resp.status_code == 200
        task = task_resp.json()
        assert task["task_id"] == task_id
        assert task["state"] == "PENDING"

        async with session_factory() as db:
            await _seed_crawl(db, audit_id, n_pages=2)
        await _run_pipeline(audit_id, session_factory)
        async with session_factory() as db:
            job = await db.get(CrawlJob, audit_id)
            if job:
                job.status = "completed"
                await db.commit()

        status_resp = await client.get(f"/api/v1/audit/status/{audit_id}")
        assert status_resp.status_code == 200
        status = status_resp.json()
        assert status["parse_status"] == "completed"
        assert status["evaluate_status"] == "completed"
        assert status["score_status"] == "completed"

        result_resp = await client.get(f"/api/v1/audit/result/{audit_id}")
        assert result_resp.status_code == 200
        data = result_resp.json()
        assert data["audit"]["domain"] == "example.com"
