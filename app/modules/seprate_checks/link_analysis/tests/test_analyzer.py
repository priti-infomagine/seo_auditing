"""Tests for the link analysis analyzer functions."""
import pytest

from app.modules.seprate_checks.link_analysis import analyzer
from app.modules.seprate_checks.link_analysis.analyzer import (
    FindingCandidate,
    SourceInfo,
    analyze,
    analyze_optimization,
    compute_overall_status,
    compute_summary,
)
from app.modules.seprate_checks.link_analysis.constants import GENERIC_ANCHORS
from app.modules.seprate_checks.link_analysis.graph import (
    CheckResult,
    LinkEdge,
    LinkGraph,
    PageNode,
    RedirectInfo,
)
from app.modules.seprate_checks.link_analysis.model import (
    FindingCategory,
    FindingType,
    LinkAnalysisCheck,
    LinkAnalysisOverallStatus,
    LinkAnalysisSeverity,
    LinkStatusClass,
)


def _make_graph(base_host="example.com"):
    return LinkGraph(base_host=base_host, base_scheme="https")


def _make_page(url, status_code=200, depth=0, final_url=None, **kw):
    return PageNode(
        url=url,
        final_url=final_url or url,
        status_code=status_code,
        content_type="text/html",
        depth=depth,
        **kw,
    )


def _make_edge(source, target, anchor_text="link text", rel=None, is_internal=True):
    return LinkEdge(
        source_url=source,
        target_url=target,
        anchor_text=anchor_text,
        rel=rel or [],
        is_internal=is_internal,
    )


# ---------------------------------------------------------------------------
# _find_broken_internal
# ---------------------------------------------------------------------------


class TestFindBrokenInternal:
    def test_finds_broken_internal_url(self):
        graph = _make_graph()
        page = _make_page("https://example.com/page", status_code=404)
        graph.add_page(page)
        edge = _make_edge("https://example.com/home", "https://example.com/page")
        graph.add_edge(edge)
        page.outgoing_edges.append(edge)

        checked_urls = {
            "https://example.com/page": CheckResult(
                status_class=LinkStatusClass.BROKEN,
                status_code=404,
            )
        }

        findings = analyzer._find_broken_internal(graph, checked_urls, set())
        assert len(findings) == 1
        f = findings[0]
        assert f.type == FindingType.BROKEN_INTERNAL
        assert f.severity == LinkAnalysisSeverity.HIGH
        assert f.target_url == "https://example.com/page"
        assert f.status_code == 404
        assert len(f.sources) == 1

    def test_no_broken_internal(self):
        graph = _make_graph()
        page = _make_page("https://example.com/page", status_code=200)
        graph.add_page(page)

        checked_urls = {
            "https://example.com/page": CheckResult(
                status_class=LinkStatusClass.OK,
                status_code=200,
            )
        }

        findings = analyzer._find_broken_internal(graph, checked_urls, set())
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# _find_broken_external
# ---------------------------------------------------------------------------


class TestFindBrokenExternal:
    def test_finds_broken_external_url(self):
        graph = _make_graph()
        checked_urls = {
            "https://external.com/broken": CheckResult(
                status_class=LinkStatusClass.BROKEN,
                status_code=404,
            )
        }

        findings = analyzer._find_broken_external(checked_urls, graph)
        assert len(findings) == 1
        f = findings[0]
        assert f.type == FindingType.BROKEN_EXTERNAL
        assert f.severity == LinkAnalysisSeverity.MEDIUM
        assert f.target_url == "https://external.com/broken"


# ---------------------------------------------------------------------------
# _find_redirects
# ---------------------------------------------------------------------------


class TestFindRedirects:
    def test_finds_internal_redirect(self):
        graph = _make_graph()
        chain = [RedirectInfo(url="https://example.com/old", status_code=301, location="/new")]
        checked_urls = {
            "https://example.com/old": CheckResult(
                status_class=LinkStatusClass.REDIRECT,
                status_code=301,
                final_url="https://example.com/new",
                redirect_chain=chain,
            )
        }

        findings = analyzer._find_redirects(graph, checked_urls, False)
        assert len(findings) == 1
        f = findings[0]
        assert f.type == FindingType.REDIRECT_INTERNAL
        assert f.severity == LinkAnalysisSeverity.LOW
        assert f.final_url == "https://example.com/new"

    def test_multi_hop_redirect_is_medium(self):
        graph = _make_graph()
        chain = [
            RedirectInfo(url="https://example.com/a", status_code=301, location="/b"),
            RedirectInfo(url="https://example.com/b", status_code=301, location="/c"),
        ]
        checked_urls = {
            "https://example.com/a": CheckResult(
                status_class=LinkStatusClass.REDIRECT,
                status_code=301,
                redirect_chain=chain,
            )
        }

        findings = analyzer._find_redirects(graph, checked_urls, False)
        assert findings[0].severity == LinkAnalysisSeverity.MEDIUM

    def test_no_redirects(self):
        graph = _make_graph()
        checked_urls = {}
        findings = analyzer._find_redirects(graph, checked_urls, False)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# _find_orphans
