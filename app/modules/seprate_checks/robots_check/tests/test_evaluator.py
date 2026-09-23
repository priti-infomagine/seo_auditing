"""
Tests for the robots.txt evaluator.
"""
import pytest

from app.modules.seprate_checks.robots_check.evaluator import evaluate
from app.modules.seprate_checks.robots_check.fetcher import (
    FetchResult,
    FetchStatus,
    ParsedRobots,
)
from app.modules.seprate_checks.robots_check.model import OverallStatus, Severity


def _make_fetch_result(
    text: str,
    fetch_status: FetchStatus = FetchStatus.SUCCESS,
    content_length: int | None = None,
) -> FetchResult:
    return FetchResult(
        url=f"https://example.com/robots.txt",
        text=text,
        status_code=200 if fetch_status == FetchStatus.SUCCESS else None,
        response_time_ms=100,
        final_url="https://example.com/robots.txt",
        content_length=content_length if content_length is not None else len(text),
        success=fetch_status == FetchStatus.SUCCESS,
        fetch_status=fetch_status,
    )


@pytest.mark.asyncio
async def test_evaluator_clean_pass():
    """Well-formed robots.txt → PASS, severity NONE."""
    raw = "User-agent: *\nDisallow: /private/\nSitemap: https://example.com/sitemap.xml"
    from app.modules.seprate_checks.robots_check.parser import parse_robots_txt
    parsed = parse_robots_txt(raw)
    fetch_result = _make_fetch_result(raw)

    eval_result = evaluate(parsed, fetch_result)

    assert eval_result.overall_status == OverallStatus.PASS.value
    assert eval_result.severity == Severity.NONE.value
    assert eval_result.blocks_entire_site is False
    assert eval_result.blocks_assets is False


@pytest.mark.asyncio
async def test_evaluator_site_block():
    """Disallow: / → CRITICAL, FAIL."""
    raw = "User-agent: *\nDisallow: /\nSitemap: https://example.com/sitemap.xml"
    from app.modules.seprate_checks.robots_check.parser import parse_robots_txt
    parsed = parse_robots_txt(raw)
    fetch_result = _make_fetch_result(raw)

    eval_result = evaluate(parsed, fetch_result)

    assert eval_result.blocks_entire_site is True
    assert eval_result.overall_status == OverallStatus.FAIL.value
    assert eval_result.severity == Severity.CRITICAL.value
    codes = [f["code"] for f in eval_result.findings]
    assert "robots_site_block" in codes


@pytest.mark.asyncio
async def test_evaluator_asset_block():
    """Disallow: /css/, /js/ → HIGH, FAIL."""
    raw = "User-agent: *\nDisallow: /css/\nDisallow: /js/\nSitemap: https://example.com/sitemap.xml"
    from app.modules.seprate_checks.robots_check.parser import parse_robots_txt
    parsed = parse_robots_txt(raw)
    fetch_result = _make_fetch_result(raw)

    eval_result = evaluate(parsed, fetch_result)

    assert eval_result.blocks_assets is True
    assert eval_result.overall_status == OverallStatus.FAIL.value
    assert eval_result.severity == Severity.HIGH.value
    codes = [f["code"] for f in eval_result.findings]
    assert "robots_asset_block" in codes


@pytest.mark.asyncio
async def test_evaluator_missing_sitemap_warning():
    """No Sitemap directive → LOW warning."""
    raw = "User-agent: *\nDisallow: /private/"
    from app.modules.seprate_checks.robots_check.parser import parse_robots_txt
    parsed = parse_robots_txt(raw)
    fetch_result = _make_fetch_result(raw)

    eval_result = evaluate(parsed, fetch_result)

    codes = [f["code"] for f in eval_result.findings]
    assert "robots_sitemap_declared" in codes
    sitemap_finding = [f for f in eval_result.findings if f["code"] == "robots_sitemap_declared"][0]
    assert sitemap_finding["severity"] == Severity.LOW.value


