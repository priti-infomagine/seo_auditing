"""Pure analyzer functions for link analysis.

Takes a LinkGraph + CheckResults + sitemap results and produces
LinkFinding objects grouped by target URL. No I/O, no DB.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from app.core.config import settings
from app.shared.utils.url_utils import normalize_host

from .constants import EVIDENCE_SOURCE_CAP, GENERIC_ANCHORS
from .graph import CheckResult, LinkGraph, RedirectInfo
from .model import (
    FindingCategory,
    FindingType,
    LinkAnalysisSeverity,
    LinkStatusClass,
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SourceInfo:
    source_url: str
    anchor_text: str
    rel: List[str]


@dataclass
class FindingCandidate:
    """Intermediate finding before recommendation assignment."""

    category: FindingCategory
    type: FindingType
    severity: LinkAnalysisSeverity
    target_url: str
    status_code: Optional[int]
    final_url: Optional[str]
    sources: List[SourceInfo]
    redirect_chain: Optional[List[RedirectInfo]] = None
    error_type: Optional[str] = None
    extra: Dict[str, Any] = None


def _cap_sources(sources: List[SourceInfo]) -> List[SourceInfo]:
    return sources[:EVIDENCE_SOURCE_CAP]


def _sources_to_evidence(
    sources: List[SourceInfo],
    total_sources: int,
) -> Dict[str, Any]:
    return {
        "sources": [asdict(s) for s in _cap_sources(sources)],
        "total_sources": total_sources,
    }


# ---------------------------------------------------------------------------
# Group links by target
# ---------------------------------------------------------------------------


def _group_by_target(
    graph: LinkGraph,
) -> Dict[str, List[SourceInfo]]:
    """Group all edges by target_url, collecting source info."""
    by_target: Dict[str, List[SourceInfo]] = {}
    for source_url, target_urls in graph.edges_by_source.items():
        for target_url in target_urls:
            pass  # need to look up edge details
    return by_target


def _group_edges_by_target(
    graph: LinkGraph,
) -> Dict[str, List[SourceInfo]]:
    """Iterate all edges and group by target_url."""
    by_target: Dict[str, List[SourceInfo]] = {}
    for page_node in graph.pages.values():
        for edge in page_node.outgoing_edges:
            by_target.setdefault(edge.target_url, []).append(
                SourceInfo(
                    source_url=edge.source_url,
                    anchor_text=edge.anchor_text,
                    rel=edge.rel,
                )
            )
    return by_target


# ---------------------------------------------------------------------------
# Standard findings
# ---------------------------------------------------------------------------


def _find_broken_internal(
    graph: LinkGraph,
    checked_urls: Dict[str, CheckResult],
    sitemap_urls: Set[str],
) -> List[FindingCandidate]:
    """Find internal links whose target is broken (crawled node or checked URL)."""
    findings: List[FindingCandidate] = []

    # Collect all checked results for internal URLs
    internal_checked = {
        url: result
        for url, result in checked_urls.items()
        if graph.is_same_site(urlparse(url).netloc or "")
    }

    # Check crawled pages
    for url, result in internal_checked.items():
        if result.status_class == LinkStatusClass.BROKEN:
            sources: List[SourceInfo] = []
            # Find which pages link to this URL
            for page_node in graph.pages.values():
                for edge in page_node.outgoing_edges:
                    if edge.target_url == url and edge.is_internal:
                        sources.append(SourceInfo(
                            source_url=edge.source_url,
                            anchor_text=edge.anchor_text,
                            rel=edge.rel,
                        ))

            findings.append(FindingCandidate(
                category=FindingCategory.STANDARD,
                type=FindingType.BROKEN_INTERNAL,
                severity=LinkAnalysisSeverity.HIGH,
                target_url=url,
                status_code=result.status_code,
                final_url=result.final_url,
                sources=sources,
                error_type=result.error_type,
            ))

    return findings


def _find_broken_external(
    checked_urls: Dict[str, CheckResult],
    graph: LinkGraph,
) -> List[FindingCandidate]:
    """Find external links that are broken."""
    findings: List[FindingCandidate] = []

    # Group edges by target for external URLs
    by_target = _group_edges_by_target(graph)

    for url, result in checked_urls.items():
        if result.status_class == LinkStatusClass.BROKEN:
            # Check if this is an external URL
            if not graph.is_same_site(urlparse(url).netloc or ""):
                sources = by_target.get(url, [])
                findings.append(FindingCandidate(
                    category=FindingCategory.STANDARD,
                    type=FindingType.BROKEN_EXTERNAL,
                    severity=LinkAnalysisSeverity.MEDIUM,
                    target_url=url,
                    status_code=result.status_code,
                    final_url=result.final_url,
                    sources=sources,
                    error_type=result.error_type,
                ))

    return findings


def _find_redirects(
    graph: LinkGraph,
    checked_urls: Dict[str, CheckResult],
    crawl_truncated: bool,
) -> List[FindingCandidate]:
    """Find internal and external links that redirect."""
    findings: List[FindingCandidate] = []
    by_target = _group_edges_by_target(graph)

    for url, result in checked_urls.items():
        if result.status_class == LinkStatusClass.REDIRECT and result.redirect_chain:
            is_internal = graph.is_same_site(urlparse(url).netloc or "")
            chain_len = len(result.redirect_chain)

            severity = (
                LinkAnalysisSeverity.MEDIUM
                if chain_len > 1
                else LinkAnalysisSeverity.LOW
            )

            finding_type = (
                FindingType.REDIRECT_INTERNAL
                if is_internal
                else FindingType.REDIRECT_EXTERNAL
            )

            findings.append(FindingCandidate(
                category=FindingCategory.STANDARD,
                type=finding_type,
                severity=severity,
                target_url=url,
                status_code=result.status_code,
                final_url=result.final_url,
                sources=by_target.get(url, []),
                redirect_chain=result.redirect_chain,
            ))

    return findings


def _find_orphans(
    graph: LinkGraph,
    sitemap_urls: Set[str],
    crawl_truncated: bool,
) -> List[FindingCandidate]:
    """Find orphan pages: sitemap URLs with zero inbound internal links."""
    findings: List[FindingCandidate] = []

    # Collect all crawled URLs (normalized)
    crawled_urls = set(graph.pages.keys())

    # Build sitemap URL set (normalized)
    sitemap_normalized: Set[str] = set()
    for url in sitemap_urls:
        try:
            from app.shared.utils.url_utils import normalize_url
            sitemap_normalized.add(normalize_url(url))
        except Exception:
            sitemap_normalized.add(url)

    # Sitemap-only URLs not discovered during crawl
    sitemap_only = sitemap_normalized - crawled_urls

    # Orphans from sitemap: URLs in sitemap not crawled
    for url in sitemap_only:
        findings.append(FindingCandidate(
            category=FindingCategory.STANDARD,
            type=FindingType.ORPHAN,
            severity=LinkAnalysisSeverity.MEDIUM if not crawl_truncated else LinkAnalysisSeverity.LOW,
            target_url=url,
            status_code=None,
            final_url=None,
            sources=[],
            extra={
                "sitemap_origin": True,
                "crawl_truncated": crawl_truncated,
                "inbound_count": 0,
                "pages_crawled": len(crawled_urls),
            },
        ))

    # Crawled pages with zero inbound internal links (excluding homepage)
    homepage_url = None
    for url in crawled_urls:
        if normalize_host(urlparse(url).netloc or "") == graph.base_host:
            if not homepage_url or len(url) < len(homepage_url):
                homepage_url = url

    for url in crawled_urls:
        if url == homepage_url:
            continue
        inbound = graph.inbound_counts.get(url, 0)
        if inbound == 0:
            findings.append(FindingCandidate(
                category=FindingCategory.STANDARD,
                type=FindingType.ORPHAN,
                severity=LinkAnalysisSeverity.MEDIUM if not crawl_truncated else LinkAnalysisSeverity.LOW,
                target_url=url,
                status_code=None,
                final_url=None,
                sources=[],
                extra={
                    "sitemap_origin": url in sitemap_normalized,
                    "crawl_truncated": crawl_truncated,
                    "inbound_count": 0,
                    "pages_crawled": len(crawled_urls),
                },
            ))

    return findings


def _find_sitemap_url_errors(
    sitemap_urls: Set[str],
    checked_urls: Dict[str, CheckResult],
) -> List[FindingCandidate]:
    """Find sitemap URLs that are broken or redirect."""
    findings: List[FindingCandidate] = []
    by_target = {}  # will be built from graph edges if needed

    for url in sitemap_urls:
        try:
            from app.shared.utils.url_utils import normalize_url
            norm = normalize_url(url)
        except Exception:
            norm = url

        result = checked_urls.get(norm)
        if result is None:
            # Some sitemap URLs might have different normalization
            result = checked_urls.get(url)

        if result and result.status_class == LinkStatusClass.BROKEN:
            findings.append(FindingCandidate(
                category=FindingCategory.STANDARD,
                type=FindingType.SITEMAP_URL_ERROR,
                severity=LinkAnalysisSeverity.MEDIUM,
                target_url=url,
                status_code=result.status_code,
                final_url=result.final_url,
                sources=[],
                error_type=result.error_type,
                extra={"source": "sitemap"},
            ))

    return findings


# ---------------------------------------------------------------------------
# Optimization findings
# ---------------------------------------------------------------------------


def _find_deep_pages(
    graph: LinkGraph,
) -> List[FindingCandidate]:
    """Find pages deeper than DEEP_PAGE_THRESHOLD."""
    findings: List[FindingCandidate] = []
    threshold = settings.LINK_ANALYSIS_DEEP_PAGE_THRESHOLD

    for url, node in graph.pages.items():
        if node.status_code == 200 and node.depth is not None and node.depth > threshold:
            findings.append(FindingCandidate(
                category=FindingCategory.OPTIMIZATION,
                type=FindingType.DEEP_PAGE,
                severity=LinkAnalysisSeverity.LOW,
                target_url=url,
                status_code=node.status_code,
                final_url=node.final_url,
                sources=[],
                extra={"depth": node.depth, "threshold": threshold},
            ))

    return findings


def _find_dead_end_pages(
    graph: LinkGraph,
) -> List[FindingCandidate]:
    """Find 200 HTML pages with zero outgoing internal links."""
    findings: List[FindingCandidate] = []

    for url, node in graph.pages.items():
        if node.status_code != 200:
            continue
        internal_outgoing = [e for e in node.outgoing_edges if e.is_internal]
        if not internal_outgoing:
            findings.append(FindingCandidate(
                category=FindingCategory.OPTIMIZATION,
                type=FindingType.DEAD_END_PAGE,
                severity=LinkAnalysisSeverity.LOW,
                target_url=url,
                status_code=node.status_code,
                final_url=node.final_url,
                sources=[],
                extra={"outgoing_internal": 0},
            ))

    return findings


def _find_weakly_linked_pages(
    graph: LinkGraph,
    crawl_truncated: bool,
) -> List[FindingCandidate]:
    """Find pages with exactly one inbound internal link."""
    if crawl_truncated:
        return []

    findings: List[FindingCandidate] = []

    for url in graph.pages:
        inbound = graph.inbound_counts.get(url, 0)
        if inbound == 1:
            findings.append(FindingCandidate(
                category=FindingCategory.OPTIMIZATION,
                type=FindingType.WEAKLY_LINKED_PAGE,
                severity=LinkAnalysisSeverity.LOW,
                target_url=url,
                status_code=None,
                final_url=None,
                sources=[],
                extra={"inbound_count": 1},
            ))

    return findings


def _find_anchor_issues(
    graph: LinkGraph,
) -> List[FindingCandidate]:
    """Find empty or generic anchor text, grouped by target."""
    by_target: Dict[str, Dict[str, Any]] = {}

    for page_node in graph.pages.values():
        for edge in page_node.outgoing_edges:
            target = edge.target_url
            if not edge.anchor_text.strip():
                key = (FindingType.EMPTY_ANCHOR, target)
                if key not in by_target:
                    by_target[key] = {
                        "sources": [],
                        "target_url": target,
                    }
                by_target[key]["sources"].append(SourceInfo(
                    source_url=edge.source_url,
                    anchor_text="",
                    rel=edge.rel,
                ))
            elif edge.anchor_text.strip().lower() in GENERIC_ANCHORS:
                key = (FindingType.GENERIC_ANCHOR, target)
                if key not in by_target:
                    by_target[key] = {
                        "sources": [],
                        "target_url": target,
                        "anchor_text": edge.anchor_text,
                    }
                by_target[key]["sources"].append(SourceInfo(
                    source_url=edge.source_url,
                    anchor_text=edge.anchor_text,
                    rel=edge.rel,
                ))

    findings: List[FindingCandidate] = []
    for (finding_type, target), data in by_target.items():
        sources = data["sources"]
        total = len(sources)
        evidence = _sources_to_evidence(sources, total)
        evidence["anchor_text"] = data.get("anchor_text", "")

        findings.append(FindingCandidate(
            category=FindingCategory.OPTIMIZATION,
            type=finding_type,
            severity=LinkAnalysisSeverity.LOW,
            target_url=target,
            status_code=None,
            final_url=None,
            sources=sources,
            extra=evidence,
        ))

    return findings


def _find_nofollow_internal(
    graph: LinkGraph,
) -> List[FindingCandidate]:
    """Find internal links with rel=nofollow, grouped by target."""
    by_target: Dict[str, List[SourceInfo]] = {}

    for page_node in graph.pages.values():
        for edge in page_node.outgoing_edges:
            if not edge.is_internal:
                continue
            if "nofollow" not in [r.lower() for r in edge.rel]:
                continue
            by_target.setdefault(edge.target_url, []).append(SourceInfo(
                source_url=edge.source_url,
                anchor_text=edge.anchor_text,
                rel=edge.rel,
            ))

    findings: List[FindingCandidate] = []
    for target, sources in by_target.items():
        total = len(sources)
        findings.append(FindingCandidate(
            category=FindingCategory.OPTIMIZATION,
            type=FindingType.NOFOLLOW_INTERNAL,
            severity=LinkAnalysisSeverity.LOW,
            target_url=target,
            status_code=None,
            final_url=None,
            sources=sources,
        ))

    return findings


def _find_insecure_links(
    graph: LinkGraph,
) -> List[FindingCandidate]:
    """Find http:// links on https pages."""
    by_target: Dict[str, Dict[str, Any]] = {}

    for page_node in graph.pages.values():
        source_scheme = urlparse(page_node.final_url or page_node.url).scheme.lower()
        if source_scheme != "https":
            continue

        for edge in page_node.outgoing_edges:
            if not edge.is_internal:
                continue
            if not edge.target_url.startswith("http://"):
                continue

            if edge.target_url not in by_target:
                by_target[edge.target_url] = {
                    "sources": [],
                }
            by_target[edge.target_url]["sources"].append(SourceInfo(
                source_url=edge.source_url,
                anchor_text=edge.anchor_text,
                rel=edge.rel,
            ))

    findings: List[FindingCandidate] = []
    for target, data in by_target.items():
        sources = data["sources"]
        total = len(sources)
        evidence = _sources_to_evidence(sources, total)
        findings.append(FindingCandidate(
            category=FindingCategory.OPTIMIZATION,
            type=FindingType.INSECURE_LINK,
            severity=LinkAnalysisSeverity.MEDIUM,
            target_url=target,
            status_code=None,
            final_url=None,
            sources=sources,
            extra=evidence,
        ))

    return findings


