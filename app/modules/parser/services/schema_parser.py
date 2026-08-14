"""
Backward compatibility: SchemaParser → SchemaExtractor (with legacy methods)
"""
from app.modules.parser.extractors.schema_extractor import SchemaExtractor
from bs4 import BeautifulSoup


class SchemaParser:
    """Legacy compatibility wrapper."""

    @staticmethod
    def get_schema_markup(soup: BeautifulSoup):
        return SchemaExtractor().extract(type("C", (), {"soup": soup})())

    @staticmethod
    def has_schema_markup(soup: BeautifulSoup) -> bool:
        return len(SchemaParser.get_schema_markup(soup)) > 0

    @staticmethod
    def get_schema_types(soup: BeautifulSoup):
        items = SchemaParser.get_schema_markup(soup)
        types = []
        for item in items:
            types.extend(item.types or [])
        return list(set(types))

    @staticmethod
    def validate_schema(soup: BeautifulSoup) -> dict:
        items = SchemaParser.get_schema_markup(soup)
        return {
            "has_schema": len(items) > 0,
            "schema_count": len(items),
            "schema_types": SchemaParser.get_schema_types(soup),
            "issues": [],
            "warnings": [],
            "valid": True,
        }


__all__ = ["SchemaParser"]