# ---------------------------------------------------------------------------


class TestFindOrphans:
    def test_sitemap_only_url_not_crawled(self):
        graph = _make_graph()
        sitemap_urls = {"https://example.com/orphan-page"}

        findings = analyzer._find_orphans(graph, sitemap_urls, False)
        assert len(findings) == 1
        f = findings[0]
        assert f.type == FindingType.ORPHAN
        assert f.severity == LinkAnalysisSeverity.MEDIUM
        assert f.target_url == "https://example.com/orphan-page"

    def test_crawled_page_with_no_inbound_links_is_orphan(self):
        graph = _make_graph()
        page = _make_page("https://example.com/no-inbound", status_code=200)
        graph.add_page(page)

        homepage = _home_page(graph)

        findings = analyzer._find_orphans(graph, set(), False)
        orphans = [f for f in findings if f.target_url == "https://example.com/no-inbound"]
        assert len(orphans) == 1
        assert orphans[0].type == FindingType.ORPHAN

    def test_homepage_not_orphan(self):
        graph = _make_graph()
        home_url = "https://example.com/"
        page = _make_page(home_url, status_code=200)
        graph.add_page(page)

        findings = analyzer._find_orphans(graph, set(), False)
        assert len(findings) == 0

    def test_crawl_truncated_lowers_severity(self):
        graph = _make_graph()
        sitemap_urls = {"https://example.com/orphan-page"}

        findings = analyzer._find_orphans(graph, sitemap_urls, True)
        assert findings[0].severity == LinkAnalysisSeverity.LOW


def _home_page(graph):
    """Create a homepage page in the graph."""
    home = _make_page("https://example.com/", status_code=200)
    graph.add_page(home)
    return home


# ---------------------------------------------------------------------------
# _find_sitemap_url_errors
# ---------------------------------------------------------------------------


class TestFindSitemapUrlErrors:
    def test_finds_broken_sitemap_url(self):
        checked_urls = {
            "https://example.com/sitemap-page": CheckResult(
                status_class=LinkStatusClass.BROKEN,
                status_code=404,
            )
        }
        sitemap_urls = {"https://example.com/sitemap-page"}

        findings = analyzer._find_sitemap_url_errors(sitemap_urls, checked_urls)
        assert len(findings) == 1
        f = findings[0]
        assert f.type == FindingType.SITEMAP_URL_ERROR
        assert f.target_url == "https://example.com/sitemap-page"
        assert f.status_code == 404


# ---------------------------------------------------------------------------
# _find_deep_pages
# ---------------------------------------------------------------------------


class TestFindDeepPages:
    def test_finds_deep_page(self):
        graph = _make_graph()
        page = _make_page("https://example.com/deep", status_code=200, depth=4)
        graph.add_page(page)

        findings = analyzer._find_deep_pages(graph)
        assert len(findings) == 1
        f = findings[0]
        assert f.type == FindingType.DEEP_PAGE
        assert f.category == FindingCategory.OPTIMIZATION
        assert f.extra["depth"] == 4

    def test_finds_deep_page_at_depth_5(self):
        graph = _make_graph()
        page = _make_page("https://example.com/deep5", status_code=200, depth=5)
        graph.add_page(page)

        findings = analyzer._find_deep_pages(graph)
        assert len(findings) == 1
        f = findings[0]
        assert f.type == FindingType.DEEP_PAGE
        assert f.category == FindingCategory.OPTIMIZATION
        assert f.extra["depth"] == 5

    def test_none_depth_page_not_flagged(self):
        graph = _make_graph()
        page = _make_page("https://example.com/orphan-seed", status_code=200, depth=None)
        graph.add_page(page)

        findings = analyzer._find_deep_pages(graph)
        assert len(findings) == 0

    def test_non_200_none_depth_page_not_flagged(self):
        graph = _make_graph()
        page = _make_page("https://example.com/broken-seed", status_code=404, depth=None)
        graph.add_page(page)

        findings = analyzer._find_deep_pages(graph)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# set_min_depth