def _find_excessive_outlinks(
    graph: LinkGraph,
) -> List[FindingCandidate]:
    """Find pages with more than MAX_OUTLINKS links."""
    findings: List[FindingCandidate] = []
    max_outlinks = settings.LINK_ANALYSIS_MAX_OUTLINKS

    for url, node in graph.pages.items():
        outlink_count = len(node.outgoing_edges)
        if outlink_count > max_outlinks:
            findings.append(FindingCandidate(
                category=FindingCategory.OPTIMIZATION,
                type=FindingType.EXCESSIVE_OUTLINKS,
                severity=LinkAnalysisSeverity.LOW,
                target_url=url,
                status_code=node.status_code,
                final_url=node.final_url,
                sources=[],
                extra={"outlink_count": outlink_count, "threshold": max_outlinks},
            ))

    return findings


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def analyze(
    graph: LinkGraph,
    checked_urls: Dict[str, CheckResult],
    sitemap_urls: Set[str],
    crawl_truncated: bool,
) -> List[FindingCandidate]:
    """Run all finding analyzers on the graph + checked URLs.

    Returns a flat list of FindingCandidate objects grouped by target.
    Standard findings only (optimization findings are separate).
    """
    findings: List[FindingCandidate] = []

    # Standard findings
    findings.extend(_find_broken_internal(graph, checked_urls, sitemap_urls))
    findings.extend(_find_broken_external(checked_urls, graph))
    findings.extend(_find_redirects(graph, checked_urls, crawl_truncated))
    findings.extend(_find_orphans(graph, sitemap_urls, crawl_truncated))
    findings.extend(_find_sitemap_url_errors(sitemap_urls, checked_urls))

    return findings


