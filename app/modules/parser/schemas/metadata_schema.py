"""
Backward compatibility: schemas.metadata_schema → models.page_metadata
"""
from app.modules.parser.models.page_metadata import (
    PageMetadata,
    MetaTag,
    HreflangLink,
)

MetadataData = PageMetadata
MetadataSchema = PageMetadata
MetaTagSchema = MetaTag
HreflangLinkSchema = HreflangLink

__all__ = [
    "MetadataData",
    "MetadataSchema",
    "MetaTagSchema",
    "HreflangLinkSchema",
    "PageMetadata",
    "MetaTag",
    "HreflangLink",
]
