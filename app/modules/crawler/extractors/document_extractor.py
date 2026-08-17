"""
Document extractor - dataclass definitions for crawler document facts.

.. deprecated::
    BS4 extraction has been removed. Use ``ParserOrchestrator`` + bridge
    (``parsed_document_to_page_facts``) instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DocumentFacts:
    soup: Optional[object] = None
    language: str = ""
    charset: str = ""
    doctype: str = ""
    base_url: str = ""
    is_html: bool = True
    raw_html: str = ""


def create_document_facts(html: str, url: str) -> DocumentFacts:
    """Create a minimal DocumentFacts without BS4 parsing."""
    is_html = html.strip().upper().startswith(("<HTML", "<!DOCTYPE"))
    return DocumentFacts(
        soup=None,
        language="",
        charset="",
        doctype="",
        base_url=url,
        is_html=is_html,
        raw_html=html,
    )
