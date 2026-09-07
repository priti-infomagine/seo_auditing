"""
End-to-end integration tests for the async SEO audit pipeline.

Covers the three core endpoints and their full lifecycle:

  1. POST /audit/analyze               -> 202 + { crawl_id, project_id, task_id, urls }
  2. GET  /audit/status/{project_id}   -> { parse_status, evaluate_status, score_status }
  3. GET  /audit/result/project/{project_id}
        -> 202 (still processing)  OR
        -> 200 (full audit payload after the pipeline finishes)

The tests use ``mock_celery`` + ``_ensure_schema`` fixtures to:
* Replace Celery ``send_task`` with a no-op so POST /audit/analyze works
  without a live Redis broker / Celery worker.
* Replace Celery ``AsyncResult`` so task polling works without a real
  result backend.
* Stand up a clean PostgreSQL test database (``app/tests/conftest.py``)
  so crawl jobs, parsed facts, rule results, and the SeoAnalysisRun row
  are all real and observable.

The "task is queued but no worker" scenario is the central case: a POST
queues the audit, the worker never picks it up, and we assert the
**expected observed behaviour** of all three endpoints from the
client's perspective — i.e.:

  * POST /audit/analyze   -> 202 with the polling URLs.
  * GET  /audit/status/.. -> status report (likely 'pending' / 'missing').
  * GET  /audit/result/.. -> 202 because no run has finished.
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
    """Record every enqueued task so the test can assert on the side effects
    of POST /audit/analyze without a real worker."""
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
    """No real result backend: every task stays in PENDING state forever.

    This is the "task is queued but no worker" case the user asked about.
    """
    return SimpleNamespace(state="PENDING", result=None, info=None)


@pytest.fixture
def mock_celery(monkeypatch):
    """Patch Celery + auth so the queued flow works without a worker/Redis."""
    global _captured_user_id, _captured_send_tasks
    _captured_user_id = None
    _captured_send_tasks = []

    monkeypatch.setattr(celery_app, "send_task", _fake_send_task)
    monkeypatch.setattr(celery_app, "AsyncResult", _fake_async_result)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=_captured_user_id
    )

    yield

    app.dependency_overrides.clear()


@pytest.fixture
def captured_send_tasks():
    """Read-only view of the tasks the most recent POST /audit/analyze enqueued."""
    return _captured_send_tasks


# --------------------------------------------------------------------- helpers


async def _seed_crawl(
    db: AsyncSession,
    crawl_id: uuid.UUID,
    project_id: uuid.UUID,
    n_pages: int = 2,
) -> list:
    """Seed a minimal but realistic crawl (pages + snapshots + SEO + network)."""
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
    crawl_id: uuid.UUID,
    project_id: uuid.UUID,
    session_factory,
) -> Dict[str, Any]:
    """Drive the parse -> evaluate -> score pipeline inline (no worker)."""
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


# =====================================================================
# 1. POST /audit/analyze — task queued but no worker
# =====================================================================


@pytest.mark.asyncio
async def test_post_analyze_queued_when_no_worker(mock_celery):
    """The most important case the user asked about: the task is enqueued
    on Celery but no worker is ever started. The endpoint must still:

      * return 202
      * include crawl_id, project_id, task_id
      * include the polling/status URLs
      * NOT block on the worker (i.e. the response is immediate)
    """
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

    # Immediate return (no waiting for a worker)
    assert elapsed < 5.0, f"POST /audit/analyze took {elapsed:.2f}s; expected < 5s"
    assert response.status_code == 202, response.text
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "queued"
    assert data["url"] == "https://example.com/"
    assert data["domain"] == "example.com"
    assert data["full_pipeline"] is True

    # All identifiers are present and well-formed
    for key in ("crawl_id", "project_id", "task_id"):
        assert data[key], f"{key!r} is empty"
    # crawl_id / project_id are valid UUIDs
    uuid.UUID(data["crawl_id"])
    uuid.UUID(data["project_id"])
    # task_id is a non-empty string (Celery format)
    assert isinstance(data["task_id"], str) and data["task_id"]

    # All status URLs are wired up
    assert data["task_status_url"].endswith(f"/task/{data['task_id']}")
    assert data["crawl_status_url"].endswith(f"/{data['crawl_id']}")
    assert data["pipeline_status_url"].endswith(f"/{data['project_id']}")
    assert data["result_url"].endswith(
        f"/{data['crawl_id']}?project_id={data['project_id']}"
    )
    assert data["result_project_url"].endswith(f"/project/{data['project_id']}")


@pytest.mark.asyncio
async def test_post_analyze_enqueues_crawler_task_only(
    mock_celery, captured_send_tasks
):
    """Only the crawler.crawl_website task is enqueued at the POST /audit/analyze
    step. The analysis pipeline is fired by the crawler task itself, NOT
    by POST /audit/analyze (otherwise the worker would do nothing useful)."""
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
    # 3 positional args: crawl_id, url, user_id
    assert len(task["args"]) == 3


@pytest.mark.asyncio
async def test_post_analyze_format_compact_echoed_into_urls(mock_celery):
    """The new ?format=compact|full switch is echoed into the returned
    result_url and result_project_url. When the default is used, the URLs
    are byte-for-byte identical to the pre-feature format (no format
    suffix)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Default (no format param) — URLs are bare
        r1 = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        # Explicit full — same URL suffix as default (no &format=)
        r2 = await client.post(
            "/api/v1/audit/analyze?format=full",
            json={"url": "https://example.com/"},
        )
        # Compact — &format=compact is appended to the two result URLs
        r3 = await client.post(
            "/api/v1/audit/analyze?format=compact",
            json={"url": "https://example.com/"},
        )

    for resp in (r1, r2, r3):
        assert resp.status_code == 202

    d1, d2, d3 = r1.json(), r2.json(), r3.json()

    # Default + explicit full: no format suffix on the result URLs.
    for key in ("result_url", "result_project_url"):
        assert "format=" not in d1[key], (key, d1[key])
        assert "format=" not in d2[key], (key, d2[key])
        # Strip the UUIDs and project_id before comparing the URL *shape*
        # (UUIDs are freshly generated per request, so we can't compare
        # the full strings).
        def _strip_ids(url: str) -> str:
            import re
            return re.sub(r"[0-9a-f-]{36}", "<uuid>", url).replace(
                "project_id=<uuid>", "project_id=<uuid>"
            )
        assert _strip_ids(d1[key]) == _strip_ids(d2[key]), (key, d1[key], d2[key])

    # Compact: &format=compact appended to BOTH result URLs (and only those).
    assert d3["result_url"].endswith("&format=compact")
    assert d3["result_project_url"].endswith("&format=compact")
    for url in (
        d3["task_status_url"],
        d3["crawl_status_url"],
        d3["pipeline_status_url"],
    ):
        assert "format=" not in url


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
# 2. GET /audit/status/{project_id} — before any pipeline stage
# =====================================================================


