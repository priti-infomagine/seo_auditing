"""
Page extraction service - converts parser output to crawler PageFacts.

This service now only supports the parser-backed path:

    1. Receives a ParserService ParsedDocument
    2. Converts it to crawler PageFacts via the SEO fact extractor bridge

It does NOT:
- Make HTTP requests
- Write to PostgreSQL
- Run SEO rules
- Run BS4 extractors (removed; parser module is the single extraction source)
"""
from dataclasses import dataclass, field

from app.modules.crawler.extractors.document_extractor import DocumentFacts
from app.modules.crawler.extractors.content_extractor import ContentFacts
from app.modules.crawler.extractors.metadata_extractor import MetadataFacts
from app.modules.crawler.extractors.link_extractor import LinkFacts
from app.modules.crawler.extractors.asset_extractor import ResourceFacts
from app.modules.crawler.extractors.technical_extractor import TechnicalFacts
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
    """Service for converting parser output to crawler PageFacts."""

    def extract_from_parsed(
        self,
        parsed_document,
        status_code: int = 0,
        headers: dict | None = None,
        content_length: int = 0,
        response_time_ms: int = 0,
        redirects: list | None = None,
        raw_html: str = "",
    ) -> PageFacts:
        """
        Convert a ParserService ParsedDocument into PageFacts.

        This is the only active extraction path. HTML is parsed by the
        parser module; this service converts parser output into the
        crawler's dataclass contract.
        """
        return parsed_document_to_page_facts(
            parsed_document,
            status_code=status_code,
            headers=headers,
            content_length=content_length,
            response_time_ms=response_time_ms,
            redirects=redirects,
            raw_html=raw_html,
        )
