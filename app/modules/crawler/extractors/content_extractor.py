"""
Content extractor - extracts page content, headings, forms, and buttons.
"""
import copy
from dataclasses import dataclass, field
import hashlib
import re
from bs4 import BeautifulSoup


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


def extract_content(soup: BeautifulSoup, raw_html: str = "") -> ContentFacts:
    """
    Extract content facts from parsed HTML.

    Works on a copy of the soup so the original DOM is preserved
    for downstream extractors (links, resources, structured data).

    Args:
        soup: BeautifulSoup object (NOT mutated)
        raw_html: Raw HTML string for ratio calculation

    Returns:
        ContentFacts with content metrics
    """
    working = copy.copy(soup)

    for tag in working(["script", "style", "noscript", "template"]):
        tag.decompose()

    text = working.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()

    words = re.findall(r"\b\w+\b", text)
    word_count = len(words)

    sentences = re.split(r"[.!?]+", text)
    sentence_count = len([s for s in sentences if s.strip()])

    paragraph_count = len(working.find_all("p"))

    headings = {}
    for level in range(1, 7):
        tag = f"h{level}"
        tags = working.find_all(tag)
        headings[tag] = [h.get_text(strip=True) for h in tags if h.get_text(strip=True)]

    forms = len(working.find_all("form"))
    buttons = len(working.find_all("button"))

    content_hash = hashlib.md5(text.encode("utf-8")).hexdigest() if text else ""

    text_html_ratio = 0.0
    if raw_html:
        html_length = len(raw_html)
        text_length = len(text)
        if html_length > 0:
            text_html_ratio = round(text_length / html_length, 3)

    return ContentFacts(
        text=text,
        word_count=word_count,
        sentence_count=sentence_count,
        paragraph_count=paragraph_count,
        headings=headings,
        forms=forms,
        buttons=buttons,
        content_hash=content_hash,
        text_html_ratio=text_html_ratio,
    )
