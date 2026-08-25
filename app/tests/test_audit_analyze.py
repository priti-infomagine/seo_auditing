"""
Integration tests for the Audit Analyze API endpoint (async / queued flow).

POST /api/v1/audit/analyze now *queues* a Celery task and returns 202 with
crawl_id / project_id / task_id and status URLs. The crawl then triggers the
parse → evaluate → score pipeline. These tests:

  1. Assert POST returns 202 with the queued identifiers.
  2. Simulate the crawl offline (no network) by seeding CrawlPage + snapshot +
     SEO + network rows, then run the real parser/evaluator/scorer services
     against the same Postgres database (this exercises the N+1 batch-fetch
     refactor in parse/evaluate/response-build).
  3. Poll GET /audit/analyze/task/{task_id} until a terminal state.
  4. GET /audit/result/{crawl_id}?project_id=... and assert the unified shape.

Celery broker/backend are bypassed: send_task is patched to a no-op and
AsyncResult is patched to report SUCCESS, so no worker/Redis is required.
"""
import hashlib
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.core.database import async_session_factory, engine, Base
from app.core.security import get_current_user
from app.shared.tasks.celery_app import celery_app
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.page_snapshots import PageSnapshot
from app.modules.crawler.models.page_seo_data import PageSEOData
from app.modules.crawler.models.page_network_data import PageNetworkData
from app.modules.audit.services.db_parser_service import DBParserService
from app.modules.audit.services.rule_evaluator_service import RuleEvaluatorService
from app.modules.audit.services.analysis_scorer_service import AnalysisScorerService


@pytest.fixture(autouse=True)
async def _ensure_schema():
    """Make sure all tables (incl. unique constraints) exist for the test DB."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


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


def _fake_send_task(name, args=None, kwargs=None, queue=None, **opts):
    # Bypass the broker entirely — the pipeline is run by the test directly.
    return SimpleNamespace(id=str(uuid.uuid4()), state="PENDING")


def _fake_async_result(task_id):
    # The test runs the pipeline itself, so report a terminal SUCCESS state.
    return SimpleNamespace(state="SUCCESS", result=None, info=None)


@pytest.fixture
def queued_audit_setup(monkeypatch):
    """Patch auth + Celery so the queued flow works without a worker/Redis."""
    fake_user = SimpleNamespace(id=uuid.uuid4())

    app.dependency_overrides[get_current_user] = lambda: fake_user
    monkeypatch.setattr(celery_app, "send_task", _fake_send_task)
    monkeypatch.setattr(celery_app, "AsyncResult", _fake_async_result)

    yield fake_user

    app.dependency_overrides.clear()


async def _seed_crawl(db: AsyncSession, crawl_id: uuid.UUID, project_id: uuid.UUID, n_pages: int):
    """Persist synthetic crawl pages + related rows (offline, no network)."""
    pages = []
    for i in range(n_pages):
        url = f"https://example.com/page{i + 1}"
        norm = url
        page = CrawlPage(
            crawl_id=crawl_id,
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
            description="A test meta description for SEO auditing purposes that is long enough.",
            url=page.normalized_url,
        )
        db.add(PageSnapshot(page_id=page.id, content=html, compressed=False))
        db.add(PageSEOData(
            page_id=page.id,
            title=f"Test Page {i + 1}",
            title_length=len(f"Test Page {i + 1}"),
            meta_description="A test meta description for SEO auditing purposes that is long enough.",
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


async def _run_pipeline(crawl_id: uuid.UUID, project_id: uuid.UUID):
    """Run the real parse → evaluate → score pipeline against the DB."""
    async with async_session_factory() as db:
        await DBParserService(db).parse_crawl(project_id, crawl_id)
        await db.commit()
    async with async_session_factory() as db:
        await RuleEvaluatorService(db).evaluate_crawl(project_id, crawl_id)
        await db.commit()
    async with async_session_factory() as db:
        result = await AnalysisScorerService(db).score_project(project_id, crawl_id)
        await db.commit()
    return result


async def _poll_task_until_terminal(client, task_id, timeout=30.0):
    import asyncio
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
async def test_audit_analyze_queued_returns_202(queued_audit_setup):
    """POST /audit/analyze queues and returns 202 with identifiers + URLs."""
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
    for key in ("crawl_id", "project_id", "task_id"):
        assert data[key]
    assert data["task_status_url"].endswith(f"/task/{data['task_id']}")
    assert data["crawl_status_url"].endswith(f"/{data['crawl_id']}")
    assert data["result_url"].endswith(f"/{data['crawl_id']}?project_id={data['project_id']}")


@pytest.mark.asyncio
async def test_audit_analyze_full_pipeline_shape(queued_audit_setup):
    """
    Queue, simulate the offline crawl, run the real pipeline, then assert the
    unified result shape (mirrors the original synchronous assertions).
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        assert response.status_code == 202, response.text
        posted = response.json()
        crawl_id = uuid.UUID(posted["crawl_id"])
        project_id = uuid.UUID(posted["project_id"])
        task_id = posted["task_id"]

        # Simulate the crawl offline.
        async with async_session_factory() as db:
            _seed_crawl(db, crawl_id, project_id, n_pages=2)

        # Run the real pipeline (parse → evaluate → score).
        unified = await _run_pipeline(crawl_id, project_id)

        # Poll task endpoint until terminal.
        state = await _poll_task_until_terminal(client, task_id)
        assert state == "SUCCESS"

        # Fetch the final result.
        result_resp = await client.get(
            f"/api/v1/audit/result/{crawl_id}?project_id={project_id}"
        )
        assert result_resp.status_code == 200, result_resp.text
        data = result_resp.json()

    # --- audit block ---
    audit = data["audit"]
    assert audit["domain"] == "example.com"
    assert audit["url"] == "https://example.com/"
    assert audit["pages_crawled"] >= 1
    assert audit["pages_analyzed"] >= 1
    assert audit["pages_discovered"] >= 1
    assert audit["status"] == "completed"

    # --- summary ---
    summary = data["summary"]
    assert "overall_score" in summary
    assert 0 <= summary["overall_score"] <= 100
    assert summary["health"] in {"excellent", "good", "needs_attention", "poor", "critical"}
    for key in ("critical_issues", "high_issues", "medium_issues", "low_issues"):
        assert isinstance(summary[key], int)

    # --- categories ---
    categories = data["categories"]
    assert isinstance(categories, list) and len(categories) >= 1
    cat_ids = {c["id"] for c in categories}
    for expected in ("on_page", "technical_seo", "content_quality", "performance"):
        assert expected in cat_ids, f"missing category {expected}"

    # --- issues: strict slim shape {page_url, affected_part} + current_value ---
    issues = data["issues"]
    assert isinstance(issues, list)
    for issue in issues:
        assert {"page_url", "affected_part", "rule_id", "severity", "message"} <= set(issue.keys())
        assert issue["page_url"]
        assert issue["affected_part"]

    # --- category_results ---
    category_results = data["category_results"]
    assert isinstance(category_results, dict)
    assert "on_page" in category_results

    # --- crawl / indexation ---
    crawl = data["crawl"]
    assert crawl["pages_discovered"] >= 1
    assert "status_codes" in crawl
    indexation = data["indexation"]
    assert "indexable" in indexation
    assert "noindex" in indexation

    # --- priorities + recommendations ---
    priorities = data["priorities"]
    assert {"critical", "high", "medium", "low"} <= set(priorities.keys())
    recommendations = data["recommendations"]
    assert isinstance(recommendations, list)

    # --- errors + metadata ---
    assert isinstance(data["errors"], list)
    assert data["metadata"]["output_shape"] == "unified_v1"


