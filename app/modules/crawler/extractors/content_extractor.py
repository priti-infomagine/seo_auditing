"""
Content extractor - extracts page content, headings, forms, and buttons.
"""
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

    Args:
        soup: BeautifulSoup object
        raw_html: Raw HTML string for ratio calculation

    Returns:
        ContentFacts with content metrics
    """
    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    # Extract main text
    main_content = soup.find("main") or soup.find("article") or soup.find("body")
    if main_content:
        text = main_content.get_text(separator=" ", strip=True)
    else:
        text = soup.get_text(separator=" ", strip=True)

    text = re.sub(r"\s+", " ", text).strip()

    # Word count
    words = re.findall(r"\b\w+\b", text)
    word_count = len(words)

    # Sentence count (rough estimate)
    sentences = re.split(r"[.!?]+", text)
    sentence_count = len([s for s in sentences if s.strip()])

    # Paragraph count
    paragraph_count = len(soup.find_all("p"))

    # Headings
    headings = {}
    for level in range(1, 7):
        tag = f"h{level}"
        tags = soup.find_all(tag)
        headings[tag] = [h.get_text(strip=True) for h in tags if h.get_text(strip=True)]

    # Forms and buttons
    forms = len(soup.find_all("form"))
    buttons = len(soup.find_all("button"))

    # Content hash
    content_hash = hashlib.md5(text.encode("utf-8")).hexdigest() if text else ""

    # Text/HTML ratio
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
