"""
SEO fact extractor - converts ParserService output (ParsedDocument)
into normalized crawler PageFacts AND a flat rule-engine-compatible
SEO-facts dict.

This is the contract boundary:

    ParsedDocument  ──►  PageFacts (crawler dataclasses)
                        SEO facts dict (rule engine input)

No parser knowledge lives in the crawler extractors.
No crawler knowledge lives in the parser.
This file is the bridge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from app.modules.crawler.extractors.asset_extractor import ResourceFacts
from app.modules.crawler.extractors.content_extractor import ContentFacts
from app.modules.crawler.extractors.document_extractor import DocumentFacts
from app.modules.crawler.extractors.link_extractor import LinkFacts
from app.modules.crawler.extractors.metadata_extractor import MetadataFacts
from app.modules.crawler.extractors.technical_extractor import TechnicalFacts


# ---------------------------------------------------------------------------
# Crawler PageFacts - unchanged dataclass, populated from ParsedDocument
# ---------------------------------------------------------------------------

@dataclass
class PageFacts:
    """Structured page crawl facts from all extractors."""
    document: DocumentFacts
    content: ContentFacts
    metadata: MetadataFacts
    links: LinkFacts
    resources: ResourceFacts
    technical: TechnicalFacts


# ---------------------------------------------------------------------------
# SEO fact dataclasses - normalized, provenance-tracked facts
# ---------------------------------------------------------------------------

@dataclass
class SEOFact:
    """A single normalized SEO fact with provenance."""
    fact_type: str
    value: Any = None
    source: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class PageSEOFacts:
    """All SEO facts for a single page."""
    page_facts: PageFacts
    facts: list[SEOFact] = field(default_factory=list)
    rule_engine_data: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Converter: ParsedDocument → PageFacts
# ---------------------------------------------------------------------------

def parsed_document_to_page_facts(
    parsed_document: Any,
    *,
    status_code: int = 0,
    headers: dict | None = None,
    content_length: int = 0,
    response_time_ms: int = 0,
    redirects: list | None = None,
    raw_html: str = "",
) -> PageFacts:
    """
    Convert a ParserService ParsedDocument into the crawler's PageFacts
    dataclass so that the existing persistence layer continues to work
    without modification.

    This function is the ONLY place where ParsedDocument feeds into
    the crawler's extractor/persistence pipeline.
    """
    from app.modules.crawler.extractors.document_extractor import DocumentFacts
    from app.modules.crawler.extractors.content_extractor import ContentFacts
    from app.modules.crawler.extractors.metadata_extractor import MetadataFacts
    from app.modules.crawler.extractors.link_extractor import LinkFacts
    from app.modules.crawler.extractors.asset_extractor import ResourceFacts
    from app.modules.crawler.extractors.technical_extractor import TechnicalFacts

    if headers is None:
        headers = {}
    if redirects is None:
        redirects = []

    doc_info = parsed_document.document
    metadata = parsed_document.metadata
    content = parsed_document.content
    links = parsed_document.links
    resources = parsed_document.resources

    document_facts = DocumentFacts(
        soup=None,
        language=doc_info.language or metadata.language or "",
        charset=doc_info.charset or metadata.charset or "",
        doctype=doc_info.doctype,
        base_url=doc_info.url,
        is_html=True,
        raw_html=raw_html,
    )

    heading_dict: dict = {}
    if content.headings:
        for h in content.headings:
            key = f"h{h.level}"
            heading_dict.setdefault(key, []).append(h.text)

    content_facts = ContentFacts(
        text=content.text or "",
        word_count=content.word_count or 0,
        sentence_count=getattr(content, "sentence_count", 0),
        paragraph_count=len(content.paragraphs or []),
        headings=heading_dict,
        forms=getattr(content, "forms", 0),
        buttons=getattr(content, "buttons", 0),
        content_hash="",
        text_html_ratio=getattr(content, "text_html_ratio", 0.0),
    )

    hreflang_list = []
    for h in (metadata.hreflang or []):
        hreflang_list.append(
            {
                "url": h.href,
                "hreflang": h.hreflang,
            }
        )

    def _first_robot_content(meta_tags, name):
        for t in (meta_tags or []):
            if t.name == name:
                return t.content
        return ""

    robots_meta = _first_robot_content(metadata.robots, "robots")
    googlebot = _first_robot_content(metadata.robots, "googlebot")

    metadata_facts = MetadataFacts(
        title=metadata.title or "",
        title_length=metadata.title_length or len(metadata.title or ""),
        meta_description=metadata.meta_description or "",
        meta_description_length=metadata.meta_description_length or len(metadata.meta_description or ""),
        canonical=metadata.canonical or "",
        robots_meta=robots_meta,
        googlebot=googlebot,
        viewport=metadata.viewport or "",
        charset=metadata.charset or doc_info.charset or "",
        favicon=(metadata.favicon_urls or [""])[0],
        open_graph=dict(metadata.open_graph or {}),
        twitter=dict(metadata.twitter or {}),
        hreflang=hreflang_list,
    )

    page_url = doc_info.url or ""
    page_domain = urlparse(page_url).netloc.lower() if page_url else ""

    link_list = []
    internal_count = 0
    external_count = 0
    for l in links:
        link_url = l.absolute_url or l.href or ""
        link_domain = urlparse(link_url).netloc.lower() if link_url else ""
        is_internal = bool(page_domain) and bool(link_domain) and link_domain == page_domain
        is_external = bool(link_domain) and not is_internal

        if is_internal:
            internal_count += 1
        elif is_external:
            external_count += 1

        link_list.append(
            {
                "url": link_url,
                "anchor_text": l.text,
                "rel": " ".join(l.rel) if l.rel else "",
                "link_type": "anchor",
                "is_internal": is_internal,
                "is_external": is_external,
                "nofollow": "nofollow" in [r.lower() for r in l.rel],
                "ugc": "ugc" in [r.lower() for r in l.rel],
                "sponsored": "sponsored" in [r.lower() for r in l.rel],
            }
        )

    link_facts = LinkFacts(
        links=link_list,
        internal_count=internal_count,
        external_count=external_count,
    )

    resource_list = []
    for r in resources:
        resource_list.append(
            {
                "type": r.resource_type,
                "url": r.url,
                "alt": r.alt,
                "width": r.width,
                "height": r.height,
                "loading": r.loading,
                "srcset": r.srcset,
                "sizes": r.sizes,
                "is_lazy": r.loading == "lazy",
            }
        )

    resource_facts = ResourceFacts(resources=resource_list)

    json_ld_list = []
    for item in parsed_document.structured_data:
        if item.format == "json-ld":
            json_ld_list.append(
                {
                    "type": (item.types or ["Unknown"])[0],
                    "context": item.context,
                    "raw": item.raw,
                    "parsed": item.parsed,
                }
            )

    technical_facts = TechnicalFacts(
        status_code=status_code,
        content_type=headers.get("content-type", "").split(";")[0].strip().lower(),
        content_length=content_length,
        response_time_ms=response_time_ms,
        headers=dict(headers),
        redirects=redirects,
        security={},
        performance={},
        accessibility={},
        json_ld=json_ld_list,
    )

    return PageFacts(
        document=document_facts,
        content=content_facts,
        metadata=metadata_facts,
        links=link_facts,
        resources=resource_facts,
        technical=technical_facts,
    )


# ---------------------------------------------------------------------------
# SEO facts → rule engine flat dict
# ---------------------------------------------------------------------------

def extract_seo_facts(parsed_document: Any) -> dict:
    """
    Convert a ParsedDocument into a flat dict compatible with the rule
    engine's evaluate(data) contract.

    This function lives in the crawler extractors package. It avoids
    importing ParserService at module level to prevent circular imports.
    The conversion logic is self-contained here.

    Every value is raw extracted data - no PASS/FAIL, no thresholds.
    """
    from app.modules.parser.schemas.content_schema import ContentData
    from app.modules.parser.schemas.document_schema import DocumentInfo
    from app.modules.parser.schemas.link_schema import LinkData
    from app.modules.parser.schemas.resource_schema import ResourceData

    metadata = parsed_document.metadata
    content = parsed_document.content
    links = parsed_document.links
    resources = parsed_document.resources
    structured_data = parsed_document.structured_data
    document = parsed_document.document

    heading_lists: dict = {}
    heading_stats: dict = {}
    if content.headings:
        for h in content.headings:
            key = f"h{h.level}"
            heading_lists.setdefault(key, []).append(h.text)

        levels = [h.level for h in content.headings]
        heading_stats = {
            "total_headings": len(content.headings),
            "is_sequential": _is_sequential(levels),
        }

    meta_tags_list = [
        {
            "name": t.name,
            "property": t.property,
            "content": t.content,
            "http_equiv": t.http_equiv,
        }
        for t in (metadata.meta_tags or [])
    ]

    robots_list = [
        {"name": r.name, "content": r.content}
        for r in (metadata.robots or [])
    ]

    hreflang_list = [
        {
            "href": h.href,
            "hreflang": h.hreflang,
            "rel": h.rel,
        }
        for h in (metadata.hreflang or [])
    ]

    og_tags = dict(metadata.open_graph or {})
    twitter_tags = dict(metadata.twitter or {})

    image_resources = [r for r in resources if r.resource_type == "image"]
    script_resources = [r for r in resources if r.resource_type == "script"]
    css_resources = [r for r in resources if r.resource_type == "stylesheet"]

    sd_items: list[dict] = []
    for item in structured_data:
        sd_items.append(
            {
                "format": item.format,
                "raw": item.raw,
                "types": item.types,
                "context": item.context,
                "parse_error": item.attributes.get("parse_error"),
                "attributes": item.attributes,
            }
        )

    crawler_ctx = {}
    if parsed_document.warnings or parsed_document.errors:
        crawler_ctx = {
            "parser_warnings": [w.message for w in parsed_document.warnings],
            "parser_errors": [e.message for e in parsed_document.errors],
        }

    def _first_robot_content(meta_tags, name):
        for t in (meta_tags or []):
            if t.name == name:
                return t.content
        return ""

    robots_meta = _first_robot_content(metadata.robots, "robots")

    return {
        "basic": {
            "url": document.url,
            "title": metadata.title or "",
            "title_length": metadata.title_length or len(metadata.title or ""),
            "meta_description": metadata.meta_description or "",
            "meta_description_length": metadata.meta_description_length or len(metadata.meta_description or ""),
            "meta_keywords": [
                t.content for t in (metadata.meta_tags or [])
                if t.name and t.name.lower() == "keywords"
            ],
            "doctype": document.doctype,
            "language": metadata.language or document.language or "",
            "charset": metadata.charset or document.charset or "",
            "viewport": metadata.viewport or "",
            "html_size": document.html_size,
        },
        "headings": {
            **heading_lists,
            "heading_stats": heading_stats,
        },
        "seo": {
            "canonical_url": metadata.canonical or "",
            "robots_meta": robots_meta,
            "robots": robots_list,
            "meta_tags": meta_tags_list,
            "hreflang": hreflang_list,
            "favicon_urls": list(metadata.favicon_urls or []),
        },
        "social": {
            "open_graph": {
                "tags": og_tags,
            },
            "twitter_cards": {
                "tags": twitter_tags,
            },
        },
        "content": {
            "text": content.text or "",
            "normalized_text": content.normalized_text or "",
            "word_count": content.word_count or 0,
            "character_count": content.character_count or 0,
            "paragraph_count": len(content.paragraphs or []),
            "sentence_count": getattr(content, "sentence_count", 0),
            "text_html_ratio": getattr(content, "text_html_ratio", 0.0),
            "has_main": getattr(content, "has_main", False),
            "has_article": getattr(content, "has_article", False),
            "has_nav": getattr(content, "has_nav", False),
            "has_header": getattr(content, "has_header", False),
            "has_footer": getattr(content, "has_footer", False),
        },
        "links": [
            {
                "href": l.href,
                "absolute_url": l.absolute_url,
                "text": l.text,
                "rel": list(l.rel),
                "target": l.target,
                "title": l.title,
                "download": l.download,
            }
            for l in links
        ],
        "images": [
            {
                "url": r.url,
                "alt": r.alt,
                "title": r.title,
                "width": r.width,
                "height": r.height,
                "loading": r.loading,
                "decoding": r.decoding,
                "srcset": r.srcset,
                "sizes": r.sizes,
            }
            for r in image_resources
        ],
        "scripts": [
            {
                "url": r.url,
                "attributes": r.attributes,
            }
            for r in script_resources
        ],
        "stylesheets": [
            {
                "url": r.url,
                "rel": r.rel,
                "attributes": r.attributes,
            }
            for r in css_resources
        ],
        "resources": [
            {
                "resource_type": r.resource_type,
                "url": r.url,
                "tag": r.tag,
                "alt": r.alt,
                "loading": r.loading,
                "attributes": r.attributes,
            }
            for r in resources
        ],
        "structured_data": sd_items,
        "technical": {
            "doctype": document.doctype,
            "language": document.language or metadata.language or "",
            "charset": document.charset or metadata.charset or "",
        },
        "crawl_context": crawler_ctx,
    }


def _is_sequential(levels: list[int]) -> bool:
    if not levels:
        return True
    for i in range(1, len(levels)):
        if levels[i] > levels[i - 1] + 1:
            return False
    return True
