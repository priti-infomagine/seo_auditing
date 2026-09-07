"""
Backward compatibility: schemas.structured_data_schema → models.schema_data
"""
from app.modules.parser.models.schema_data import SchemaData as StructuredDataItem

SchemaMarkupSchema = StructuredDataItem

__all__ = ["StructuredDataItem", "SchemaData", "SchemaMarkupSchema"]
