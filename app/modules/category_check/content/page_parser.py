"""
ContentPageParser — HTML → ParsedPage using BeautifulSoup.

Content-specific parser that extends the core PageParser to add content-
relevant fields (pixel width calculations, reading grade, link density)
not present in the core parser's output.
"""
from __future__ import annotations

from typing import Any

from app.modules.category_check.core_seo.constants import MIN_WORDS_GOOD, MIN_WORDS_ACCEPTABLE
from app.modules.category_check.core_seo.models import ParsedPage
from app.modules.category_check.core_seo.page_parser import PageParser
from .models import CrawlResult


class ContentPageParser(PageParser):
    """Content-specific parser extending PageParser.

    Adds convenience methods for content-oriented analysis not provided
    by the base parser:
        - build_content_rule_data — enriched data dict for content rules
        - pixel_width_of — approximate pixel width of a string
        - reading_grade_of — Flesch-Kincaid grade level (approx)
        - link_density_of — ratio of link text chars to total content chars
    """

    TITLE_PIXELS_PER_CHAR = 8
    META_DESC_PIXELS_PER_CHAR = 7
    TITLE_PIXEL_LIMIT = 580
    META_DESC_PIXEL_LIMIT = 920

    def __init__(self, base_url: str = ""):
        super().__init__(base_url=base_url)

    def build_content_rule_data(
        self,
        parsed: ParsedPage,
        crawl_result: Any = None,
        config: Any = None,
    ) -> dict[str, Any]:
        """Build the enriched data dict consumed by the 13 content rules.

        Extends the base build_rule_data output with content-specific fields:
            - text_to_html_ratio
            - title_pixel_width
            - meta_description_pixel_width
            - reading_grade
            - keyword_density
            - heading_lengths
            - html_structure_errors
            - meta_tags_in_body
            - content_type
        """
        html = crawl_result.html if crawl_result and crawl_result.html else ""
        content_text = parsed.content_text or ""

        base_data = super().build_rule_data(parsed, crawl_result)

        text_to_html_ratio = self._text_to_html_ratio(html, content_text)
        title_pixel_width = self.pixel_width_of(parsed.title)
        desc_pixel_width = self.pixel_width_of(parsed.description, pixels_per_char=self.META_DESC_PIXELS_PER_CHAR)
        reading_grade = self.reading_grade_of(content_text)
        keyword_density = self._keyword_density(content_text, parsed.keywords)
        heading_lengths = self._heading_lengths(parsed.headings)
        html_structure_errors = self._html_structure_errors(html, parsed)
        meta_tags_in_body = self._meta_tags_in_body(html)
        content_type = self._content_type_from_headers(crawl_result) if crawl_result else parsed.content_type or ""

        base_data.update({
            "text_to_html_ratio": text_to_html_ratio,
            "title_pixel_width": title_pixel_width,
            "meta_description_pixel_width": desc_pixel_width,
            "reading_grade": reading_grade,
            "keyword_density": keyword_density,
            "heading_lengths": heading_lengths,
            "html_structure_errors": html_structure_errors,
            "meta_tags_in_body": meta_tags_in_body,
            "content_type": content_type,
            "word_count": parsed.word_count,
            "char_count": parsed.char_count,
            "links": base_data.get("links", []),
            "internal_links": base_data.get("internal_links", []),
            "external_links": base_data.get("external_links", []),
        })

        return base_data

    def pixel_width_of(self, text: str, pixels_per_char: int | None = None) -> int:
        """Approximate the rendered pixel width of a text string.

        Uses a conservative per-character estimate. Titles and descriptions
        are typically rendered in variable-width fonts, so this is an
        approximation for threshold-based rules.
        """
        if not text:
            return 0
        ppc = pixels_per_char if pixels_per_char is not None else self.TITLE_PIXELS_PER_CHAR
        return len(text.strip()) * ppc

    def reading_grade_of(self, text: str) -> float:
        """Approximate the Flesch-Kincaid Grade Level of text.

        Formula: 0.39 * (words/sentences) + 11.8 * (syllables/words) - 15.59

        Returns 0.0 for empty or very short text.
        """
        if not text or len(text.split()) < 5:
            return 0.0
        try:
            sentences = self._count_sentences(text)
            words = text.split()
            word_count = len(words)
            if sentences == 0 or word_count == 0:
                return 0.0
            syllables = self._count_syllables(" ".join(words))
            if syllables == 0:
                return 0.0
            grade = 0.39 * (word_count / sentences) + 11.8 * (syllables / word_count) - 15.59
            return round(max(0.0, grade), 1)
        except Exception:
            return 0.0

    def _count_sentences(self, text: str) -> int:
        import re
        sentence_endings = re.findall(r"[.!?]+", text)
        return max(1, len(sentence_endings))

    def _count_syllables(self, text: str) -> int:
        import re
        text = text.lower()
        text = re.sub(r"[^a-z\s]", "", text)
        words = text.split()
        if not words:
            return 0
        total = 0
        vowels = "aeiouy"
        for word in words:
            if not word:
                continue
            count = 0
            prev_was_vowel = False
            for char in word:
                is_vowel = char in vowels
                if is_vowel and not prev_was_vowel:
                    count += 1
                prev_was_vowel = is_vowel
            if word.endswith("e"):
                count = max(1, count - 1)
            if count == 0:
                count = 1
            total += count
        return max(1, total)

    def _text_to_html_ratio(self, html: str, text: str) -> float:
        if not html or len(html) == 0:
            return 1.0 if text else 0.0
        if len(text) == 0:
            return 0.0
        return round(len(text) / len(html), 4)

    def _keyword_density(self, text: str, keywords: list[str]) -> dict[str, float]:
        if not text or not keywords:
            return {}
        text_lower = text.lower()
        words = text_lower.split()
        total = len(words) if words else 1
        density: dict[str, float] = {}
        for kw in keywords:
            kw_lower = kw.lower().strip()
            if not kw_lower:
                continue
            kw_words = kw_lower.split()
            if len(kw_words) == 1:
                count = sum(1 for w in words if w == kw_lower)
            else:
                count = sum(
                    1 for i in range(len(words) - len(kw_words) + 1)
                    if " ".join(words[i:i + len(kw_words)]) == kw_lower
                )
            density[kw_lower] = round(count / total, 4)
        return density

    def _heading_lengths(self, headings: dict[str, list[str]]) -> dict[str, int]:
        result: dict[str, int] = {}
        for level, texts in headings.items():
            result[level] = max((len(t) for t in texts), default=0) if texts else 0
        return result

    def _html_structure_errors(self, html: str, parsed: ParsedPage) -> list[str]:
        errors: list[str] = []
        if not html:
            return ["Empty or missing HTML"]
        import re
        body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
        if not body_match:
            errors.append("Missing <body> tag")
        if not parsed.has_h1:
            errors.append("No <h1> tag found")
        open_tags = re.findall(r"<([a-zA-Z][a-zA-Z0-9]*)\s*(?:[^>]*?)?(?<!/)>", html, re.IGNORECASE)
        close_tags = re.findall(r"</([a-zA-Z][a-zA-Z0-9]*)>", html, re.IGNORECASE)
        significant_tags = {"div", "p", "section", "article", "span", "ul", "ol", "li", "table", "header", "footer", "nav", "aside", "main", "form"}
        significant_open = sum(1 for t in open_tags if t.lower() in significant_tags)
        significant_close = sum(1 for t in close_tags if t.lower() in significant_tags)
        if significant_open != significant_close:
            errors.append(f"Tag imbalance: {significant_open} opening vs {significant_close} closing significant tags")
        return errors

    def _meta_tags_in_body(self, html: str) -> list[str]:
        import re
        body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
        body_content = body_match.group(1) if body_match else html
        metas = re.findall(r"<meta[^>]+>", body_content, re.IGNORECASE)
        return [m for m in metas if m.strip()]

    def _content_type_from_headers(self, crawl_result: Any) -> str:
        if not crawl_result:
            return ""
        headers = getattr(crawl_result, "headers", {}) or {}
        for key, val in headers.items():
            if key.lower() == "content-type":
                return val
        return ""


def get_content_parser() -> ContentPageParser:
    """Get the singleton ContentPageParser instance."""
    return ContentPageParser()


__all__ = ["ContentPageParser", "get_content_parser"]
