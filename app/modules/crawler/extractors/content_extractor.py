"""
Content extractor - dataclass definitions for crawler content facts.

.. deprecated::
    BS4 extraction has been removed. Use ``ParserOrchestrator`` + bridge
    (``parsed_document_to_page_facts``) instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FormFieldFact:
    tag: str = ""
    type: str = ""
    name: str = ""
    id: str = ""
    label_text: str = ""
    has_label_for: bool = False
    has_wrapping_label: bool = False
    aria_label: str = ""
    aria_labelledby: str = ""
    aria_describedby: str = ""
    required: bool = False
    disabled: bool = False
    readonly: bool = False
    placeholder: str = ""
    title: str = ""
    accessible_name: str = ""
    accessible_name_source: str = ""


@dataclass
class FormFact:
    action: str = ""
    method: str = ""
    id: str = ""
    name: str = ""
    fields: list[FormFieldFact] = field(default_factory=list)
    fieldsets: list[dict] = field(default_factory=list)


@dataclass
class ButtonFact:
    tag: str = ""
    type: str = ""
    id: str = ""
    name: str = ""
    text_content: str = ""
    value: str = ""
    aria_label: str = ""
    aria_labelledby: str = ""
    title: str = ""
    accessible_name: str = ""
    accessible_name_source: str = ""
    has_accessible_name: bool = False


@dataclass
class SkipLinkFact:
    href: str = ""
    text: str = ""
    is_first_focusable: bool = False
    position: int = 0


@dataclass
class LandmarkFact:
    type: str = ""
    element: str = ""
    role: str = ""
    aria_label: str = ""
    aria_labelledby: str = ""
    has_accessible_name: bool = False


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

    # New accessibility fields
    forms_detailed: list[FormFact] = field(default_factory=list)
    buttons_detailed: list[ButtonFact] = field(default_factory=list)
    skip_links: list[SkipLinkFact] = field(default_factory=list)
    landmarks: list[LandmarkFact] = field(default_factory=list)
    aria_attributes: dict = field(default_factory=dict)
    has_main: bool = False
    has_article: bool = False
    has_nav: bool = False
    has_header: bool = False
    has_footer: bool = False