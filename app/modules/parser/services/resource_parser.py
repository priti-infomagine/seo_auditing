"""
Backward compatibility: ResourceParser → ResourceExtractor
"""
from app.modules.parser.extractors.resource_extractor import ResourceExtractor

ResourceParser = ResourceExtractor

__all__ = ["ResourceParser", "ResourceExtractor"]