@pytest.mark.asyncio
async def test_status_returns_202_pending_when_no_worker_and_no_data(
    mock_celery, _ensure_schema
):
    """POST queued the task but no worker is running, AND no pipeline row
    has been written. The status endpoint must return 200 (it is a
    public status endpoint), and report all stages as 'pending' or
    'missing' — never 500 or 404."""
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        posted = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        project_id = uuid.UUID(posted.json()["project_id"])

        status_resp = await client.get(f"/api/v1/audit/status/{project_id}")
    assert status_resp.status_code == 200, status_resp.text
    data = status_resp.json()
    assert data["project_id"] == str(project_id)
    for stage in ("parse_status", "evaluate_status", "score_status"):
        assert stage in data, f"missing {stage}"
    # No rows anywhere → parse_status is 'missing' (no parsed facts),
    # evaluate_status is 'missing', score_status is 'missing'.
    assert data["parse_status"] in {"missing", "pending"}
    assert data["evaluate_status"] in {"missing", "pending"}
    assert data["score_status"] in {"missing"}


@pytest.mark.asyncio
async def test_status_progresses_after_pipeline_runs(
    mock_celery, _ensure_schema
):
    """Once the pipeline runs (parse → evaluate → score), the status flips
    to 'completed' for each stage. This proves the endpoint reflects real
    DB state and isn't just a static 'pending' response."""
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        posted = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        crawl_id = uuid.UUID(posted.json()["crawl_id"])
        project_id = uuid.UUID(posted.json()["project_id"])

        async with session_factory() as db:
            await _seed_crawl(db, crawl_id, project_id, n_pages=2)
        await _run_pipeline(crawl_id, project_id, session_factory)

        status_resp = await client.get(f"/api/v1/audit/status/{project_id}")

    assert status_resp.status_code == 200, status_resp.text
    data = status_resp.json()
    assert data["parse_status"] == "completed"
    assert data["evaluate_status"] == "completed"
    assert data["score_status"] == "completed"
    # Score should also carry the scalar summary fields
    assert 0 <= float(data["overall_score"]) <= 100
    assert data["grade"]
    assert data["pages_parsed"] >= 2
    assert data["rules_evaluated"] >= 1


