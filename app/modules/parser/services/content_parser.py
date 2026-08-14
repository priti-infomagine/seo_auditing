"""
Backward compatibility: ContentParser → ContentExtractor
"""
from app.modules.parser.extractors.content_extractor import ContentExtractor

ContentParser = ContentExtractor

__all__ = ["ContentParser", "ContentExtractor"]
