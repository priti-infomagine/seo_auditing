"""
Backward compatibility: helpers.html_parser → services.document_parser_service
"""
from app.modules.parser.services.document_parser_service import DocumentParserService, DocumentContext

HTMLParser = DocumentParserService
ParserContext = DocumentContext

__all__ = ["HTMLParser", "ParserContext", "DocumentParserService", "DocumentContext"]
