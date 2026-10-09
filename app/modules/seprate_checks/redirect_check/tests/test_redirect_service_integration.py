"""Tests for RedirectCheckService._analyzed_to_result and _browser_result_to_raw."""
from __future__ import annotations

from protego import Protego

from app.modules.crawler.services.site_discovery_service import (
    RobotsTxtEvidence,
    SiteDiscoveryResult,
)
from app.modules.seprate_checks.bulk_status.schema import (
    RedirectHop as BulkRedirectHop,
    RedirectResult,
)
from app.modules.seprate_checks.redirect_check.redirect_report import analyze_result
from app.modules.seprate_checks.redirect_check.resolver import ResolveContext
from app.modules.seprate_checks.redirect_check.service import RedirectCheckService

EXPECTED_FIELDS = {
    "url", "state", "redirect_count", "redirect_type", "final_url", "final_status",
    "error", "error_type", "client_redirect", "hops",
    "canonical", "robots_allowed", "in_sitemap", "source_pages",
}


def _site() -> SiteDiscoveryResult:
    return SiteDiscoveryResult(
        robots=RobotsTxtEvidence(
            url="https://example.com/robots.txt", exists=True,
            content="User-agent: *\nDisallow: /admin/\n"),
    )


def _ctx(**kw) -> ResolveContext:
    return ResolveContext(site_discovery=_site(), domain="example.com", **kw)


def _hop(url, status, loc=None, **extra):
    return {"url": url, "status": status, "location": loc, "latency_ms": 10, **extra}


def _convert(raw, context=None):
    analyzed = analyze_result(raw)
    return RedirectCheckService._analyzed_to_result(raw["url"], analyzed, context or _ctx())


class TestAnalyzedToResult:
    def test_single_redirect(self):
        r = _convert({"url": "https://example.com/old", "hops": [
            _hop("https://example.com/old", 301, "/new"), _hop("https://example.com/new", 200)]})
        assert r.state == "redirected" and r.redirect_count == 1
        assert r.redirect_type == "internal"
        assert r.final_url == "https://example.com/new" and r.final_status == 200
        assert [h.kind for h in r.hops] == ["http", None]
        assert r.hops[0].location == "https://example.com/new"

    def test_normal_page_has_zero_redirects_and_one_hop(self):
        """Regression: the final 200 hop must NOT be counted as a redirect."""
        r = _convert({"url": "https://example.com/page", "hops": [_hop("https://example.com/page", 200)]})
        assert r.state == "ok" and r.redirect_count == 0 and r.redirect_type == "none"
        assert len(r.hops) == 1
        assert r.final_url == "https://example.com/page" and r.final_status == 200

    def test_external_temporary_redirect(self):
        r = _convert({"url": "https://example.com/r", "hops": [
            _hop("https://example.com/r", 302, "https://other.com/x"), _hop("https://other.com/x", 200)]})
        assert r.redirect_type == "external" and r.redirect_count == 1

    def test_broken_unreachable_loop_and_too_many(self):
        gone = _convert({"url": "https://example.com/gone", "hops": [_hop("https://example.com/gone", 404)]})
        assert gone.state == "broken" and gone.final_status == 404

        dead = _convert({"url": "https://example.com/x", "hops": [], "error": "boom",
                         "error_type": "timeout"})
        assert dead.state == "unreachable" and dead.final_url is None and dead.error_type == "timeout"

        loop = _convert({"url": "https://example.com/a", "hops": [
            _hop("https://example.com/a", 301, "/b"), _hop("https://example.com/b", 301, "/a")]})
        assert loop.state == "loop"

        many = _convert({"url": "https://example.com/r0", "hops": [
            _hop(f"https://example.com/r{i}", 301, f"/r{i + 1}") for i in range(5)]})
        assert many.state == "too_many_redirects"

    def test_seo_enrichment(self):
        ctx = _ctx(
            sitemap_url_set={"https://example.com/old-path"},
            url_to_seo={"https://example.com/old-path": {"canonical": "https://example.com/new-path"}},
            url_to_sources={"https://example.com/old-path": ["https://example.com/"]},
            robot_parser=Protego.parse("User-agent: *\nDisallow: /admin/\n"),
        )
        r = _convert({"url": "https://example.com/old-path",
                      "hops": [_hop("https://example.com/old-path", 200)]}, ctx)
        assert r.canonical == "https://example.com/new-path"
        assert r.in_sitemap is True and r.source_pages == ["https://example.com/"]
        assert r.robots_allowed is True
        blocked = _convert({"url": "https://example.com/admin/x",
                            "hops": [_hop("https://example.com/admin/x", 200)]}, ctx)
        assert blocked.robots_allowed is False

    def test_client_signal_without_browser_is_suspected_only(self):
        r = _convert({"url": "https://example.com/stub", "hops": [
            _hop("https://example.com/stub", 200, client_signal="meta_refresh",
                 client_target="https://example.com/new")]})
        assert r.client_redirect == "suspected" and r.redirect_count == 0

    def test_payload_has_no_extra_fields(self):
        r = _convert({"url": "https://example.com/p", "hops": [_hop("https://example.com/p", 200)]})
        dumped = r.model_dump()
        assert set(dumped) == EXPECTED_FIELDS
        assert set(dumped["hops"][0]) == {"url", "status", "location", "kind", "latency_ms"}


