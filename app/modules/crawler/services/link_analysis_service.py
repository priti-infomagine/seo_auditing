"""
Link analysis service - analyzes extracted links.

This service:
1. Receives LinkFacts from page_extraction_service
2. Enriches each link with rel-derived flags (nofollow, sponsored, ugc, canonical, hreflang)
3. Returns enriched link list for persistence and enqueue

Broken-link detection and redirect tracking require HTTP checks and are deferred.

It does NOT:
- Write to PostgreSQL
- Determine SEO pass/fail
"""
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

        Enriches each link dict with boolean flags derived from rel,
        link_type, and other attributes so downstream consumers
        (persistence, enqueue) have complete evidence.

        Args:
            link_facts: LinkFacts from link_extractor
            crawl_job_id: Optional crawl job ID for context

        Returns:
            LinkAnalysisResult with enriched links
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

        return LinkAnalysisResult(
            links=enriched_links,
            internal_count=link_facts.internal_count,
            external_count=link_facts.external_count,
            broken_links=[],
            redirect_links=[],
        )
