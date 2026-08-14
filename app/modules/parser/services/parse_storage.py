"""
Backward compatibility: parse_storage.ParseService → BatchParserService
"""
from app.modules.parser.services.batch_parser_service import BatchParserService

ParseService = BatchParserService

__all__ = ["ParseService", "BatchParserService"]