def analyze_optimization(
    graph: LinkGraph,
    crawl_truncated: bool,
) -> List[FindingCandidate]:
    """Run optimization finding analyzers."""
    findings: List[FindingCandidate] = []

    findings.extend(_find_deep_pages(graph))
    findings.extend(_find_dead_end_pages(graph))
    findings.extend(_find_weakly_linked_pages(graph, crawl_truncated))
    findings.extend(_find_anchor_issues(graph))
    findings.extend(_find_nofollow_internal(graph))
    findings.extend(_find_insecure_links(graph))
    findings.extend(_find_excessive_outlinks(graph))

    return findings


def compute_page_analysis(
    graph: LinkGraph,
    findings: List[FindingCandidate],
) -> List[Dict[str, Any]]:
    """Compute per-page link analysis metrics and issues without duplicate bloat."""
    # Index issues by URL (both where page is source and target)
    issues_by_page: Dict[str, List[str]] = {}

    for f in findings:
        ft = f.type.value if hasattr(f.type, "value") else str(f.type)
        if f.target_url:
            msg = f"Target of {ft}"
            if f.status_code:
                msg += f" (HTTP {f.status_code})"
            issues_by_page.setdefault(f.target_url, []).append(msg)

        for s in f.sources:
            if s.source_url:
                msg = f"Links to {ft}: {f.target_url}"
                if msg not in issues_by_page.setdefault(s.source_url, []):
                    issues_by_page[s.source_url].append(msg)

    homepage_url = None
    for url in graph.pages:
        if normalize_host(urlparse(url).netloc or "") == graph.base_host:
            if not homepage_url or len(url) < len(homepage_url):
                homepage_url = url

    pages: List[Dict[str, Any]] = []
    for url, node in graph.pages.items():
        inbound = graph.inbound_counts.get(url, 0)
        out_internal = sum(1 for e in node.outgoing_edges if e.is_internal)
        out_external = sum(1 for e in node.outgoing_edges if not e.is_internal)
        is_orphan = (inbound == 0 and url != homepage_url)
        is_dead_end = (node.status_code == 200 and out_internal == 0)

        page_issues = issues_by_page.get(url, [])

        pages.append({
            "url": url,
            "status_code": node.status_code,
            "depth": -1 if node.depth is None else node.depth,
            "inbound_internal_links": inbound,
            "outbound_internal_links": out_internal,
            "outbound_external_links": out_external,
            "is_orphan": is_orphan,
            "is_dead_end": is_dead_end,
            "issues": page_issues[:10],
        })

    # Sort pages by depth then inbound links descending
    pages.sort(key=lambda p: (
        float("inf") if p["depth"] == -1 else p["depth"],
        -p["inbound_internal_links"],
    ))
    return pages