# =====================================================================
# 3. GET /audit/result/project/{project_id} — the 202 vs 200 contract
# =====================================================================


@pytest.mark.asyncio
async def test_result_by_project_returns_202_before_pipeline_finishes(
    mock_celery, _ensure_schema
):
    """The project-keyed result endpoint must return 202 (not 404, not
    500) when the analysis is still in progress — i.e. POST queued the
    task, no worker ever ran, and no SeoAnalysisRun row exists."""
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        posted = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        assert posted.status_code == 202
        project_id = uuid.UUID(posted.json()["project_id"])

        result_resp = await client.get(f"/api/v1/audit/result/project/{project_id}")
    assert result_resp.status_code == 202
    detail = result_resp.json()["detail"]
    assert detail["status"] == "processing"
    assert detail["project_id"] == str(project_id)
    assert "Poll" in detail["message"] or "audit" in detail["message"].lower()


@pytest.mark.asyncio
async def test_result_by_project_returns_200_after_pipeline_finishes(
    mock_celery, _ensure_schema
):
    """After the pipeline runs, the same endpoint must return 200 with
    the full UnifiedAuditResponse (default format=full)."""
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        posted = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        crawl_id = uuid.UUID(posted.json()["crawl_id"])
        project_id = uuid.UUID(posted.json()["project_id"])

        async with session_factory() as db:
            await _seed_crawl(db, crawl_id, project_id, n_pages=2)
        await _run_pipeline(crawl_id, project_id, session_factory)

        # Mark the crawl job completed (real crawler would do this)
        async with session_factory() as db:
            job = await db.get(CrawlJob, crawl_id)
            if job:
                job.status = "completed"
                await db.commit()

        result_resp = await client.get(
            f"/api/v1/audit/result/project/{project_id}"
        )
    assert result_resp.status_code == 200, result_resp.text
    data = result_resp.json()
    assert data["audit"]["domain"] == "example.com"
    assert data["audit"]["url"] == "https://example.com/"
    # The unified response has the 4 top-level keys (audit, summary,
    # categories, issues).
    for key in ("audit", "summary", "categories", "issues"):
        assert key in data, f"missing top-level key {key!r}"
    # Score is a real number in the [0, 100] range
    assert 0 <= data["summary"]["score"] <= 100


@pytest.mark.asyncio
async def test_result_by_project_format_compact_returns_overview(
    mock_celery, _ensure_schema
):
    """With ?format=compact, the project-keyed result endpoint must
    return the new compact AuditOverview (no per-page evidence, no
    nested issues, no legacy audit sub-blocks)."""
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        posted = await client.post(
            "/api/v1/audit/analyze?format=compact",
            json={"url": "https://example.com/"},
        )
        crawl_id = uuid.UUID(posted.json()["crawl_id"])
        project_id = uuid.UUID(posted.json()["project_id"])

        async with session_factory() as db:
            await _seed_crawl(db, crawl_id, project_id, n_pages=2)
        await _run_pipeline(crawl_id, project_id, session_factory)

        async with session_factory() as db:
            job = await db.get(CrawlJob, crawl_id)
            if job:
                job.status = "completed"
                await db.commit()

        result_resp = await client.get(
            f"/api/v1/audit/result/project/{project_id}?format=compact"
        )
    assert result_resp.status_code == 200, result_resp.text
    data = result_resp.json()
    # Compact shape: 4 top-level keys (audit, summary, categories, top_issues)
    for key in ("audit", "summary", "categories", "top_issues"):
        assert key in data, f"missing compact top-level key {key!r}"
    # Compact shape must NOT include the legacy heavy keys
    for forbidden in ("issues", "crawl_stats", "indexation", "performance",
                      "structured_data", "links", "images", "content",
                      "external_dependencies", "meta"):
        assert forbidden not in data["audit"], forbidden


