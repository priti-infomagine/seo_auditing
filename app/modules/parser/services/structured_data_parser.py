"""
Backward compatibility: StructuredDataParser → SchemaExtractor
"""
from app.modules.parser.extractors.schema_extractor import SchemaExtractor

StructuredDataParser = SchemaExtractor

__all__ = ["StructuredDataParser", "SchemaExtractor"]
