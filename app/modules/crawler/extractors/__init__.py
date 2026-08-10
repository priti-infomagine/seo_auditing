# Crawler extractors package
from app.modules.crawler.extractors.document_extractor import (
    DocumentFacts,
    extract_document,
)
from app.modules.crawler.extractors.metadata_extractor import (
    MetadataFacts,
    extract_metadata,
)
from app.modules.crawler.extractors.content_extractor import (
    ContentFacts,
    extract_content,
)
from app.modules.crawler.extractors.link_extractor import (
    LinkFacts,
    extract_links,
)
from app.modules.crawler.extractors.asset_extractor import (
    ResourceFacts,
    extract_resources,
)
from app.modules.crawler.extractors.technical_extractor import (
    TechnicalFacts,
    extract_technical,
)
from app.modules.crawler.extractors.seo_fact_extractor import (
    PageFacts,
    PageSEOFacts,
    SEOFact,
    parsed_document_to_page_facts,
    extract_seo_facts,
)

__all__ = [
    "DocumentFacts",
    "extract_document",
    "MetadataFacts",
    "extract_metadata",
    "ContentFacts",
    "extract_content",
    "LinkFacts",
    "extract_links",
    "ResourceFacts",
    "extract_resources",
    "TechnicalFacts",
    "extract_technical",
    "PageFacts",
    "PageSEOFacts",
    "SEOFact",
    "parsed_document_to_page_facts",
    "extract_seo_facts",
]
