from ..schemas.document_schema import DocumentInfo, ParsedDocument
from .content_parser import ContentParser
from .helpers.html_parser import HTMLParser
from .link_parser import LinkParser
from .metadata_parser import MetadataParser
from .resource_parser import ResourceParser
from .structured_data_parser import StructuredDataParser


class ParserService:
    """
    Orchestrates document parsing.

    Produces a stable ParsedDocument from raw HTML + URL context.

    This service knows nothing about:
    - filesystem storage
    - database
    - crawler queues
    - SEO scoring
    - rule evaluation
    """

    def __init__(self):
        self.html_parser = HTMLParser()
        self.metadata_parser = MetadataParser()
        self.content_parser = ContentParser()
        self.link_parser = LinkParser()
        self.resource_parser = ResourceParser()
        self.structured_data_parser = StructuredDataParser()

    def parse(
        self,
        html: str,
        url: str = "",
    ) -> ParsedDocument:
        context = self.html_parser.parse(html=html, url=url)

        metadata = self.metadata_parser.parse(context)
        content = self.content_parser.parse(context)
        links = self.link_parser.parse(context)
        resources = self.resource_parser.parse(context)
        structured_data = self.structured_data_parser.parse(context)

        return ParsedDocument(
            document=DocumentInfo(
                url=url,
                doctype=context.doctype,
                language=context.language,
                charset=context.charset,
                html_size=len(html.encode("utf-8")),
            ),
            metadata=metadata,
            content=content,
            links=links,
            resources=resources,
            structured_data=structured_data,
            warnings=[
                {"level": "warning", "message": message}
                for message in context.warnings
            ],
            errors=[
                {"level": "error", "message": message}
                for message in context.errors
            ],
        )

    def parse_html(
        self,
        html: str,
        url: str = "",
        crawler_data: dict | None = None,
    ) -> dict:
        """
        API-compatible parse entry point used by score/analyze endpoints.

        Returns a plain dict (not a Pydantic model) so callers
        do not need to know about ParsedDocument internals.
        """
        parsed = self.parse(html=html, url=url)
        result = parsed.model_dump(mode="json")

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
