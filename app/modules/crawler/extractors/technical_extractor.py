"""
Technical extractor - dataclass definitions for crawler technical facts.

.. deprecated::
    BS4 extraction has been removed. Use ``ParserOrchestrator`` + bridge
    (``parsed_document_to_page_facts``) instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TechnicalFacts:
    status_code: int = 0
    content_type: str = ""
    content_length: int = 0
    response_time_ms: int = 0
    headers: dict = field(default_factory=dict)
    redirects: list = field(default_factory=list)
    security: dict = field(default_factory=dict)
    performance: dict = field(default_factory=dict)
    accessibility: dict = field(default_factory=dict)
    json_ld: list = field(default_factory=list)
