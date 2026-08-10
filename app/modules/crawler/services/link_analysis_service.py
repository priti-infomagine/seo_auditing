"""
Link analysis service - analyzes extracted links.

This service:
1. Receives LinkFacts from page_extraction_service
2. Classifies internal/external
3. Tracks redirect targets
4. Detects broken links (evidence only, no PASS/FAIL)

It does NOT:
- Write to PostgreSQL
- Determine SEO pass/fail
"""
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from app.modules.crawler.extractors.link_extractor import LinkFacts
from app.shared.utils.url_utils import is_internal_link


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

        Args:
            link_facts: LinkFacts from link_extractor
            crawl_job_id: Optional crawl job ID for context

        Returns:
            LinkAnalysisResult with analysis
        """
        broken_links = []
        redirect_links = []

        for link in link_facts.links:
            analyzed_link = dict(link)

            if link.get("link_type") == "canonical":
                analyzed_link["is_canonical"] = True
            elif link.get("link_type") == "hreflang":
                analyzed_link["is_hreflang"] = True

            if link.get("rel", "").lower().count("nofollow") > 0:
                analyzed_link["is_nofollow"] = True

            if link.get("rel", "").lower().count("sponsored") > 0:
                analyzed_link["is_sponsored"] = True

            if link.get("rel", "").lower().count("ugc") > 0:
                analyzed_link["is_ugc"] = True

        return LinkAnalysisResult(
            links=link_facts.links,
            internal_count=link_facts.internal_count,
            external_count=link_facts.external_count,
            broken_links=broken_links,
            redirect_links=redirect_links,
        )
