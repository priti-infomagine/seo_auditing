"""
Integration tests for the Audit Analyze API endpoint (async / queued flow).
...
"""
import hashlib
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.core.database import get_db
from app.core.security import get_current_user
from app.shared.tasks.celery_app import celery_app
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.page_snapshots import PageSnapshot
from app.modules.crawler.models.page_seo_data import PageSEOData
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.models.page_network_data import PageNetworkData
from app.modules.audit.services.db_parser_service import DBParserService
from app.modules.audit.services.rule_evaluator_service import RuleEvaluatorService
from app.modules.audit.services.analysis_scorer_service import AnalysisScorerService


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


_captured_user_id = None


def _fake_send_task(name, args=None, kwargs=None, queue=None, **opts):
    global _captured_user_id
    _captured_user_id = uuid.UUID(args[2]) if args and len(args) > 2 else None
    return SimpleNamespace(id=str(uuid.uuid4()), state="PENDING")


def _fake_async_result(task_id):
    return SimpleNamespace(state="SUCCESS", result=None, info=None)


@pytest.fixture
def mock_celery(monkeypatch):
    """Patch Celery + auth so the queued flow works without a worker/Redis."""
    global _captured_user_id
    _captured_user_id = None
    monkeypatch.setattr(celery_app, "send_task", _fake_send_task)
    monkeypatch.setattr(celery_app, "AsyncResult", _fake_async_result)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=_captured_user_id)

    yield

    app.dependency_overrides.clear()


async def _seed_crawl(db: AsyncSession, crawl_id: uuid.UUID, project_id: uuid.UUID, n_pages: int):
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


async def _run_pipeline(crawl_id: uuid.UUID, project_id: uuid.UUID, session_factory):
    async with session_factory() as db:
        await DBParserService(db).parse_crawl(project_id, crawl_id)
        await db.commit()
    async with session_factory() as db:
        await RuleEvaluatorService(db).evaluate_crawl(project_id, crawl_id)
        await db.commit()
    async with session_factory() as db:
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
    for key in ("crawl_id", "project_id", "task_id"):
        assert data[key]
    assert data["task_status_url"].endswith(f"/task/{data['task_id']}")
    assert data["crawl_status_url"].endswith(f"/{data['crawl_id']}")
    assert data["result_url"].endswith(f"/{data['crawl_id']}?project_id={data['project_id']}")
    assert data["full_pipeline"] is True
    assert data["result_project_url"].endswith(f"/project/{data['project_id']}")


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
        crawl_id = uuid.UUID(posted["crawl_id"])
        project_id = uuid.UUID(posted["project_id"])
        task_id = posted["task_id"]

        async with session_factory() as db:
            await _seed_crawl(db, crawl_id, project_id, n_pages=2)

        unified = await _run_pipeline(crawl_id, project_id, session_factory)

        # Mark crawl completed for offline test (real crawler updates this).
        async with session_factory() as db:
            crawl_job = await db.get(CrawlJob, crawl_id)
            if crawl_job:
                crawl_job.status = "completed"
                await db.commit()

        state = await _poll_task_until_terminal(client, task_id)
        assert state == "SUCCESS"

        result_resp = await client.get(
            f"/api/v1/audit/result/{crawl_id}?project_id={project_id}"
        )
        assert result_resp.status_code == 200, result_resp.text
        data = result_resp.json()

    audit = data["audit"]
    assert audit["domain"] == "example.com"
    assert audit["url"] == "https://example.com/"
    assert audit["pages_crawled"] >= 1
    assert audit["pages_analyzed"] >= 1
    assert audit["pages_discovered"] >= 1
    assert audit["status"] == "completed"

    summary = data["summary"]
    assert "overall_score" in summary
    assert 0 <= summary["overall_score"] <= 100
    assert summary["health"] in {"excellent", "good", "needs_attention", "poor", "critical"}
    for key in ("critical_issues", "high_issues", "medium_issues", "low_issues"):
        assert isinstance(summary[key], int)

    categories = data["categories"]
    assert isinstance(categories, list) and len(categories) >= 1
    cat_ids = {c["id"] for c in categories}
    for expected in ("on_page", "technical_seo", "content_quality", "performance"):
        assert expected in cat_ids, f"missing category {expected}"

    issues = data["issues"]
    assert isinstance(issues, list)
    for issue in issues:
        assert {"page_url", "affected_part", "rule_id", "severity", "message"} <= set(issue.keys())
        assert issue["page_url"]
        assert issue["affected_part"]

    category_results = data["category_results"]
    assert isinstance(category_results, dict)
    assert "on_page" in category_results

    crawl = data["crawl"]
    assert crawl["pages_discovered"] >= 1
    assert "status_codes" in crawl
    indexation = data["indexation"]
    assert "indexable" in indexation
    assert "noindex" in indexation

    priorities = data["priorities"]
    assert {"critical", "high", "medium", "low"} <= set(priorities.keys())
    recommendations = data["recommendations"]
    assert isinstance(recommendations, list)

    assert isinstance(data["errors"], list)
    assert data["metadata"]["output_shape"] == "unified_v1"


