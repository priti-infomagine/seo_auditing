"""
Asset extractor - dataclass definitions for crawler resource facts.

.. deprecated::
    BS4 extraction has been removed. Use ``ParserOrchestrator`` + bridge
    (``parsed_document_to_page_facts``) instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ResourceFacts:
    resources: list = field(default_factory=list)
