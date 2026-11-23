from __future__ import annotations
from app.modules.parser.models.eeat_data import EEATData
from app.modules.parser.analyzers.eeat_analyzer import EEATAnalyzer
from app.modules.parser.services.document_parser_service import DocumentContext


class EEATExtractor:
    """
    Parser pipeline extractor for E-E-A-T signals.
    
    Runs the EEATAnalyzer and returns EEATData for storage in ParsedPage.
    """
    
    def __init__(self):
        self.analyzer = EEATAnalyzer()
    
    def extract(self, context: DocumentContext) -> EEATData:
        # Get page_type from context if available (for YMYL context)
        page_type = getattr(context, "page_type", "") or ""
        url = getattr(context, "url", "") or ""
        
        return self.analyzer.analyze(context.soup, url, page_type)