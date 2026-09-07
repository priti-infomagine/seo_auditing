"""
Backward compatibility: schemas.content_schema → models.content_data
"""
from app.modules.parser.models.content_data import (
    ContentData,
    HeadingData,
    ParagraphData,
    ListData,
    TableData,
    SemanticElement,
)

ContentSchema = ContentData
HeadingSchema = HeadingData
ParagraphSchema = ParagraphData
ListSchema = ListData
TableSchema = TableData
SemanticElementSchema = SemanticElement

__all__ = [
    "ContentData",
    "ContentSchema",
    "HeadingData",
    "HeadingSchema",
    "ParagraphData",
    "ParagraphSchema",
    "ListData",
    "ListSchema",
    "TableData",
    "TableSchema",
    "SemanticElement",
    "SemanticElementSchema",
]
