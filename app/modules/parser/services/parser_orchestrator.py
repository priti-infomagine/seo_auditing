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
from app.modules.parser.models.head_data import HeadData
from app.modules.parser.models.inline_css_data import InlineCSSData
from app.modules.parser.models.inline_js_data import InlineJSData
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
from app.modules.parser.extractors.head_extractor import HeadExtractor
from app.modules.parser.extractors.inline_css_extractor import InlineCSSExtractor
from app.modules.parser.extractors.inline_js_extractor import InlineJSExtractor
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
            "head": HeadExtractor(),
            "inline_css": InlineCSSExtractor(),
            "inline_js": InlineJSExtractor(),
        }

    def parse(self, html: str, url: str = "") -> ParsedPage:
        """Parse static HTML only."""
        return self._parse_with_context(html, url, None)

    def parse_dual(self, html: str, url: str = "", rendered_html: str = "") -> ParsedPage:
        """
        Parse both static and rendered HTML for dual-pass extraction.

        Args:
            html: Static HTML from initial HTTP response
            url: Page URL
            rendered_html: Rendered HTML from Playwright (optional)
        """
        return self._parse_with_context(html, url, rendered_html)

    def _parse_with_context(self, html: str, url: str, rendered_html: str | None) -> ParsedPage:
        # Parse static HTML
        context = self.document_parser.parse(html=html, url=url)

        # Run extractors on static HTML
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
        head = self.extractors["head"].extract(context)
        inline_css = self.extractors["inline_css"].extract(context)
        inline_js = self.extractors["inline_js"].extract(context)

        # Run extractors on rendered HTML if available
        head_rendered = None
        images_rendered = None
        resources_rendered = None
        technical_rendered = None
        inline_css_rendered = None
        inline_js_rendered = None

        if rendered_html and rendered_html != html:
            rendered_context = self.document_parser.parse(html=rendered_html, url=url)
            head_rendered = self.extractors["head"].extract(rendered_context)
            images_rendered = self.extractors["image"].extract(rendered_context)
            resources_rendered = self.extractors["resource"].extract(rendered_context)
            technical_rendered = self.extractors["technical"].extract(rendered_context)
            inline_css_rendered = self.extractors["inline_css"].extract(rendered_context)
            inline_js_rendered = self.extractors["inline_js"].extract(rendered_context)

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
            # New dual-pass fields
            head=head,
            head_rendered=head_rendered,
            images_rendered=images_rendered,
            resources_rendered=resources_rendered,
            technical_rendered=technical_rendered,
            inline_css=inline_css,
            inline_css_rendered=inline_css_rendered,
            inline_js=inline_js,
            inline_js_rendered=inline_js_rendered,
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