def compute_summary(
    graph: LinkGraph,
    checked_urls: Dict[str, CheckResult],
    findings: List[FindingCandidate],
    sitemap_urls: Set[str],
    crawl_truncated: bool,
) -> Dict[str, Any]:
    """Build the clean JSONB summary and page analysis for the check master row."""
    internal_targets = len({
        url for url in checked_urls
        if graph.is_same_site(urlparse(url).netloc or "")
    })
    external_targets = len(checked_urls) - internal_targets

    broken_count = sum(
        1 for r in checked_urls.values()
        if r.status_class == LinkStatusClass.BROKEN
    )
    unverified_count = sum(
        1 for r in checked_urls.values()
        if r.status_class == LinkStatusClass.UNVERIFIED
    )

    standard_findings = [f for f in findings if f.category == FindingCategory.STANDARD]
    optimization_findings = [f for f in findings if f.category == FindingCategory.OPTIMIZATION]

    # Count by type
    by_type: Dict[str, int] = {}
    by_severity: Dict[str, int] = {}
    for f in findings:
        ft = f.type.value if hasattr(f.type, "value") else f.type
        by_type[ft] = by_type.get(ft, 0) + 1
        sv = f.severity.value if hasattr(f.severity, "value") else f.severity
        by_severity[sv] = by_severity.get(sv, 0) + 1

    pages_list = compute_page_analysis(graph, findings)

    return {
        "pages_crawled": len(graph.pages),
        "crawl_truncated": crawl_truncated,
        "blocked_by_robots": 0,  # set by caller
        "internal_link_occurrences": sum(
            1 for p in graph.pages.values() for e in p.outgoing_edges if e.is_internal
        ),
        "unique_internal_targets": internal_targets,
        "unique_external_targets": external_targets,
        "unverified_links": unverified_count,
        "broken_links": broken_count,
        "counts_by_category": {
            "standard": len(standard_findings),
            "optimization": len(optimization_findings),
        },
        "counts_by_type": by_type,
        "counts_by_severity": by_severity,
        "total_issues": len(standard_findings),
        "total_opportunities": len(optimization_findings),
        "pages": pages_list,
    }


def compute_overall_status(
    findings: List[FindingCandidate],
) -> tuple[str, str]:
    """Compute overall status and severity from STANDARD findings only."""
    standard_findings = [
        f for f in findings if f.category == FindingCategory.STANDARD
    ]

    if not standard_findings:
        return "pass", "none"

    has_high = any(f.severity == LinkAnalysisSeverity.HIGH for f in standard_findings)
    has_medium = any(f.severity == LinkAnalysisSeverity.MEDIUM for f in standard_findings)
    has_low = any(f.severity == LinkAnalysisSeverity.LOW for f in standard_findings)

    if has_high:
        return "fail", LinkAnalysisSeverity.HIGH.value
    if has_medium:
        return "warning", LinkAnalysisSeverity.MEDIUM.value
    if has_low:
        return "warning", LinkAnalysisSeverity.LOW.value

    return "warning", "low"


# Fix the missing settings reference for MAX_OUTLINKS