# ---------------------------------------------------------------------------


class TestSetMinDepth:
    def test_sets_depth_from_none(self):
        graph = _make_graph()
        page = _make_page("https://example.com/orphan-seed", depth=None)
        graph.add_page(page)

        graph.set_min_depth("https://example.com/orphan-seed", 4)
        assert graph.pages["https://example.com/orphan-seed"].depth == 4

    def test_keeps_minimum_depth(self):
        graph = _make_graph()
        page = _make_page("https://example.com/page", depth=3)
        graph.add_page(page)

        graph.set_min_depth("https://example.com/page", 5)
        assert graph.pages["https://example.com/page"].depth == 3

    def test_never_resets_to_none(self):
        graph = _make_graph()
        page = _make_page("https://example.com/page", depth=3)
        graph.add_page(page)

        graph.set_min_depth("https://example.com/page", None)
        assert graph.pages["https://example.com/page"].depth == 3

    def test_unknown_url_is_noop(self):
        graph = _make_graph()
        graph.set_min_depth("https://example.com/nope", 4)
        assert len(graph.pages) == 0


# ---------------------------------------------------------------------------
# _find_dead_end_pages
# ---------------------------------------------------------------------------


class TestFindDeadEndPages:
    def test_finds_dead_end_page(self):
        graph = _make_graph()
        page = _make_page("https://example.com/dead-end", status_code=200)
        page.outgoing_edges = []  # no outgoing links
        graph.add_page(page)

        findings = analyzer._find_dead_end_pages(graph)
        assert len(findings) == 1
        assert findings[0].type == FindingType.DEAD_END_PAGE

    def test_no_dead_end_with_outgoing_links(self):
        graph = _make_graph()
        page = _make_page("https://example.com/page", status_code=200)
        page.outgoing_edges = [_make_edge("https://example.com/page", "https://example.com/other")]
        graph.add_page(page)

        findings = analyzer._find_dead_end_pages(graph)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# _find_weakly_linked_pages
# ---------------------------------------------------------------------------


class TestFindWeaklyLinkedPages:
    def test_finds_weakly_linked(self):
        graph = _make_graph()
        page = _make_page("https://example.com/weak", status_code=200)
        graph.add_page(page)
        graph.inbound_counts["https://example.com/weak"] = 1

        findings = analyzer._find_weakly_linked_pages(graph, False)
        assert len(findings) == 1
        assert findings[0].type == FindingType.WEAKLY_LINKED_PAGE

    def test_skipped_when_crawl_truncated(self):
        graph = _make_graph()
        page = _make_page("https://example.com/weak", status_code=200)
        graph.add_page(page)
        graph.inbound_counts["https://example.com/weak"] = 1

        findings = analyzer._find_weakly_linked_pages(graph, True)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# _find_anchor_issues
# ---------------------------------------------------------------------------


class TestFindAnchorIssues:
    def test_finds_empty_anchor(self):
        graph = _make_graph()
        edge = _make_edge("https://example.com/home", "https://example.com/page", anchor_text="")
        page = _make_page("https://example.com/home", status_code=200)
        page.outgoing_edges.append(edge)
        graph.add_page(page)
        graph.add_edge(edge)

        findings = analyzer._find_anchor_issues(graph)
        empty_findings = [f for f in findings if f.type == FindingType.EMPTY_ANCHOR]
        assert len(empty_findings) == 1

    def test_finds_generic_anchor(self):
        graph = _make_graph()
        edge = _make_edge("https://example.com/home", "https://example.com/page", anchor_text="click here")
        page = _make_page("https://example.com/home", status_code=200)
        page.outgoing_edges.append(edge)
        graph.add_page(page)
        graph.add_edge(edge)

        findings = analyzer._find_anchor_issues(graph)
        generic_findings = [f for f in findings if f.type == FindingType.GENERIC_ANCHOR]
        assert len(generic_findings) == 1


# ---------------------------------------------------------------------------
# _find_nofollow_internal
# ---------------------------------------------------------------------------


class TestFindNofollowInternal:
    def test_finds_nofollow_internal(self):
        graph = _make_graph()
        edge = _make_edge(
            "https://example.com/home",
            "https://example.com/page",
            rel=["nofollow"],
        )
        page = _make_page("https://example.com/home", status_code=200)
        page.outgoing_edges.append(edge)
        graph.add_page(page)
        graph.add_edge(edge)

        findings = analyzer._find_nofollow_internal(graph)
        assert len(findings) == 1
        assert findings[0].type == FindingType.NOFOLLOW_INTERNAL


