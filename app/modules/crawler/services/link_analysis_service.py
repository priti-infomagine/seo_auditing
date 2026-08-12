"""
Link analysis service - analyzes extracted links.

This service:
1. Receives LinkFacts from page_extraction_service
2. Enriches each link in ``links`` with rel-derived flags (nofollow, sponsored,
   ugc, canonical, hreflang) - unchanged behaviour
3. Computes a deep-analysis summary over ``deep_links``: protocol / link-type
   breakdowns, anchor-text quality, new-tab behaviour, duplicate targets,
   rel-flag roll-ups. If ``deep_links`` is absent it falls back to ``links``.
4. Returns the enriched link list (with summary) for persistence and enqueue

Broken-link detection and redirect tracking require HTTP checks and are deferred.

It does NOT:
- Write to PostgreSQL
- Determine SEO pass/fail
"""
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from app.modules.crawler.extractors.link_extractor import LinkFacts


@dataclass
class LinkAnalysisResult:
    """Structured link analysis result."""
    links: list = field(default_factory=list)
    internal_count: int = 0
    external_count: int = 0
    broken_links: list = field(default_factory=list)
    redirect_links: list = field(default_factory=list)
    # Deep-analysis summary (additive - non-breaking).
    summary: dict = field(default_factory=dict)


class LinkAnalysisService:
    """Service for link analysis."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    async def analyze(
        self,
        link_facts: LinkFacts,
        crawl_job_id: Optional[UUID] = None,
    ) -> LinkAnalysisResult:
        """
        Analyze extracted links.

        Enriches each link dict with boolean flags derived from rel and
        link_type, then computes a deep-analysis summary (protocol / link-type
        breakdowns, anchor-text quality, new-tab, duplicates, rel flags).

        Args:
            link_facts: LinkFacts from link_extractor
            crawl_job_id: Optional crawl job ID for context

        Returns:
            LinkAnalysisResult with enriched links and a deep-analysis summary
        """
        enriched_links = []

        for link in link_facts.links:
            enriched = dict(link)

            link_type = link.get("link_type", "anchor")
            if link_type == "canonical":
                enriched["is_canonical"] = True
            elif link_type == "hreflang":
                enriched["is_hreflang"] = True

            rel = str(link.get("rel", "")).lower()
            enriched["is_nofollow"] = "nofollow" in rel
            enriched["is_sponsored"] = "sponsored" in rel
            enriched["is_ugc"] = "ugc" in rel

            enriched_links.append(enriched)

        # Deep analysis runs over the full surface when available.
        deep_links = getattr(link_facts, "deep_links", None) or enriched_links
        summary = self._build_summary(
            deep_links,
            link_facts.internal_count,
            link_facts.external_count,
        )

        return LinkAnalysisResult(
            links=enriched_links,
            internal_count=link_facts.internal_count,
            external_count=link_facts.external_count,
            broken_links=[],
            redirect_links=[],
            summary=summary,
        )

    def _build_summary(
        self,
        links: list,
        internal_count: int,
        external_count: int,
    ) -> dict:
        """Compute deep-analysis roll-up statistics over the links."""
        total = len(links)

        by_link_type = Counter(l.get("link_type", "anchor") for l in links)
        by_protocol = Counter(
            l.get("protocol", "other")
            for l in links
            if l.get("protocol")
        )
        by_anchor_class = Counter(
            l.get("anchor_text_classification", "unknown") for l in links
        )

        nofollow = sum(1 for l in links if l.get("nofollow") or l.get("is_nofollow"))
        ugc = sum(1 for l in links if l.get("ugc") or l.get("is_ugc"))
        sponsored = sum(1 for l in links if l.get("sponsored") or l.get("is_sponsored"))
        canonical = sum(1 for l in links if l.get("is_canonical") or l.get("link_type") == "canonical")
        hreflang = sum(1 for l in links if l.get("is_hreflang") or l.get("link_type") == "hreflang")
        opens_new_tab = sum(1 for l in links if l.get("opens_new_tab"))
        empty_anchor_text = sum(1 for l in links if not (l.get("anchor_text") or "").strip())
        download_links = sum(1 for l in links if l.get("download"))

        unique_targets = set(l.get("url") for l in links if l.get("url"))
        duplicate_targets = total - len(unique_targets)

        return {
            "total_links": total,
            "internal_count": internal_count,
            "external_count": external_count,
            "non_http_count": sum(1 for l in links if not l.get("is_http", True)),
            "by_link_type": dict(by_link_type),
            "by_protocol": dict(by_protocol),
            "by_anchor_text_classification": dict(by_anchor_class),
            "rel_flags": {
                "nofollow": nofollow,
                "ugc": ugc,
                "sponsored": sponsored,
                "canonical": canonical,
                "hreflang": hreflang,
            },
            "opens_new_tab_count": opens_new_tab,
            "empty_anchor_text_count": empty_anchor_text,
            "download_link_count": download_links,
            "unique_targets": len(unique_targets),
            "duplicate_targets": duplicate_targets,
        }