@pytest.mark.asyncio
async def test_audit_analyze_invalid_url_queued(mock_celery):
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
async def test_audit_analyze_empty_url(mock_celery):
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
async def test_audit_analyze_max_pages_floor_validation(mock_celery):
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
        crawl_id = uuid.UUID(posted["crawl_id"])
        project_id = uuid.UUID(posted["project_id"])
        task_id = posted["task_id"]

        async with session_factory() as db:
            await _seed_crawl(db, crawl_id, project_id, n_pages=3)

        await _run_pipeline(crawl_id, project_id, session_factory)
        state = await _poll_task_until_terminal(client, task_id)
        assert state == "SUCCESS"

        result_resp = await client.get(
            f"/api/v1/audit/result/{crawl_id}?project_id={project_id}"
        )
        assert result_resp.status_code == 200, result_resp.text
        data = result_resp.json()

    assert data["crawl"]["pages_discovered"] >= 3
    assert data["audit"]["pages_crawled"] >= 3


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
    assert data["result_project_url"].endswith(f"/project/{data['project_id']}")


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
        project_id = uuid.UUID(response.json()["project_id"])

        # Public status check (no auth)
        status_resp = await client.get(f"/api/v1/audit/status/{project_id}")
        assert status_resp.status_code == 200, status_resp.text
        data = status_resp.json()
        assert data["project_id"] == str(project_id)
        assert "parse_status" in data
        assert "evaluate_status" in data
        assert "score_status" in data


@pytest.mark.asyncio
async def test_public_result_by_project(mock_celery, _ensure_schema):
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Queue an audit
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        assert response.status_code == 202, response.text
        posted = response.json()
        project_id = uuid.UUID(posted["project_id"])
        crawl_id = uuid.UUID(posted["crawl_id"])

        # Before analysis completes → 202
        result_resp = await client.get(f"/api/v1/audit/result/project/{project_id}")
        assert result_resp.status_code == 202

        # Seed data and run pipeline
        async with session_factory() as db:
            await _seed_crawl(db, crawl_id, project_id, n_pages=2)
        await _run_pipeline(crawl_id, project_id, session_factory)

        # Mark crawl completed
        async with session_factory() as db:
            crawl_job = await db.get(CrawlJob, crawl_id)
            if crawl_job:
                crawl_job.status = "completed"
                await db.commit()

        # After analysis → 200 with full response
        result_resp = await client.get(f"/api/v1/audit/result/project/{project_id}")
        assert result_resp.status_code == 200, result_resp.text
        data = result_resp.json()
        assert "audit" in data
        assert "summary" in data
        assert data["audit"]["domain"] == "example.com"
