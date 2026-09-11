"""
Tests for PDF report generation and email dispatch API.
"""
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.reports.services.pdf_generator import render_audit_report_pdf
from app.modules.reports.services.report_data_service import build_audit_report, _per_check_score
from app.modules.scorer.report_assembler import build_report_response
from app.schemas.report_schemas import CheckResult
from app.shared.services.email_service import send_email_sync


def test_build_report_response_and_pdf_rendering(tmp_path):
    """Test building AuditReportResponse and rendering PDF via ReportLab."""
    checks = [
        CheckResult(
            check_id="on_page_001",
            category="on_page",
            weight=1.0,
            applicable=True,
            passed=False,
            severity="critical",
            score_impact=-15.0,
            page_url="https://example.com/page1",
            title="Missing Title Tag",
            description="Page 1 is missing a <title> tag.",
            recommendation="Add a title tag.",
            found_value={"title": ""},
            expected_value="30-60 chars",
            evidence={"title_len": 0},
        ),
        CheckResult(
            check_id="technical_001",
            category="technical",
            weight=1.0,
            applicable=True,
            passed=True,
            severity="passed",
            score_impact=0.0,
            page_url="https://example.com/page1",
            title="SSL Certificate",
            description="HTTPS is active.",
        ),
    ]

    report = build_report_response(
        scan_id=str(uuid4()),
        url="https://example.com",
        site_category="ecommerce",
        scanned_at="2026-09-11T12:00:00Z",
        pages_crawled=2,
        check_results=checks,
    )

    assert report.url == "https://example.com"
    assert report.overall_score is not None
    assert len(report.categories) > 0

    target_pdf = tmp_path / "test_report.pdf"
    rendered_path = render_audit_report_pdf(report, str(target_pdf))

    assert Path(rendered_path).exists()
    assert Path(rendered_path).stat().st_size > 1000


def test_send_email_sync_with_attachments_signature():
    """Test send_email_sync attachment handling when SMTP settings are missing or mocked."""
    fake_pdf = b"%PDF-1.4 test content"
    with pytest.raises(RuntimeError, match="SMTP server configuration missing"):
        send_email_sync(
            to_email="test@example.com",
            subject="Test PDF",
            content="Hello",
            attachments=[("test.pdf", fake_pdf)],
        )


@pytest.mark.asyncio
async def test_send_report_api_unknown_audit_404():
    """POST /api/v1/reports/{unknown_id}/send should return 404."""
    unknown_id = uuid4()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
         resp = await client.post(f"/api/v1/reports/{unknown_id}/send")
    assert resp.status_code == 404


def test_per_check_score_derives_from_passed_and_impact():
    """_per_check_score mirrors check_result_adapter: passed=100, failed=100+impact (clamped)."""
    # Passed checks get a perfect score regardless of impact.
    assert _per_check_score(True, 0.0) == 100.0
    assert _per_check_score(True, -10.0) == 100.0
    assert _per_check_score(True, 5.0) == 100.0

    # Failed checks are penalized: 100 + score_impact (clamped to [0, 100]).
    assert _per_check_score(False, -15.0) == 85.0
    assert _per_check_score(False, -5.0) == 95.0
    assert _per_check_score(False, 0.0) == 100.0

    # Clamped to 0 when penalty exceeds 100.
    assert _per_check_score(False, -200.0) == 0.0

    # Handles None / falsy impact gracefully.
    assert _per_check_score(False, None) == 100.0
