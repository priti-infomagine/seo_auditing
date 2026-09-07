"""
Backward compatibility: MetadataParser → MetadataExtractor
"""
from app.modules.parser.extractors.metadata_extractor import MetadataExtractor

MetadataParser = MetadataExtractor

__all__ = ["MetadataParser", "MetadataExtractor"]
