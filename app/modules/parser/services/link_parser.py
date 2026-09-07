"""
Backward compatibility: LinkParser → LinkExtractor
"""
from app.modules.parser.extractors.link_extractor import LinkExtractor

LinkParser = LinkExtractor

__all__ = ["LinkParser", "LinkExtractor"]