class TestBrowserResultToRaw:
    def _result(self, hops, final_url=None, final_status=None, error=None, redirects=0):
        return RedirectResult(input=hops[0].url if hops else "https://example.com/",
                              hops=hops, redirects=redirects, finalUrl=final_url,
                              finalStatus=final_status, error=error)

    def test_http_redirect_chain(self):
        result = self._result([
            BulkRedirectHop(url="https://example.com/old", status=301, statusText="Moved",
                            location="/new", resolved="https://example.com/new", latencyMs=50, headers=[]),
            BulkRedirectHop(url="https://example.com/new", status=200, statusText="OK", headers=[]),
        ], "https://example.com/new", 200, redirects=1)
        raw = RedirectCheckService._browser_result_to_raw("https://example.com/old", result)
        assert raw["browser_checked"] is True and raw["error"] is None
        assert raw["hops"][0] == {"url": "https://example.com/old", "status": 301,
                                  "location": "https://example.com/new", "latency_ms": 50}
        assert all("headers" not in h and "statusText" not in h for h in raw["hops"])
        a = analyze_result(raw)
        assert a["state"] == "redirected" and a["redirect_count"] == 1
        assert a["final_url"] == "https://example.com/new"

    def test_js_redirect_final_url_is_appended_as_last_hop(self):
        result = self._result([BulkRedirectHop(url="https://infomagine.com/", status=200, headers=[])],
                              "https://infomagine.in/", 200)
        raw = RedirectCheckService._browser_result_to_raw("https://infomagine.com/", result)
        assert [h["url"] for h in raw["hops"]] == ["https://infomagine.com/", "https://infomagine.in/"]
        raw["client_signal"] = "js"
        a = analyze_result(raw)
        assert a["client_redirect"] == "confirmed" and a["redirect_count"] == 1
        assert a["redirect_type"] == "external" and a["final_url"] == "https://infomagine.in/"

    def test_browser_saw_no_navigation_clears_the_suspicion(self):
        result = self._result([BulkRedirectHop(url="https://example.com/p", status=200, headers=[])],
                              "https://example.com/p", 200)
        raw = RedirectCheckService._browser_result_to_raw("https://example.com/p", result)
        raw["client_signal"] = "js"
        a = analyze_result(raw)
        assert a["client_redirect"] is None and a["redirect_count"] == 0 and a["state"] == "ok"

    def test_browser_error_is_reported_as_browser_error(self):
        result = self._result([], error="net::ERR_CONNECTION_REFUSED")
        raw = RedirectCheckService._browser_result_to_raw("https://example.com/p", result)
        assert raw["error"] and raw["error_type"] == "browser_error"