# ---------------------------------------------------------------------------
# _find_insecure_links
# ---------------------------------------------------------------------------


class TestFindInsecureLinks:
    def test_finds_http_links_on_https_page(self):
        graph = _make_graph()
        edge = _make_edge("https://example.com/home", "http://example.com/insecure")
        page = _make_page("https://example.com/home", status_code=200)
        page.outgoing_edges.append(edge)
        graph.add_page(page)
        graph.add_edge(edge)

        findings = analyzer._find_insecure_links(graph)
        assert len(findings) == 1
        assert findings[0].type == FindingType.INSECURE_LINK

    def test_no_insecure_on_http_page(self):
        graph = _make_graph()
        edge = _make_edge("http://example.com/home", "http://example.com/insecure")
        page = _make_page("http://example.com/home", status_code=200)
        page.outgoing_edges.append(edge)
        graph.add_page(page)
        graph.add_edge(edge)

        findings = analyzer._find_insecure_links(graph)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# _find_excessive_outlinks
# ---------------------------------------------------------------------------


class TestFindExcessiveOutlinks:
    def test_finds_excessive_outlinks(self):
        graph = _make_graph()
        page = _make_page("https://example.com/page", status_code=200)
        for i in range(200):
            page.outgoing_edges.append(
                _make_edge("https://example.com/page", f"https://example.com/target{i}")
            )
        graph.add_page(page)

        findings = analyzer._find_excessive_outlinks(graph)
        assert len(findings) == 1
        assert findings[0].type == FindingType.EXCESSIVE_OUTLINKS
        assert findings[0].extra["outlink_count"] == 200


# ---------------------------------------------------------------------------
# analyze (standard findings)
# ---------------------------------------------------------------------------


class TestAnalyze:
    def test_analyze_returns_standard_findings_only(self):
        graph = _make_graph()
        page = _make_page("https://example.com/page", status_code=404)
        graph.add_page(page)
        edge = _make_edge("https://example.com/home", "https://example.com/page")
        page.outgoing_edges.append(edge)
        graph.add_edge(edge)

        from app.modules.seprate_checks.link_analysis.crawler import _classify_fetch_status as cfs

        checked_urls = {
            "https://example.com/page": CheckResult(
                status_class=LinkStatusClass.BROKEN,
                status_code=404,
            )
        }

        findings = analyze(graph, checked_urls, set(), False)
        types = [f.type for f in findings]
        assert FindingType.BROKEN_INTERNAL in types
        # Optimization findings should NOT be in standard analyze
        assert FindingType.DEEP_PAGE not in types

    def test_analyze_empty_graph(self):
        graph = _make_graph()
        findings = analyze(graph, {}, set(), False)
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# analyze_optimization
# ---------------------------------------------------------------------------


class TestAnalyzeOptimization:
    def test_returns_optimization_findings(self):
        graph = _make_graph()
        page = _make_page("https://example.com/page", status_code=200, depth=0)
        page.outgoing_edges = []
        graph.add_page(page)
        graph.inbound_counts["https://example.com/page"] = 1

        findings = analyze_optimization(graph, False)
        types = [f.type for f in findings]
        assert FindingType.DEAD_END_PAGE in types
        assert FindingType.WEAKLY_LINKED_PAGE in types


# ---------------------------------------------------------------------------
# compute_summary
# ---------------------------------------------------------------------------


