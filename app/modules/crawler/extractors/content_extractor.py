"""
Content extractor - dataclass definitions for crawler content facts.

.. deprecated::
    BS4 extraction has been removed. Use ``ParserOrchestrator`` + bridge
    (``parsed_document_to_page_facts``) instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContentFacts:
    text: str = ""
    word_count: int = 0
    sentence_count: int = 0
    paragraph_count: int = 0
    headings: dict = field(default_factory=dict)
    forms: int = 0
    buttons: int = 0
    content_hash: str = ""
    text_html_ratio: float = 0.0
