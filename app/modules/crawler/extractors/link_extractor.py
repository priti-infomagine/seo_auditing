"""
Link extractor - dataclass definitions for crawler link facts.

.. deprecated::
    BS4 extraction has been removed. Use ``ParserOrchestrator`` + bridge
    (``parsed_document_to_page_facts``) instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LinkFacts:
    links: list = field(default_factory=list)
    internal_count: int = 0
    external_count: int = 0
    deep_links: list = field(default_factory=list)
    total_link_count: int = 0
    fragment_count: int = 0
    mailto_count: int = 0
    tel_count: int = 0
    javascript_count: int = 0
    non_http_count: int = 0