class TestComputeSummary:
    def test_page_counts_include_mailto_and_tel_without_duplicate_final_urls(self):
        graph = _make_graph()
        page_url = "https://example.com/contact-us"
        page = _make_page(page_url)

        internal_targets = [f"https://example.com/page-{index}" for index in range(32)]
        for index in range(51):
            edge = _make_edge(page_url, internal_targets[index % len(internal_targets)])
            page.outgoing_edges.append(edge)
            graph.add_edge(edge)

        for index in range(7):
            page.outgoing_edges.append(_make_edge(
                page_url,
                f"https://external.example/link-{index}",
                is_internal=False,
            ))

        page.non_http_links.extend([
            _make_edge(page_url, "mailto:hello@example.com"),
            _make_edge(page_url, "tel:+1234567890"),
        ])
        graph.add_page(page)

        checked_urls = {
            internal_targets[0]: CheckResult(
                status_class=LinkStatusClass.OK,
                status_code=200,
                final_url=internal_targets[0],
            ),
            internal_targets[1]: CheckResult(
                status_class=LinkStatusClass.REDIRECT,
                status_code=301,
                final_url="https://example.com/page-1-destination",
            ),
        }
        summary = compute_summary(graph, checked_urls, [], set(), False)
        page_summary = summary["pages"][0]

        assert page_summary["total_links"] == 60
        assert page_summary["unique_links"] == 41
        assert page_summary["outbound_internal_links"] == 53
        assert page_summary["outbound_external_links"] == 7
        assert "final_url" not in page_summary["internal_links"][0]
        assert page_summary["internal_links"][1]["final_url"] == (
            "https://example.com/page-1-destination"
        )

    def test_summary_counts(self):
        graph = _make_graph()
        home = _make_page("https://example.com/", status_code=200)
        edge1 = _make_edge("https://example.com/", "https://example.com/page1")
        edge2 = _make_edge("https://example.com/", "https://external.com", is_internal=False)
        home.outgoing_edges.append(edge1)
        home.outgoing_edges.append(edge2)
        graph.add_page(home)
        graph.add_edge(edge1)
        graph.add_edge(edge2)

        checked_urls = {
            "https://example.com/page1": CheckResult(status_class=LinkStatusClass.OK, status_code=200),
            "https://external.com": CheckResult(status_class=LinkStatusClass.BROKEN, status_code=404),
        }

        summary = compute_summary(graph, checked_urls, [], set(), False)
        assert summary["broken_links"] == 1
        assert summary["unique_external_targets"] == 1
        assert summary["internal_link_occurrences"] == 1
        assert summary["external_link_occurrences"] == 1
        assert summary["broken_external_link_occurrences"] == 1
        assert summary["crawl_truncated"] is False
        page = summary["pages"][0]
        assert page["outbound_internal_links"] == 1
        assert page["outbound_external_links"] == 1
        assert page["internal_links"][0]["target_url"] == "https://example.com/page1"
        assert page["internal_links"][0]["status_class"] == "ok"
        assert page["external_links"][0]["target_url"] == "https://external.com"
        assert page["external_links"][0]["status_code"] == 404

    def test_external_edges_do_not_increase_internal_inbound_count(self):
        graph = _make_graph()
        page = _make_page("https://example.com/page")
        graph.add_page(page)
        external_edge = _make_edge(
            "https://external.com/",
            "https://example.com/page",
            is_internal=False,
        )

        graph.add_edge(external_edge)

        assert graph.inbound_counts.get("https://example.com/page", 0) == 0

    def test_database_enums_bind_lowercase_values(self):
        from sqlalchemy.dialects.postgresql import dialect

        bind_overall = LinkAnalysisCheck.__table__.c.overall_status.type.bind_processor(
            dialect()
        )
        bind_severity = LinkAnalysisCheck.__table__.c.severity.type.bind_processor(
            dialect()
        )

        assert bind_overall(LinkAnalysisOverallStatus.WARNING) == "warning"
        assert bind_severity(LinkAnalysisSeverity.MEDIUM) == "medium"


# ---------------------------------------------------------------------------
# compute_overall_status
# ---------------------------------------------------------------------------


class TestComputeOverallStatus:
    def test_no_findings_pass(self):
        status, severity = compute_overall_status([])
        assert status == "pass"
        assert severity == "none"

    def test_high_finding_fail(self):
        from app.modules.seprate_checks.link_analysis.analyzer import FindingCandidate

        findings = [
            FindingCandidate(
                category=FindingCategory.STANDARD,
                type=FindingType.BROKEN_INTERNAL,
                severity=LinkAnalysisSeverity.HIGH,
                target_url="https://example.com/broken",
                status_code=404,
                final_url=None,
                sources=[],
            )
        ]
        status, severity = compute_overall_status(findings)
        assert status == "fail"
        assert severity == "high"

    def test_medium_finding_warning(self):
        findings = [
            FindingCandidate(
                category=FindingCategory.STANDARD,
                type=FindingType.ORPHAN,
                severity=LinkAnalysisSeverity.MEDIUM,
                target_url="https://example.com/orphan",
                status_code=None,
                final_url=None,
                sources=[],
            )
        ]
        status, severity = compute_overall_status(findings)
        assert status == "warning"
        assert severity == "medium"

    def test_optimization_findings_do_not_affect_status(self):
        findings = [
            FindingCandidate(
                category=FindingCategory.OPTIMIZATION,
                type=FindingType.DEAD_END_PAGE,
                severity=LinkAnalysisSeverity.LOW,
                target_url="https://example.com/dead",
                status_code=None,
                final_url=None,
                sources=[],
            )
        ]
        status, severity = compute_overall_status(findings)
        assert status == "pass"
        assert severity == "none"
