"""
Parser module — SEO fact-extraction pipeline.

Architecture:
  Crawler output → Document parsing → Extractors → Normalizers → Analyzers
  → ParsedPage → Persistence
"""
from app.modules.parser.services.document_parser_service import DocumentParserService
from app.modules.parser.services.parser_orchestrator import ParserOrchestrator
from app.modules.parser.services.batch_parser_service import BatchParserService

__all__ = [
    "DocumentParserService",
    "ParserOrchestrator",
    "BatchParserService",
]