@pytest.mark.asyncio
async def test_evaluator_missing_robots_txt():
    """404 → not_found finding."""
    fetch_result = FetchResult(
        url="https://example.com/robots.txt",
        text="",
        status_code=404,
        response_time_ms=50,
        final_url="https://example.com/robots.txt",
        content_length=0,
        error=None,
        success=False,
        fetch_status=FetchStatus.NOT_FOUND,
    )

    eval_result = evaluate(None, fetch_result)

    codes = [f["code"] for f in eval_result.findings]
    assert "robots_missing" in codes
    missing_finding = [f for f in eval_result.findings if f["code"] == "robots_missing"][0]
    assert missing_finding["severity"] == Severity.MEDIUM.value


@pytest.mark.asyncio
async def test_evaluator_unreachable():
    """Connection error → unreachable finding, NOT_APPLICABLE status."""
    fetch_result = FetchResult(
        url="https://example.com/robots.txt",
        text="",
        status_code=0,
        response_time_ms=5000,
        final_url="https://example.com/robots.txt",
        content_length=0,
        error="connection_error: timeout",
        success=False,
        fetch_status=FetchStatus.UNREACHABLE,
    )

    eval_result = evaluate(None, fetch_result)

    codes = [f["code"] for f in eval_result.findings]
    assert "robots_unreachable" in codes
    assert eval_result.overall_status == OverallStatus.NOT_APPLICABLE.value


@pytest.mark.asyncio
async def test_evaluator_oversized():
    """Content > 500KB → oversized warning."""
    raw = "User-agent: *\nDisallow: /private/"
    from app.modules.seprate_checks.robots_check.parser import parse_robots_txt
    parsed = parse_robots_txt(raw)
    large_text = raw + "\n" + "x" * 600_000
    fetch_result = _make_fetch_result(large_text, content_length=len(large_text))

    eval_result = evaluate(parsed, fetch_result)

    assert eval_result.oversized is True
    codes = [f["code"] for f in eval_result.findings]
    assert "robots_oversized" in codes


@pytest.mark.asyncio
async def test_evaluator_sitemap_unreachable():
    """Declared sitemap that's unreachable → MEDIUM warning."""
    raw = "User-agent: *\nDisallow: /private/\nSitemap: https://example.com/sitemap.xml"
    from app.modules.seprate_checks.robots_check.parser import parse_robots_txt
    parsed = parse_robots_txt(raw)
    fetch_result = _make_fetch_result(raw)
    sitemap_reachability = [
        {"url": "https://example.com/sitemap.xml", "status_code": 0, "reachable": False, "error": "Connection error"}
    ]

    eval_result = evaluate(parsed, fetch_result, sitemap_reachability)

    codes = [f["code"] for f in eval_result.findings]
    assert "robots_sitemap_reachable" in codes
    sitemap_finding = [f for f in eval_result.findings if f["code"] == "robots_sitemap_reachable"][0]
    assert sitemap_finding["severity"] == Severity.MEDIUM.value


@pytest.mark.asyncio
async def test_evaluator_syntax_warnings():
    """Syntax warnings → LOW warning."""
    from app.modules.seprate_checks.robots_check.parser import parse_robots_txt
    raw = "User-agent: *\nDisallow:\nSitemap: https://example.com/sitemap.xml"
    parsed = parse_robots_txt(raw)
    fetch_result = _make_fetch_result(raw)

    eval_result = evaluate(parsed, fetch_result)

    codes = [f["code"] for f in eval_result.findings]
    assert "robots_syntax" in codes
    syntax_finding = [f for f in eval_result.findings if f["code"] == "robots_syntax"][0]
    assert syntax_finding["severity"] == Severity.LOW.value


def test_severity_aggregation():
    """Highest severity finding wins."""
    findings = [
        {"code": "robots_sitemap_declared", "severity": "low", "status": "warning", "message": "test", "evidence": ""},
        {"code": "robots_site_block", "severity": "critical", "status": "fail", "message": "test", "evidence": ""},
    ]
    from app.modules.seprate_checks.robots_check.evaluator import _finalize
    eval_result = _finalize(
        findings, OverallStatus.FAIL.value, Severity.CRITICAL.value,
        True, False, False, "test evidence",
    )
    assert eval_result.severity == Severity.CRITICAL.value
    assert eval_result.overall_status == OverallStatus.FAIL.value