@pytest.mark.asyncio
async def test_result_by_project_202_when_compact_but_no_run(
    mock_celery, _ensure_schema
):
    """When the project has no SeoAnalysisRun yet, the compact branch must
    also return 202 (not 404, not 500). Keeps the contract consistent
    with the full-path 202 behaviour."""
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Use a project_id that has no run at all
        result_resp = await client.get(
            f"/api/v1/audit/result/project/{uuid.uuid4()}?format=compact"
        )
    assert result_resp.status_code == 202


# =====================================================================
# 4. Full lifecycle: POST -> status -> result (the "no worker" case)
# =====================================================================


@pytest.mark.asyncio
async def test_full_lifecycle_no_worker_does_not_break_clients(
    mock_celery, _ensure_schema
):
    """End-to-end: with the Celery worker NOT running, the three endpoints
    must cooperate so the client can observe progress and eventually
    trigger completion externally.

    This is the exact scenario the user asked about: a task is queued,
    no worker is activated. The client should still be able to:
      1. POST and receive 202 with the polling URLs.
      2. GET /audit/status and see a coherent "not ready" report.
      3. GET /audit/result and see 202.
    """
    session_factory = _ensure_schema
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Step 1: queue the audit
        posted = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://example.com/"},
        )
        assert posted.status_code == 202
        posted_data = posted.json()
        crawl_id = uuid.UUID(posted_data["crawl_id"])
        project_id = uuid.UUID(posted_data["project_id"])
        task_id = posted_data["task_id"]

        # Step 2: poll status (no worker has run, so all 'pending' / 'missing')
        status_resp = await client.get(f"/api/v1/audit/status/{project_id}")
        assert status_resp.status_code == 200
        status = status_resp.json()
        # No data → parse_status is 'missing', score_status is 'missing'
        assert status["parse_status"] in {"missing", "pending"}
        assert status["evaluate_status"] in {"missing", "pending"}
        assert status["score_status"] == "missing"

        # Step 3: poll result (no run yet → 202)
        result_resp = await client.get(
            f"/api/v1/audit/result/project/{project_id}"
        )
        assert result_resp.status_code == 202

        # Step 4: poll the task itself (fake AsyncResult returns PENDING)
        task_resp = await client.get(f"/api/v1/audit/analyze/task/{task_id}")
        assert task_resp.status_code == 200
        task = task_resp.json()
        assert task["task_id"] == task_id
        assert task["state"] == "PENDING"

        # Step 5: simulate the worker completing the pipeline manually
        # (this is what an external worker would do — the endpoint
        # contract doesn't change whether the worker is internal or external).
        async with session_factory() as db:
            await _seed_crawl(db, crawl_id, project_id, n_pages=2)
        await _run_pipeline(crawl_id, project_id, session_factory)
        async with session_factory() as db:
            job = await db.get(CrawlJob, crawl_id)
            if job:
                job.status = "completed"
                await db.commit()

        # Step 6: status now reflects completion
        status_resp = await client.get(f"/api/v1/audit/status/{project_id}")
        assert status_resp.status_code == 200
        status = status_resp.json()
        assert status["parse_status"] == "completed"
        assert status["evaluate_status"] == "completed"
        assert status["score_status"] == "completed"

        # Step 7: result now returns 200
        result_resp = await client.get(
            f"/api/v1/audit/result/project/{project_id}"
        )
        assert result_resp.status_code == 200
        data = result_resp.json()
        assert data["audit"]["domain"] == "example.com"
