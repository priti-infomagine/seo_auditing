"""
RenderDetector - Heuristics to decide if Playwright browser rendering is required.

Performs only lightweight rendering-sufficiency checks:
- Empty application shells (root/app/__next/__nuxt with no meaningful text)
- Loading placeholders
- Extremely low text density (likely JS-dependent shell)

Does NOT evaluate SEO quality (missing title, H1, meta description, etc.).
SEO parsing stays in the BeautifulSoup parser layer.
"""
import re
from bs4 import BeautifulSoup
from typing import Dict, List

from app.modules.crawler.types import FetchResult, RenderDecision

SPA_ROOT_TAGS = [
    '<div id="root"></div>',
    '<div id="app"></div>',
    '<app-root></app-root>',
    '<div id="__next"></div>',
    '<div id="__nuxt"></div>',
]

LOADING_PATTERN = re.compile(
    r"^\s*(loading\.{0,3}|please wait|initializing|redirecting)\s*$",
    re.IGNORECASE,
)


class RenderDetector:
    """Detects if an HTTP response is an empty/JS-dependent shell requiring browser rendering."""

    def __init__(
        self,
        min_word_count: int = 10,
        min_text_ratio: float = 0.01,
    ):
        self.min_word_count = min_word_count
        self.min_text_ratio = min_text_ratio

    def evaluate(self, fetch_result: FetchResult) -> RenderDecision:
        """
        Determine whether the initial HTML is sufficient for SEO analysis
        or if browser rendering is required.

        Returns:
            RenderDecision with needs_render flag and reason.
        """
        if not fetch_result.success or not fetch_result.content:
            return RenderDecision(False, "http_fetch_failed")

        content_type = fetch_result.content_type or ""
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return RenderDecision(False, "not_html")

        html_text = fetch_result.content.decode("utf-8", errors="ignore")

        # Check for empty application shells
        shell_tags = _find_shell_tags(html_text)
        if shell_tags and _is_empty_shell(html_text):
            return RenderDecision(True, "application_shell", {"shell_tags": shell_tags})

        # Check for loading placeholders
        if _contains_loading_placeholder(html_text):
            return RenderDecision(True, "loading_placeholder")

        # Lightweight text-density check using BS4 (does NOT extract SEO data)
        try:
            soup = BeautifulSoup(html_text, "html.parser")
        except Exception:
            return RenderDecision(False, "parse_error")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        visible_text = soup.get_text(" ", strip=True)
        words = re.findall(r"\b\w+\b", visible_text)
        word_count = len(words)
        text_ratio = (len(visible_text) / len(html_text)) if html_text else 0.0

        if word_count < self.min_word_count and text_ratio < self.min_text_ratio:
            return RenderDecision(
                True,
                "low_content",
                {"word_count": word_count, "text_ratio": text_ratio},
            )

        return RenderDecision(
            False,
            "initial_html_sufficient",
            {"word_count": word_count, "text_ratio": text_ratio},
        )

    def needs_browser_render(self, fetch_result: FetchResult) -> tuple:
        """Backward-compatible wrapper around evaluate()."""
        decision = self.evaluate(fetch_result)
        return decision.needs_render, decision.reason


def _find_shell_tags(html: str) -> List[str]:
    """Return list of known SPA shell tag signatures found in raw HTML."""
    found = []
    for tag in SPA_ROOT_TAGS:
        if tag in html:
            found.append(tag)
    return found


def _is_empty_shell(html: str) -> bool:
    """Check if the page contains almost no meaningful text content."""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return False

    for tag in soup(["script", "style", "noscript", "svg", "canvas"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    words = re.findall(r"\b\w+\b", text)
    return len(words) < 5


def _contains_loading_placeholder(html: str) -> bool:
    """Check for obvious loading/initialization placeholder text."""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return False

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    return bool(LOADING_PATTERN.match(text))
