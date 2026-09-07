# Crawler extractors package

# Deprecated: only dataclasses remain here.
# Extraction is now provided by the parser module.
from app.modules.crawler.extractors.document_extractor import (
    DocumentFacts,
    create_document_facts,
)
from app.modules.crawler.extractors.metadata_extractor import MetadataFacts
from app.modules.crawler.extractors.content_extractor import ContentFacts
from app.modules.crawler.extractors.link_extractor import LinkFacts
from app.modules.crawler.extractors.asset_extractor import ResourceFacts
from app.modules.crawler.extractors.technical_extractor import TechnicalFacts
from app.modules.crawler.extractors.seo_fact_extractor import (
    PageFacts,
    PageSEOFacts,
    SEOFact,
    parsed_document_to_page_facts,
    extract_seo_facts,
)

__all__ = [
    "DocumentFacts",
    "create_document_facts",
    "MetadataFacts",
    "ContentFacts",
    "LinkFacts",
    "ResourceFacts",
    "TechnicalFacts",
    "PageFacts",
    "PageSEOFacts",
    "SEOFact",
    "parsed_document_to_page_facts",
    "extract_seo_facts",
]
