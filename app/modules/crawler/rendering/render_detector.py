"""
RenderDetector - Heuristics to decide if Playwright browser rendering is required.
"""
import re
from bs4 import BeautifulSoup
from typing import Tuple

from app.modules.crawler.types import FetchResult

SPA_ROOT_TAGS = [
    '<div id="root"></div>',
    '<div id="app"></div>',
    '<app-root></app-root>',
    '<div id="__next"></div>',
    '<div id="__nuxt"></div>',
]


class RenderDetector:
    """Detects if an HTTP response represents a JS/SPA shell requiring browser rendering."""

    def __init__(
        self,
        min_body_length: int = 10000,
        min_word_count: int = 15,
        min_text_ratio: float = 0.015,
    ):
        self.min_body_length = min_body_length
        self.min_word_count = min_word_count
        self.min_text_ratio = min_text_ratio

    def needs_browser_render(self, fetch_result: FetchResult) -> Tuple[bool, str]:
        """
        Inspect fetch result and return (needs_render: bool, reason: str).
        """
        if not fetch_result.success or not fetch_result.content:
            return False, "http_fetch_failed"

        content_type = fetch_result.content_type or ""
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return False, "not_html"

        html_text = fetch_result.content.decode("utf-8", errors="ignore")
        raw_length = len(html_text)

        # Check SPA root element signatures
        for root_sig in SPA_ROOT_TAGS:
            if root_sig in html_text:
                return True, f"spa_root_element:{root_sig}"

        try:
            soup = BeautifulSoup(html_text, "html.parser")
        except Exception:
            return False, "parse_error"

        # Check Title
        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else ""
        if not title_text:
            # Missing title in HTML shell
            return True, "missing_title"

        # Clean text
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(" ", strip=True)
        words = re.findall(r"\b\w+\b", text)
        word_count = len(words)

        if word_count < self.min_word_count:
            return True, f"low_word_count:{word_count}"

        if raw_length < self.min_body_length and word_count < 30:
            return True, f"small_html_shell:{raw_length}_bytes"

        text_ratio = (len(text) / raw_length) if raw_length > 0 else 0.0
        if text_ratio < self.min_text_ratio and word_count < 40:
            return True, f"low_text_ratio:{text_ratio:.4f}"

        return False, "sufficient_http_content"
