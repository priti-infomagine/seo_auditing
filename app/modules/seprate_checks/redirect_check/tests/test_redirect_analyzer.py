"""Tests for RedirectCheckAnalyzer — classification and findings."""


from app.modules.seprate_checks.redirect_check.analyzer import RedirectCheckAnalyzer
from app.modules.seprate_checks.redirect_check.schema import (
    RedirectHop,
    RedirectUrlResult,
)


def _make_result(
    url: str,
    redirect_count: int = 0,
    final_url: str | None = None,
    final_status: int | None = 200,
    error: str | None = None,
    is_internal: bool = False,
    is_external: bool = False,
    meta_refresh: str | None = None,
    is_broken: bool = False,
) -> RedirectUrlResult:
    hops = []
    if redirect_count > 0:
        hops = [
            RedirectHop(url=url, status=301, status_text="Moved", location=final_url),
            RedirectHop(url=final_url or url, status=final_status, status_text="OK"),
        ]
    is_redirect = redirect_count > 0
    return RedirectUrlResult(
        url=url,
        hops=hops,
        redirects=redirect_count,
        final_url=final_url,
        final_status=final_status,
        error=error,
        redirect_count=redirect_count,
        chain=[],
        is_redirect=is_redirect,
        is_internal_redirect=is_internal,
        is_external_redirect=is_external,
        is_broken=is_broken,
        canonical=None,
        meta_refresh=meta_refresh,
        robots_allowed=True,
        in_sitemap=True,
        source_pages=[],
    )


def test_no_redirects_no_findings():
    results = [
        _make_result("https://example.com/page1", redirect_count=0, final_url="https://example.com/page1"),
        _make_result("https://example.com/page2", redirect_count=0, final_url="https://example.com/page2"),
    ]
    outcome = RedirectCheckAnalyzer.analyze(results, "example.com")

    assert len(outcome.findings) == 0
    assert outcome.overall_status == "pass"
    assert outcome.severity == "none"
    assert outcome.summary.total_urls == 2
    assert outcome.summary.redirects_found == 0


def test_internal_redirect_creates_finding():
    results = [
        _make_result(
            "https://example.com/old",
            redirect_count=1,
            final_url="https://example.com/new",
            final_status=200,
            is_internal=True,
        ),
    ]
    outcome = RedirectCheckAnalyzer.analyze(results, "example.com")

    finding_codes = [f.code for f in outcome.findings]
    assert "redirect_internal" in finding_codes
    assert outcome.summary.internal_redirects == 1
    assert outcome.summary.redirects_found == 1


def test_external_redirect_creates_finding():
    results = [
        _make_result(
            "https://example.com/old",
            redirect_count=1,
            final_url="https://other.com/new",
            final_status=200,
            is_external=True,
        ),
    ]
    outcome = RedirectCheckAnalyzer.analyze(results, "example.com")

    finding_codes = [f.code for f in outcome.findings]
    assert "redirect_external" in finding_codes
    assert outcome.summary.external_redirects == 1


def test_broken_link_creates_high_severity_finding():
    results = [
        _make_result("https://example.com/broken", redirect_count=1, final_url="https://example.com/dead", final_status=404),
    ]
    outcome = RedirectCheckAnalyzer.analyze(results, "example.com")

    finding_codes = [f.code for f in outcome.findings]
    assert "broken_link" in finding_codes
    assert outcome.summary.broken == 1
    assert outcome.overall_status == "fail"
    assert outcome.severity == "high"


def test_long_redirect_chain_creates_finding():
    results = [
        _make_result(
            "https://example.com/deep",
            redirect_count=3,
            final_url="https://example.com/destination",
            final_status=200,
            is_internal=True,
        ),
    ]
    outcome = RedirectCheckAnalyzer.analyze(results, "example.com")

    finding_codes = [f.code for f in outcome.findings]
    assert "redirect_chain_long" in finding_codes


def test_error_result_creates_broken_finding():
    results = [
        RedirectUrlResult(
            url="https://example.com/error",
            error="Connection failed.",
            final_status=None,
        ),
    ]
    outcome = RedirectCheckAnalyzer.analyze(results, "example.com")

    finding_codes = [f.code for f in outcome.findings]
    assert "broken_link" in finding_codes
    assert outcome.summary.broken == 1


def test_meta_refresh_creates_finding():
    results = [
        _make_result(
            "https://example.com/refresh",
            redirect_count=1,
            final_url="https://example.com/new",
            final_status=200,
            is_internal=True,
            meta_refresh="5;url=https://example.com/newest",
        ),
    ]
    outcome = RedirectCheckAnalyzer.analyze(results, "example.com")

    finding_codes = [f.code for f in outcome.findings]
    assert "meta_refresh_redirect" in finding_codes
    assert outcome.summary.meta_refresh == 1


def test_summary_counts_are_correct():
    results = [
        _make_result("https://example.com/ok", redirect_count=0, final_url="https://example.com/ok", final_status=200),
        _make_result("https://example.com/redirect", redirect_count=1, final_url="https://example.com/new", final_status=200, is_internal=True),
        _make_result("https://example.com/broken", redirect_count=0, final_url="https://example.com/dead", final_status=500),
        _make_result("https://example.com/error", error="timeout", final_status=0, is_broken=True),
    ]
    outcome = RedirectCheckAnalyzer.analyze(results, "example.com")

    assert outcome.summary.total_urls == 4
    assert outcome.summary.redirects_found == 1
    assert outcome.summary.broken == 2
    assert outcome.summary.internal_redirects == 1


def test_insecure_redirect_detected():
    results = [
        _make_result(
            "https://example.com/old",
            redirect_count=1,
            final_url="http://example.com/new",
            final_status=200,
            is_internal=True,
        ),
    ]
    outcome = RedirectCheckAnalyzer.analyze(results, "example.com")

    finding_codes = [f.code for f in outcome.findings]
    assert "insecure_redirect" in finding_codes
