"""
Tests for SEO audit report generation, covering BOTH execution paths:

1. **Without Celery** (synchronous / linear):
   Build an ``AuditReportResponse`` via ``build_report_response`` and render it
   straight to a PDF with ``render_audit_report_pdf`` — no task queue involved.

2. **With Celery** (async task dispatch):
   Run the real ``reports.send_audit_report_email_task`` Celery task in
   *eager* mode (``task_always_eager=True``) so it executes the full
   build → render → attach flow in-process, with ONLY the DB adapter
   (``build_audit_report``) and the email transport (``send_email_sync``)
   mocked. No broker/Redis/worker is required.

Both flavours write the generated PDF (plus a JSON rendering of the report data
for inspection) into ``output/report/{domain}/`` at the backend project root,
using the URL's *domain name* as the sub-folder.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import pytest

# Allow running this file directly (`python test_report_generation.py`) from
# anywhere: add the backend project root (parents[3] = backend/app/tests/reports
# -> backend) to sys.path so the absolute `app.*` imports resolve.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.config import settings
from app.modules.reports.services.pdf_generator import render_audit_report_pdf
from app.modules.reports.tasks import send_audit_report_email_task
from app.modules.scorer.report_assembler import build_report_response
from app.schemas.report_schemas import CheckResult
from app.shared.tasks.celery_app import celery_app

# backend / app / tests / reports -> backend root is parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = PROJECT_ROOT / "output" / "report"


# --------------------------------------------------------------------------- helpers


def _domain_of(url: str) -> str:
    """Extract a filesystem-safe domain name (netloc) from a URL."""
    return urlparse(url).netloc or url


def _build_demo_report(url: str = "https://example.com") -> "AuditReportResponse":
    """Build a realistic report object without touching the DB."""
    checks = [
        CheckResult(
            check_id="on_page_001",
            category="on_page",
            weight=1.0,
            applicable=True,
            passed=False,
            severity="critical",
            score_impact=-15.0,
            page_url=f"{url}/page1",
            title="Missing Title Tag",
            description="Page 1 is missing a <title> tag.",
            recommendation="Add a descriptive <title> tag (30-60 characters).",
            found_value={"title": ""},
            expected_value="30-60 chars",
            evidence={"title_len": 0},
        ),
        CheckResult(
            check_id="on_page_002",
            category="on_page",
            weight=1.0,
            applicable=True,
            passed=True,
            severity="passed",
            score_impact=0.0,
            page_url=f"{url}/page1",
            title="Meta Description",
            description="Meta description length is optimal (155 characters).",
        ),
    ]
    return build_report_response(
        scan_id="scan_report_gen_001",
        url=url,
        site_category="ecommerce",
        scanned_at="2026-09-14T12:00:00Z",
        pages_crawled=2,
        check_results=checks,
    )


def _domain_output_dir(url: str) -> Path:
    """The output/report/{domain} folder for a given report URL."""
    return OUTPUT_ROOT / _domain_of(url)


def _write_report_json(report, domain_dir: Path) -> Path:
    """Persist a JSON rendering of the report alongside the PDF for inspection."""
    domain_dir.mkdir(parents=True, exist_ok=True)
    json_path = domain_dir / f"{_domain_of(report.url)}_{report.scan_id}.json"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return json_path


# ------------------------------------------------------------------- without celery


def test_report_generation_without_celery():
    """
    Synchronous (non-celery) path: build the report object and render a PDF
    directly, storing it under output/report/{domain}/.
    """
    url = "https://example.com"
    domain_dir = _domain_output_dir(url)

    report = _build_demo_report(url)
    assert report.url == url
    assert report.overall_score is not None
    assert len(report.categories) > 0

    _write_report_json(report, domain_dir)
    pdf_path = domain_dir / f"{_domain_of(url)}_{report.scan_id}.pdf"
    rendered = render_audit_report_pdf(report, str(pdf_path))

    # Output must live under output/report/{domain}/.
    rendered_path = Path(rendered)
    assert rendered_path.resolve().is_relative_to(domain_dir.resolve()), (
        f"PDF written outside {domain_dir}: {rendered_path}"
    )
    assert rendered_path.exists()
    assert rendered_path.stat().st_size > 1000
    # It is a real PDF (magic header).
    assert rendered_path.read_bytes()[:5] == b"%PDF-"

    # JSON companion was stored in the same domain folder.
    assert (domain_dir / f"{_domain_of(url)}_{report.scan_id}.json").exists()


def test_report_generation_without_celery_domain_folder_named_after_domain():
    """The sub-folder must be the domain name (netloc) of the report URL."""
    url = "https://www.my-test-domain.io/deep/page"
    domain_dir = OUTPUT_ROOT / "www.my-test-domain.io"
    pdf_path = domain_dir / "sample.pdf"

    report = _build_demo_report(url)
    render_audit_report_pdf(report, str(pdf_path))

    assert pdf_path.exists()


# ------------------------------------------------- download API (public, no celery)


def test_download_report_pdf_generates_stores_and_serves(monkeypatch, tmp_path):
    """GET /reports/{audit_id}/download builds the PDF, stores it under
    output/report/{domain}/, and serves it as a PDF download — synchronously,
    without any Celery involvement."""
    import asyncio
    from types import SimpleNamespace

    from app.modules.reports import router as reports_router
    from app.modules.crawler.repositories.crawl_job_repository import (
        CrawlJobRepository,
    )

    url = "https://example.com"
    audit_id = UUID("00fe733b-7f90-4341-9a78-6cdd87841a7f")

    monkeypatch.setattr(settings, "REPORT_OUTPUT_DIR", str(tmp_path))

    fake_job = SimpleNamespace(url=url)

    async def _fake_job(self, audit_id):
        return fake_job

    monkeypatch.setattr(
        CrawlJobRepository, "get_by_id_or_audit_id", _fake_job
    )

    build_calls = []

    async def _fake_build(db, audit_id):
        build_calls.append(audit_id)
        return _build_demo_report(url)

    monkeypatch.setattr(reports_router, "build_audit_report", _fake_build)

    # First call: report is built + rendered + stored under {tmp}/{domain}/{audit_id}.pdf
    resp = asyncio.run(
        reports_router.download_audit_report(audit_id, db=None)
    )
    stored = tmp_path / "example.com" / f"{audit_id}.pdf"
    assert stored.exists(), f"PDF not stored at {stored}"
    assert stored.stat().st_size > 1000
    assert stored.read_bytes()[:5] == b"%PDF-"
    # Response streams that stored file with a proper download name.
    assert resp.path == str(stored)
    assert resp.media_type == "application/pdf"
    assert "example.com_seo_audit_report.pdf" in resp.headers["content-disposition"]
    assert len(build_calls) == 1

    # Second call: reuses the already-stored PDF (no re-render).
    resp2 = asyncio.run(
        reports_router.download_audit_report(audit_id, db=None)
    )
    assert resp2.path == str(stored)
    assert len(build_calls) == 1, "stored PDF should be reused, not rebuilt"


def test_download_report_pdf_404_when_audit_not_found(monkeypatch, tmp_path):
    """A missing audit returns HTTP 404, not a stored-file error."""
    import asyncio

    from fastapi import HTTPException

    from app.modules.reports import router as reports_router
    from app.modules.crawler.repositories.crawl_job_repository import (
        CrawlJobRepository,
    )

    monkeypatch.setattr(settings, "REPORT_OUTPUT_DIR", str(tmp_path))

    async def _fake_none(self, audit_id):
        return None

    monkeypatch.setattr(
        CrawlJobRepository, "get_by_id_or_audit_id", _fake_none
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            reports_router.download_audit_report(
                UUID("11111111-1111-1111-1111-111111111111"), db=None
            )
        )
    assert exc_info.value.status_code == 404


# ------------------------------------------------------------------------ with celery


@pytest.fixture
def eager_celery(monkeypatch):
    """Run Celery tasks in-process (eager) so no broker/worker is needed."""
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False, task_eager_propagates=False)


def test_report_generation_with_celery(eager_celery, monkeypatch):
    """
    Celery path: dispatch the real reports.send_audit_report_email_task in eager
    mode. The task builds the report (DB adapter mocked), generates a PDF into
    output/report/{domain}/, and hands the bytes to the email transport (mocked).
    """
    url = "https://example.com"
    audit_id = "00fe733b-7f90-4341-9a78-6cdd87841a7f"
    to_email = "test@example.com"
    domain_dir = _domain_output_dir(url)

    # Point the task's configured output dir at the parent of the domain folder
    # so the task creates {OUTPUT_ROOT}/{domain}/{audit_id}.pdf
    monkeypatch.setattr(settings, "REPORT_OUTPUT_DIR", str(OUTPUT_ROOT))

    # Mock ONLY the DB adapter and the email transport — everything else in the
    # real Celery task (path building, PDF rendering, attachment packaging) runs.
    import app.modules.reports.tasks as reports_tasks

    async def _fake_build(db, audit_id):
        return _build_demo_report(url)

    monkeypatch.setattr(reports_tasks, "build_audit_report", _fake_build)

    sent = []

    def _fake_send_email(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(reports_tasks, "send_email_sync", _fake_send_email)

    # Dispatch the task and let it execute eagerly/in-process.
    result = send_audit_report_email_task.delay(audit_id, to_email)
    assert result.successful() is True

    # It must have written a real PDF into output/report/{domain}/{audit_id}.pdf.
    pdfs = list(domain_dir.glob(f"*{audit_id}.pdf"))
    assert pdfs, f"no PDF written to {domain_dir}"
    pdf_path = pdfs[0]
    assert pdf_path.stat().st_size > 1000
    assert pdf_path.read_bytes()[:5] == b"%PDF-"

    # It must have attempted to email the PDF as an attachment.
    assert sent, "send_email_sync was never called"
    call = sent[0]
    assert call["to_email"] == to_email
    attachments = call.get("attachments") or []
    assert len(attachments) == 1
    filename, pdf_bytes = attachments[0]
    assert filename.endswith(".pdf")
    assert pdf_bytes[:5] == b"%PDF-"


# ----------------------------------------------------------- task wiring / registration


def test_report_task_registered_and_routed():
    """The reports task must be registered (as 'reports.send_audit_report_email')
    on the Celery app and routed to the 'email' queue."""
    task_name = send_audit_report_email_task.name
    assert task_name == "reports.send_audit_report_email"

    task = celery_app.tasks.get(task_name)
    assert task is not None, f"{task_name} not registered"

    from app.shared.tasks import celery_config

    routes = celery_config.task_routes
    assert "reports.*" in routes
    assert routes["reports.*"]["queue"] == "email"
    assert task.queue == "email"