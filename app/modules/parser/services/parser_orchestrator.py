from __future__ import annotations

from app.modules.parser.models.parsed_page import (
    ParsedPage,
    PageIdentity,
    ParserMetadata,
)
from app.modules.parser.models.page_metadata import PageMetadata
from app.modules.parser.models.content_data import ContentData
from app.modules.parser.models.social_data import SocialData
from app.modules.parser.models.technical_data import TechnicalData
from app.modules.parser.services.document_parser_service import DocumentContext, DocumentParserService
from app.modules.parser.extractors.metadata_extractor import MetadataExtractor
from app.modules.parser.extractors.content_extractor import ContentExtractor
from app.modules.parser.extractors.heading_extractor import HeadingExtractor
from app.modules.parser.extractors.link_extractor import LinkExtractor
from app.modules.parser.extractors.image_extractor import ImageExtractor
from app.modules.parser.extractors.schema_extractor import SchemaExtractor
from app.modules.parser.extractors.hreflang_extractor import HreflangExtractor
from app.modules.parser.extractors.social_extractor import SocialExtractor
from app.modules.parser.extractors.resource_extractor import ResourceExtractor
from app.modules.parser.extractors.technical_extractor import TechnicalExtractor
from app.modules.parser.analyzers import (
    analyze_content,
    analyze_headings,
    analyze_links,
    analyze_images,
    analyze_schemas,
    analyze_hreflang,
    analyze_resources,
)
from app.modules.parser.exceptions import PartialParseError


class ParserOrchestrator:
    """
    Orchestrates document parsing.

    Produces a ParsedPage from raw HTML + URL context.

    This service knows nothing about:
    - filesystem storage
    - database
    - crawler queues
    - SEO scoring
    - rule evaluation
    """

    def __init__(self):
        self.document_parser = DocumentParserService()
        self.extractors = {
            "metadata": MetadataExtractor(),
            "content": ContentExtractor(),
            "heading": HeadingExtractor(),
            "link": LinkExtractor(),
            "image": ImageExtractor(),
            "schema": SchemaExtractor(),
            "hreflang": HreflangExtractor(),
            "social": SocialExtractor(),
            "resource": ResourceExtractor(),
            "technical": TechnicalExtractor(),
        }

    def parse(self, html: str, url: str = "") -> ParsedPage:
        context = self.document_parser.parse(html=html, url=url)

        metadata = self.extractors["metadata"].extract(context)
        content = self.extractors["content"].extract(context)
        headings = self.extractors["heading"].extract(context)
        links = self.extractors["link"].extract(context)
        images = self.extractors["image"].extract(context)
        schemas = self.extractors["schema"].extract(context)
        hreflang = self.extractors["hreflang"].extract(context)
        social = self.extractors["social"].extract(context)
        resources = self.extractors["resource"].extract(context)
        technical = self.extractors["technical"].extract(context)

        analysis: dict[str, dict] = {}
        if content:
            analysis["content"] = analyze_content(content)
            analysis["headings"] = analyze_headings(content)
        if images:
            analysis["images"] = analyze_images(images)
        if schemas:
            analysis["schemas"] = analyze_schemas(schemas)
        if hreflang:
            analysis["hreflang"] = analyze_hreflang(hreflang)
        if resources:
            analysis["resources"] = analyze_resources(resources)
        if links:
            analysis["links"] = analyze_links(links, url)

        errors = context.errors + [
            err for err in context.warnings
            if "error" in err.lower()
        ]

        return ParsedPage(
            document=PageIdentity(
                url=url,
                doctype=context.doctype,
                language=context.language,
                charset=context.charset,
                html_size=len(html.encode("utf-8")),
            ),
            metadata=metadata,
            content=content,
            headings=headings,
            links=links,
            images=images,
            schemas=schemas,
            hreflang=hreflang,
            social=social,
            resources=resources,
            technical=technical,
            parser_metadata=ParserMetadata(
                parser_version="1.0",
                warnings=context.warnings,
                errors=errors,
            ),
        )

    def parse_html(
        self,
        html: str,
        url: str = "",
        crawler_data: dict | None = None,
    ) -> dict:
        """
        API-compatible parse entry point.

        Returns a plain dict so callers do not need to know
        about ParsedPage internals.
        """
        parsed = self.parse(html=html, url=url)
        result = parsed.model_dump(mode="json")
        result["structured_data"] = result.get("schemas", [])

        if crawler_data:
            result["crawler_data"] = {
                "status_code": crawler_data.get("status_code"),
                "content_type": crawler_data.get("content_type"),
                "response_time_ms": crawler_data.get("response_time_ms"),
                "headers": crawler_data.get("headers", {}),
                "redirect_chain": crawler_data.get("redirect_chain", []),
            }

        result.setdefault("crawl_context", {})
        result["crawl_context"].update(
            {
                "requested_url": crawler_data.get("requested_url") if crawler_data else None,
                "final_url": crawler_data.get("final_url") if crawler_data else url,
                "status_code": crawler_data.get("status_code") if crawler_data else None,
            }
        )

        return result