@pytest.mark.asyncio
async def test_audit_analyze_invalid_url_queued(queued_audit_setup):
    """
    An invalid/unreachable URL is still auto-corrected to https:// and queued
    (the crawl failure happens in the worker, not in the request). The endpoint
    now returns 202 rather than 500.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "not-a-valid-url"},
        )
    assert response.status_code == 202, response.text
    assert response.json()["task_id"]


@pytest.mark.asyncio
async def test_audit_analyze_empty_url():
    """An empty URL fails Pydantic validation before queueing (422)."""
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
async def test_audit_analyze_max_pages_floor_validation():
    """max_pages below the schema floor (ge=20) must return 422."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/", "max_pages": 5},
        )
    assert response.status_code == 422
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_audit_analyze_multi_page_crawl(queued_audit_setup):
    """
    Queue, seed multiple pages offline, run the pipeline, and assert the
    unified result reflects the multi-page crawl.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/", "max_pages": 100, "max_depth": 2},
        )
        assert response.status_code == 202, response.text
        posted = response.json()
        crawl_id = uuid.UUID(posted["crawl_id"])
        project_id = uuid.UUID(posted["project_id"])
        task_id = posted["task_id"]

        async with async_session_factory() as db:
            _seed_crawl(db, crawl_id, project_id, n_pages=3)

        await _run_pipeline(crawl_id, project_id)
        state = await _poll_task_until_terminal(client, task_id)
        assert state == "SUCCESS"

        result_resp = await client.get(
            f"/api/v1/audit/result/{crawl_id}?project_id={project_id}"
        )
        assert result_resp.status_code == 200, result_resp.text
        data = result_resp.json()

    assert data["crawl"]["pages_discovered"] >= 3
    assert data["audit"]["pages_crawled"] >= 3
