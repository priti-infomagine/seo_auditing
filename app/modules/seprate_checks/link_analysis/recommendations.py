"""Deterministic recommendation templates for link analysis findings.

No LLM. Each finding type maps to a template with concrete, actionable
steps. The service layer calls ``build_recommendation`` to attach a
recommendation dict to each finding before persistence.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .constants import RECOMMENDATION_CATALOG
from .model import FindingType, LinkAnalysisSeverity
from .analyzer import FindingCandidate, SourceInfo


def build_recommendation(
    candidate: FindingCandidate,
) -> Optional[Dict[str, Any]]:
    """Build a recommendation dict for a finding candidate."""
    ft = candidate.type.value if hasattr(candidate.type, "value") else candidate.type
    catalog_entry = RECOMMENDATION_CATALOG.get(candidate.type)
    if catalog_entry is None:
        return None

    rec: Dict[str, Any] = {
        "title": catalog_entry["title"],
        "priority": catalog_entry["priority"],
        "where_to_fix": catalog_entry["where_to_fix"],
    }

    # Type-specific steps
    rec["action"], rec["fix_steps"] = _build_steps(candidate, ft)

    # Include suggested target for redirects
    if candidate.type in (
        FindingType.REDIRECT_INTERNAL,
        FindingType.REDIRECT_EXTERNAL,
    ) and candidate.final_url:
        rec["suggested_target_url"] = candidate.final_url

    return rec


def _build_steps(
    candidate: FindingCandidate,
    ft: str,
) -> tuple[str, List[str]]:
    """Return (action_text, fix_steps) for a finding type."""
    if ft == "broken_internal":
        total = len(candidate.sources)
        urls = _unique_target_urls(candidate.sources, max_n=5)
        steps = [
            f"On each of the {total} source page(s), verify the link to {candidate.target_url} returns HTTP 404 or other error.",
            f"Fix the link by updating the href to a valid internal page, or remove the link if the target page no longer exists."
            + (f" If the page was moved, set up a 301 redirect to {candidate.final_url}." if candidate.final_url else ""),
        ]
        if candidate.error_type:
            steps.append(f"Diagnosis hint: {candidate.error_type}")
        action = f"{total} internal link(s) point to a broken URL ({candidate.target_url})."
        return action, steps

    if ft == "broken_external":
        total = len(candidate.sources)
        steps = [
            f"Verify the external URL {candidate.target_url} is reachable in a browser.",
            "If the page was moved, update the href to the new URL.",
            "If the page no longer exists, either remove the link or replace with a link to a relevant alternative page.",
            f"Status code received: {candidate.status_code or 'unreachable'}.",
        ]
        action = f"{total} external link(s) point to a broken URL ({candidate.target_url})."
        return action, steps

    if ft in ("redirect_internal", "redirect_external"):
        is_internal = ft == "redirect_internal"
        chain = candidate.redirect_chain or []
        hops = " -> ".join(
            r.location or "" for r in chain
        ) if chain else candidate.final_url or ""
        steps = [
            f"Update the link href from {candidate.target_url}"
            + (f" to the final destination: {candidate.final_url}" if candidate.final_url else ""),
            "Reduce redirect chains to a single hop or eliminate them entirely.",
        ]
        if chain:
            steps.append(f"Redirect chain: {hops}")
        action = f"{len(candidate.sources)} link(s) to {candidate.target_url} trigger redirect(s)."
        return action, steps

    if ft == "orphan":
        extra = candidate.extra or {}
        if extra.get("sitemap_origin"):
            steps = [
                f"Add internal links from at least one crawled page to {candidate.target_url}.",
                "Use descriptive anchor text that matches the target page's topic.",
            ]
        else:
            steps = [
                f"Add internal links from related pages to {candidate.target_url}, or remove the page if it is no longer needed.",
            ]
        if extra.get("crawl_truncated"):
            steps.append(
                "Note: the crawl was truncated; some orphan findings may be false positives."
            )
        total = extra.get("total_sources", len(candidate.sources))
        action = f"Orphan page {candidate.target_url} has {extra.get('inbound_count', 0)} inbound internal links."
        return action, steps

    if ft == "sitemap_url_error":
        steps = [
            f"Remove the broken URL {candidate.target_url} from the sitemap file.",
            "Or correct the URL to point to a working page.",
        ]
        action = f"A sitemap URL ({candidate.target_url}) returns HTTP {candidate.status_code or 'error'}."
        return action, steps

    if ft == "deep_page":
        depth = candidate.extra.get("depth", "?") if candidate.extra else "?"
        steps = [
            f"Move important content from {candidate.target_url} closer to the homepage (depth {depth} > threshold).",
            "Restructure the site hierarchy or add cross-links from higher-level pages.",
        ]
        action = f"Page {candidate.target_url} is at click depth {depth} (threshold: {candidate.extra.get('threshold', '?') if candidate.extra else '?'})."
        return action, steps

    if ft == "dead_end_page":
        steps = [
            f"Add internal links from related pages to {candidate.target_url}.",
            f"Alternatively, add a sitemap.xml entry or breadcrumb navigation.",
        ]
        action = f"Page {candidate.target_url} has zero outgoing internal links."
        return action, steps

    if ft == "weakly_linked_page":
        steps = [
            f"Add at least one more internal link to {candidate.target_url} from a related page.",
        ]
        action = f"Page {candidate.target_url} has only 1 inbound internal link."
        return action, steps

    if ft == "empty_anchor":
        steps = [
            "Replace empty anchor text with descriptive text that matches the target page's topic.",
        ]
        action = f"Links to {candidate.target_url} have empty anchor text."
        return action, steps

    if ft == "generic_anchor":
        steps = [
            f"Replace generic anchor text ('{candidate.extra.get('anchor_text', '') if candidate.extra else ''}') with descriptive text for links to {candidate.target_url}.",
        ]
        action = f"Links to {candidate.target_url} use generic anchor text."
        return action, steps

    if ft == "nofollow_internal":
        steps = [
            f"Remove the rel=nofollow attribute from internal links pointing to {candidate.target_url}.",
            "Search engines may not follow these links, wasting crawl budget.",
        ]
        action = f"{len(candidate.sources)} internal link(s) to {candidate.target_url} are nofollowed."
        return action, steps

    if ft == "insecure_link":
        steps = [
            f"Change http:// links to https:// for {candidate.target_url} on all source pages.",
            "Mixed content can cause browser warnings and SEO issues.",
        ]
        action = f"Links to {candidate.target_url} use insecure HTTP on an HTTPS page."
        return action, steps

    if ft == "excessive_outlinks":
        count = candidate.extra.get("outlink_count", "?") if candidate.extra else "?"
        steps = [
            f"Reduce the number of links on the page to below {candidate.extra.get('threshold', '?') if candidate.extra else '?'} (currently {count}).",
            "Consider consolidating navigation and removing low-value links.",
        ]
        action = f"Page {candidate.target_url} has {count} outgoing links (threshold: {candidate.extra.get('threshold', '?') if candidate.extra else '?'})."
        return action, steps

    return "No specific recommendation available.", ["Review and fix as needed."]


def _unique_target_urls(sources: List[SourceInfo], max_n: int = 5) -> List[str]:
    """Extract unique target URLs from SourceInfo objects."""
    urls: List[str] = []
    seen: set = set()
    for s in sources:
        u = s.source_url
        if u and u not in seen:
            seen.add(u)
            urls.append(u)
        if len(urls) >= max_n:
            break
    return urls


__all__ = [
    "build_recommendation",
]
