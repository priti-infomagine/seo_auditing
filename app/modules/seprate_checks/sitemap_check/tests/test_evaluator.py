"""
Tests for the sitemap check evaluator.
"""

from app.modules.seprate_checks.sitemap_check.evaluator import evaluate
from app.modules.seprate_checks.sitemap_check.model import (
    FetchStatus,
    OverallStatus,
    Severity,
)


def _make_result(
    url="https://example.com/sitemap.xml",
    final_url=None,
    status_code=200,
    content_type="application/xml",
    entry_count=10,
    is_index=False,
    error=None,
):
    return {
        "url": url,
        "final_url": final_url or url,
        "status_code": status_code,
        "content_type": content_type,
        "entry_count": entry_count,
        "is_index": is_index,
        "redirected": final_url is not None and final_url != url,
        "error": error,
    }


def test_evaluate_no_sitemaps_found():
    """No sitemap results → sitemap_none_found finding."""
    result = evaluate(FetchStatus.NOT_FOUND, [], [])

    codes = [f["code"] for f in result.findings]
    assert "sitemap_none_found" in codes
    assert result.overall_status == OverallStatus.WARNING.value
    assert result.severity == Severity.MEDIUM.value


def test_evaluate_sitemap_unreachable():
    """Sitemap with error → sitemap_unreachable finding."""
    results = [_make_result(status_code=0, error="Connection refused")]
    result = evaluate(FetchStatus.SUCCESS, ["https://example.com/sitemap.xml"], results)

    codes = [f["code"] for f in result.findings]
    assert "sitemap_unreachable" in codes
    unreachable = [f for f in result.findings if f["code"] == "sitemap_unreachable"][0]
    assert unreachable["severity"] == Severity.MEDIUM.value


def test_evaluate_redirect_detected():
    """Sitemap where final_url differs from url → redirect finding."""
    results = [_make_result(
        url="https://example.com/sitemap.xml",
        final_url="https://cdn.example.com/sitemap.xml",
    )]
    result = evaluate(FetchStatus.SUCCESS, [], results)

    codes = [f["code"] for f in result.findings]
    assert "sitemap_redirect_detected" in codes
    redirect_finding = [f for f in result.findings if f["code"] == "sitemap_redirect_detected"][0]
    assert redirect_finding["severity"] == Severity.LOW.value


def test_evaluate_index_empty():
    """Sitemap index with 0 entries → sitemap_index_empty finding."""
    results = [_make_result(is_index=True, entry_count=0)]
    result = evaluate(FetchStatus.SUCCESS, [], results)

    codes = [f["code"] for f in result.findings]
    assert "sitemap_index_empty" in codes


def test_evaluate_wrong_content_type():
    """Sitemap served with wrong content-type → warning."""
    results = [_make_result(
        status_code=200,
        content_type="text/html",
        entry_count=5,
    )]
    result = evaluate(FetchStatus.SUCCESS, [], results)

    codes = [f["code"] for f in result.findings]
    assert "sitemap_wrong_content_type" in codes


def test_evaluate_all_ok():
    """All sitemaps reachable, no redirects → sitemap_ok, PASS."""
    results = [_make_result(status_code=200, content_type="application/xml", entry_count=42)]
    result = evaluate(FetchStatus.SUCCESS, ["https://example.com/sitemap.xml"], results)

    # The only finding should be sitemap_ok
    assert len(result.findings) == 1
    assert result.findings[0]["code"] == "sitemap_ok"
    assert result.overall_status == OverallStatus.PASS.value
    assert result.severity == Severity.NONE.value


def test_evaluate_severity_aggregation():
    """Highest severity finding determines overall severity."""
    findings = [
        {"code": "sitemap_redirect_detected", "severity": "low", "status": "warning", "message": "test", "evidence": ""},
        {"code": "sitemap_unreachable", "severity": "medium", "status": "warning", "message": "test", "evidence": ""},
    ]
    from app.modules.seprate_checks.sitemap_check.evaluator import _finalize
    eval_result = _finalize(findings, OverallStatus.FAIL.value, Severity.HIGH.value, "test")
    assert eval_result.severity == Severity.HIGH.value
    assert eval_result.overall_status == OverallStatus.FAIL.value
