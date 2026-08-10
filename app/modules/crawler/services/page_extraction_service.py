"""
Page extraction service - coordinates all extractors to produce structured PageFacts.

This service:
1. Receives DocumentFacts from page_crawl_service
2. Calls all relevant extractors
3. Normalizes outputs
4. Returns structured PageFacts

It also supports receiving a ParserService ParsedDocument directly,
converting it to PageFacts via the SEO fact extractor.

It does NOT:
- Make HTTP requests
- Write to PostgreSQL
- Run SEO rules
"""
from dataclasses import dataclass, field
from typing import Optional

from app.modules.crawler.extractors.document_extractor import DocumentFacts
from app.modules.crawler.extractors.content_extractor import ContentFacts, extract_content
from app.modules.crawler.extractors.metadata_extractor import MetadataFacts, extract_metadata
from app.modules.crawler.extractors.link_extractor import LinkFacts, extract_links
from app.modules.crawler.extractors.asset_extractor import ResourceFacts, extract_resources
from app.modules.crawler.extractors.technical_extractor import TechnicalFacts, extract_technical
from app.modules.crawler.extractors.seo_fact_extractor import (
    parsed_document_to_page_facts,
)


@dataclass
class PageFacts:
    """Structured page crawl facts from all extractors."""
    document: DocumentFacts
    content: ContentFacts
    metadata: MetadataFacts
    links: LinkFacts
    resources: ResourceFacts
    technical: TechnicalFacts


class PageExtractionService:
    """Service for coordinating all page extractors."""

    async def extract_all(
        self,
        document: DocumentFacts,
        status_code: int = 0,
        headers: dict = None,
        content_length: int = 0,
        response_time_ms: int = 0,
        redirects: list = None,
    ) -> PageFacts:
        """
        Run all crawler extractors against a DocumentFacts (BeautifulSoup-based).

        This is the original crawler-native path.
        """
        if headers is None:
            headers = {}
        if redirects is None:
            redirects = []

        if not document.is_html:
            return PageFacts(
                document=document,
                content=ContentFacts(),
                metadata=MetadataFacts(),
                links=LinkFacts(),
                resources=ResourceFacts(),
                technical=TechnicalFacts(
                    status_code=status_code,
                    content_length=content_length,
                    response_time_ms=response_time_ms,
                    headers=headers,
                    redirects=redirects,
                ),
            )

        content = extract_content(document.soup, document.raw_html)
        metadata = extract_metadata(document.soup, document.base_url)
        links = extract_links(document.soup, document.base_url)
        resources = extract_resources(document.soup, document.base_url)
        technical = extract_technical(
            status_code=status_code,
            headers=headers,
            content_length=content_length,
            response_time_ms=response_time_ms,
            redirects=redirects,
            soup=document.soup,
            raw_html=document.raw_html,
        )

        return PageFacts(
            document=document,
            content=content,
            metadata=metadata,
            links=links,
            resources=resources,
            technical=technical,
        )

    def extract_from_parsed(
        self,
        parsed_document,
        status_code: int = 0,
        headers: dict | None = None,
        content_length: int = 0,
        response_time_ms: int = 0,
        redirects: list | None = None,
    ) -> PageFacts:
        """
        Convert a ParserService ParsedDocument into PageFacts.

        This path is used when HTML has already been parsed by the parser
        module and we want to produce crawler-compatible PageFacts
        without reparsing the DOM.

        Crawl context (status_code, headers, etc.) is passed separately
        so the parser never needs to know about HTTP transport.
        """
        return parsed_document_to_page_facts(
            parsed_document,
            status_code=status_code,
            headers=headers,
            content_length=content_length,
            response_time_ms=response_time_ms,
            redirects=redirects,
        )

