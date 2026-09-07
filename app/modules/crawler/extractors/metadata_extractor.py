"""
Metadata extractor - dataclass definitions for crawler metadata facts.

.. deprecated::
    BS4 extraction has been removed. Use ``ParserOrchestrator`` + bridge
    (``parsed_document_to_page_facts``) instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetadataFacts:
    title: str = ""
    title_length: int = 0
    meta_description: str = ""
    meta_description_length: int = 0
    canonical: str = ""
    robots_meta: str = ""
    googlebot: str = ""
    viewport: str = ""
    charset: str = ""
    favicon: str = ""
    open_graph: dict = field(default_factory=dict)
    twitter: dict = field(default_factory=dict)
    hreflang: list = field(default_factory=list)
