"""
Backward compatibility: schemas.document_schema → models.parsed_page
"""
from app.modules.parser.models.parsed_page import ParsedPage, PageIdentity, ParserMetadata

DocumentInfo = PageIdentity
ParsedDocument = ParsedPage

__all__ = ["ParsedDocument", "DocumentInfo", "ParsedPage", "PageIdentity", "ParserMetadata"]
