"""
Backward compatibility: ParserService → ParserOrchestrator
"""
from app.modules.parser.services.parser_orchestrator import ParserOrchestrator

ParserService = ParserOrchestrator

__all__ = ["ParserService", "ParserOrchestrator"]
