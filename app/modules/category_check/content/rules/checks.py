"""
Flat 13-rule Content check implementations.

Each rule is self-contained: defines slug ``rule_id``, ``name``, optional
``severity`` override, and ``evaluate(data) -> list[RuleResult]``.

Reuses BaseRule from core_seo.rules.base — content rules subclass the same
base class to benefit from the shared _result helper and fault-tolerant
pipeline behavior.
"""
from __future__ import annotations

import re
from typing import Any

from app.modules.category_check.core_seo.models import Severity
from .base import BaseRule


# ── Content Quality ─────────────────────────────────────────────────────


class TextToHTMLRatioRule(BaseRule):
    rule_id = "text_html_ratio"
    name = "Text to HTML Ratio"

    MIN_RATIO = 0.15

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        ratio = data.get("text_to_html_ratio", 0.0)
        if ratio is None:
            ratio = 0.0
        if not isinstance(ratio, (int, float)):
            ratio = 0.0
        if ratio >= self.MIN_RATIO:
            return [self._result(
                passed=True,
                message=f"Text-to-HTML ratio is {ratio:.1%} (good, above {self.MIN_RATIO:.0%} threshold)",
                severity=Severity.PASSED.value,
                details={"ratio": ratio, "threshold": self.MIN_RATIO},
            )]
        return [self._result(
            passed=False,
            message=f"Text-to-HTML ratio is {ratio:.1%} (too low, recommended: ≥{self.MIN_RATIO:.0%}) — page may be too heavy with markup",
            severity=Severity.WARNING.value,
            recommendation="Reduce HTML overhead and add more visible content text.",
            details={"ratio": ratio, "threshold": self.MIN_RATIO},
        )]


class ContentWordCountRule(BaseRule):
    rule_id = "content_word_count"
    name = "Content Word Count"

    RECOMMENDED_MIN = 300

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        word_count = data.get("word_count", data.get("char_count", 0) or 0)
        if not isinstance(word_count, int):
            word_count = 0
        if word_count >= self.RECOMMENDED_MIN:
            return [self._result(
                passed=True,
                message=f"Content has {word_count} words (sufficient for SEO)",
                severity=Severity.PASSED.value,
                details={"word_count": word_count, "threshold": self.RECOMMENDED_MIN},
            )]
        if word_count >= self.RECOMMENDED_MIN // 3:
            return [self._result(
                passed=False,
                message=f"Content has only {word_count} words (too short, recommended: ≥{self.RECOMMENDED_MIN})",
                severity=Severity.WARNING.value,
                recommendation="Add more content to reach at least 300 words.",
                details={"word_count": word_count, "threshold": self.RECOMMENDED_MIN},
            )]
        return [self._result(
            passed=False,
            message=f"Content has only {word_count} words (very short, recommended: ≥{self.RECOMMENDED_MIN})",
            severity=Severity.CRITICAL.value,
            recommendation="Significantly expand content to at least 300 words.",
            details={"word_count": word_count, "threshold": self.RECOMMENDED_MIN},
        )]


class LinkDensityRule(BaseRule):
    rule_id = "link_density"
    name = "Link Density"

    MAX_DENSITY = 0.5

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        links = data.get("links", [])
        content_text = data.get("content_text", "")
        if not content_text:
            return [self._result(
                passed=True,
                message="No content text to evaluate link density",
                severity=Severity.INFO.value,
            )]
        link_text = " ".join(l.get("text", "") for l in links if isinstance(l, dict))
        if not link_text:
            return [self._result(
                passed=True,
                message="No link text found — link density is 0%",
                severity=Severity.PASSED.value,
                details={"density": 0.0},
            )]
        content_chars = len(content_text)
        link_chars = len(link_text)
        if content_chars == 0:
            density = 0.0
        else:
            density = round(link_chars / content_chars, 4)
        if density <= self.MAX_DENSITY:
            return [self._result(
                passed=True,
                message=f"Link density is {density:.1%} (within acceptable range)",
                severity=Severity.PASSED.value,
                details={"density": density, "threshold": self.MAX_DENSITY},
            )]
        return [self._result(
            passed=False,
            message=f"Link density is {density:.1%} (too high, recommended: ≤{self.MAX_DENSITY:.0%}) — page may be over-linked",
            severity=Severity.WARNING.value,
            recommendation="Reduce the amount of link text relative to total content.",
            details={"density": density, "link_chars": link_chars, "content_chars": content_chars},
        )]


class ContentReadingLevelRule(BaseRule):
    rule_id = "reading_level"
    name = "Content Reading Level"

    MAX_GRADE = 10.0

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        grade = data.get("reading_grade")
        if grade is None or not isinstance(grade, (int, float)):
            return [self._result(
                passed=True,
                message="Reading grade not available — insufficient content for analysis",
                severity=Severity.INFO.value,
            )]
        if grade <= self.MAX_GRADE:
            return [self._result(
                passed=True,
                message=f"Reading grade level is {grade} (accessible, ≤{self.MAX_GRADE:.0f})",
                severity=Severity.PASSED.value,
                details={"reading_grade": grade, "threshold": self.MAX_GRADE},
            )]
        return [self._result(
            passed=False,
            message=f"Reading grade level is {grade} (too complex, recommended: ≤{self.MAX_GRADE:.0f}) — content may be too difficult to read",
            severity=Severity.WARNING.value,
            recommendation="Simplify sentence structure and use shorter, more common words.",
            details={"reading_grade": grade, "threshold": self.MAX_GRADE},
        )]


class KeywordStuffingRule(BaseRule):
    rule_id = "keyword_stuffing"
    name = "Keyword Stuffing Detection"

    MAX_DENSITY = 0.05

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        density = data.get("keyword_density", {})
        if not density or not isinstance(density, dict):
            return [self._result(
                passed=True,
                message="No keyword density data available — no keyword meta tag defined",
                severity=Severity.INFO.value,
            )]
        stuffed = {kw: d for kw, d in density.items() if d > self.MAX_DENSITY}
        if not stuffed:
            max_kw = max(density.items(), key=lambda x: x[1]) if density else ("", 0.0)
            return [self._result(
                passed=True,
                message=f"Keyword density is within limits (max: {max_kw[0]} at {max_kw[1]:.1%})",
                severity=Severity.PASSED.value,
                details={"keyword_density": density, "threshold": self.MAX_DENSITY},
            )]
        return [self._result(
            passed=False,
            message=f"Keyword stuffing detected: {', '.join(f'{kw} ({d:.1%})' for kw, d in stuffed.items())} exceeds {self.MAX_DENSITY:.1%} threshold",
            severity=Severity.WARNING.value,
            recommendation="Distribute keywords naturally; reduce repetition.",
            details={"stuffed_keywords": stuffed, "all_density": density},
        )]


# ── Heading Analysis ─────────────────────────────────────────────────────


class HeadingHierarchyRule(BaseRule):
    rule_id = "heading_hierarchy"
    name = "Heading Hierarchy"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        hierarchy = data.get("heading_hierarchy", [])
        if not hierarchy:
            return [self._result(
                passed=False,
                message="No headings found — content lacks structure",
                severity=Severity.WARNING.value,
                recommendation="Add headings (H1, H2, H3) to structure your content.",
                details={"hierarchy": []},
            )]
        if hierarchy[0] != 1:
            return [self._result(
                passed=False,
                message=f"First heading is H{hierarchy[0]} — should start with H1",
                severity=Severity.WARNING.value,
                recommendation="Start the page's heading structure with an H1 tag.",
                details={"hierarchy": hierarchy, "first_level": hierarchy[0]},
            )]
        for i in range(1, len(hierarchy)):
            if hierarchy[i] > hierarchy[i - 1] + 1:
                return [self._result(
                    passed=False,
                    message=f"Heading hierarchy skips from H{hierarchy[i - 1]} to H{hierarchy[i]} — should use consecutive levels",
                    severity=Severity.WARNING.value,
                    recommendation="Use consecutive heading levels (H2 under H1, H3 under H2, etc.).",
                    details={"hierarchy": hierarchy, "skip_at": i},
                )]
        return [self._result(
            passed=True,
            message=f"Heading hierarchy is well-structured: {hierarchy}",
            severity=Severity.PASSED.value,
            details={"hierarchy": hierarchy},
        )]


class HeadingLengthRule(BaseRule):
    rule_id = "heading_length"
    name = "Heading Length"

    MAX_LENGTH = 60

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        headings = data.get("headings", {})
        if not headings:
            return [self._result(
                passed=True,
                message="No headings found",
                severity=Severity.INFO.value,
            )]
        heading_lengths = data.get("heading_lengths", {})
        long_headings = []
        for level, texts in headings.items():
            if not texts:
                continue
            max_len = heading_lengths.get(level, 0)
            if max_len > self.MAX_LENGTH:
                long_headings.append({
                    "level": level,
                    "max_length": max_len,
                    "sample": texts[0][:100],
                })
        if not long_headings:
            return [self._result(
                passed=True,
                message="All headings are within recommended length (≤60 chars)",
                severity=Severity.PASSED.value,
                details={"max_lengths": heading_lengths},
            )]
        return [self._result(
            passed=False,
            message=f"Some headings exceed {self.MAX_LENGTH} characters: {', '.join(h['level'] for h in long_headings)}",
            severity=Severity.WARNING.value,
            recommendation="Keep headings under 60 characters for better readability and SEO.",
            details={"long_headings": long_headings},
        )]


class TitleH1DuplicationRule(BaseRule):
    rule_id = "title_h1_duplication"
    name = "Title-H1 Duplication"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        title = (data.get("title") or "").strip()
        headings = data.get("headings", {})
        h1_texts = headings.get("h1", []) if isinstance(headings, dict) else []
        if not title:
            return [self._result(
                passed=False,
                message="Page is missing a <title> tag",
                severity=Severity.WARNING.value,
                recommendation="Add a <title> tag to the page.",
            )]
        if not h1_texts:
            return [self._result(
                passed=True,
                message="No H1 tag found — cannot check duplication",
                severity=Severity.INFO.value,
            )]
        h1 = h1_texts[0].strip()
        # Exact or near-duplicate check (case-insensitive, whitespace-normalized)
        title_norm = re.sub(r"\s+", " ", title.lower())
        h1_norm = re.sub(r"\s+", " ", h1.lower())
        if title_norm == h1_norm:
            return [self._result(
                passed=False,
                message=f"Title and H1 are identical: \"{title[:80]}\" — they should differ to avoid redundancy",
                severity=Severity.WARNING.value,
                recommendation="Make the title tag and H1 heading complementary, not identical.",
                details={"title": title, "h1": h1},
            )]
        return [self._result(
            passed=True,
            message="Title and H1 are distinct (good)",
            severity=Severity.PASSED.value,
            details={"title_preview": title[:80], "h1_preview": h1[:80]},
        )]


# ── Pixel Width Analysis ─────────────────────────────────────────────────


class TitlePixelWidthRule(BaseRule):
    rule_id = "title_pixel_width"
    name = "Title Pixel Width"

    PIXEL_LIMIT = 580

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        title = (data.get("title") or "").strip()
        if not title:
            return [self._result(
                passed=False,
                message="Page is missing a <title> tag — cannot evaluate pixel width",
                severity=Severity.INFO.value,
                recommendation="Add a <title> tag first.",
            )]
        pixel_width = data.get("title_pixel_width")
        if pixel_width is None:
            pixel_width = len(title) * 8
        if pixel_width <= self.PIXEL_LIMIT:
            return [self._result(
                passed=True,
                message=f"Title pixel width is {pixel_width}px (within {self.PIXEL_LIMIT}px limit)",
                severity=Severity.PASSED.value,
                details={"pixel_width": pixel_width, "limit": self.PIXEL_LIMIT, "char_count": len(title)},
            )]
        return [self._result(
            passed=False,
            message=f"Title pixel width is {pixel_width}px (exceeds {self.PIXEL_LIMIT}px limit — may be truncated in SERPs)",
            severity=Severity.WARNING.value,
            recommendation="Shorten the title tag to stay under 580 pixels (~72 characters).",
            details={"pixel_width": pixel_width, "limit": self.PIXEL_LIMIT, "char_count": len(title)},
        )]


class MetaDescriptionPixelWidthRule(BaseRule):
    rule_id = "meta_desc_pixel_width"
    name = "Meta Description Pixel Width"

    PIXEL_LIMIT = 920

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        desc = (data.get("description") or "").strip()
        if not desc:
            return [self._result(
                passed=False,
                message="Page is missing a meta description — cannot evaluate pixel width",
                severity=Severity.INFO.value,
                recommendation="Add a <meta name='description'> tag first.",
            )]
        pixel_width = data.get("meta_description_pixel_width")
        if pixel_width is None:
            pixel_width = len(desc) * 7
        if pixel_width <= self.PIXEL_LIMIT:
            return [self._result(
                passed=True,
                message=f"Meta description pixel width is {pixel_width}px (within {self.PIXEL_LIMIT}px limit)",
                severity=Severity.PASSED.value,
                details={"pixel_width": pixel_width, "limit": self.PIXEL_LIMIT, "char_count": len(desc)},
            )]
        return [self._result(
            passed=False,
            message=f"Meta description pixel width is {pixel_width}px (exceeds {self.PIXEL_LIMIT}px limit — may be truncated in SERPs)",
            severity=Severity.WARNING.value,
            recommendation="Shorten the meta description to stay under 920 pixels (~131 characters).",
            details={"pixel_width": pixel_width, "limit": self.PIXEL_LIMIT, "char_count": len(desc)},
        )]


# ── HTML Structure ───────────────────────────────────────────────────────


class BrokenHTMLStructureRule(BaseRule):
    rule_id = "html_structure"
    name = "HTML Structure Validation"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        errors = data.get("html_structure_errors", [])
        if not errors:
            return [self._result(
                passed=True,
                message="HTML structure is valid — no structural errors detected",
                severity=Severity.PASSED.value,
                details={"errors": []},
            )]
        return [self._result(
            passed=False,
            message=f"HTML structure issues detected ({len(errors)}): {'; '.join(errors)}",
            severity=Severity.WARNING.value,
            recommendation="Fix the reported HTML structure issues to improve rendering and accessibility.",
            details={"errors": errors, "error_count": len(errors)},
        )]


class MetaTagsInBodyRule(BaseRule):
    rule_id = "meta_in_body"
    name = "Meta Tags in Body"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        meta_in_body = data.get("meta_tags_in_body", [])
        if not meta_in_body:
            return [self._result(
                passed=True,
                message="No <meta> tags found in <body> (correct placement)",
                severity=Severity.PASSED.value,
                details={"count": 0},
            )]
        return [self._result(
            passed=False,
            message=f"{len(meta_in_body)} <meta> tag(s) found in <body> — meta tags should only appear in <head>",
            severity=Severity.WARNING.value,
            recommendation="Move <meta> tags from <body> to <head>.",
            details={"count": len(meta_in_body), "tags": meta_in_body[:5]},
        )]


class ContentMimeTypeRule(BaseRule):
    rule_id = "content_mime_type"
    name = "Content MIME Type"

    EXPECTED_TYPE = "text/html"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        content_type = data.get("content_type", "")
        status_code = data.get("status_code")
        if not content_type:
            return [self._result(
                passed=True,
                message="No Content-Type header available for analysis",
                severity=Severity.INFO.value,
            )]
        ct_lower = content_type.lower().strip()
        if ct_lower.startswith(self.EXPECTED_TYPE):
            return [self._result(
                passed=True,
                message=f"Content-Type is {content_type} (correct for HTML pages)",
                severity=Severity.PASSED.value,
                details={"content_type": content_type},
            )]
        if status_code and status_code in (301, 302, 303, 307, 308):
            return [self._result(
                passed=True,
                message=f"Redirect response ({status_code}) with Content-Type '{content_type}' — content-type not applicable to redirects",
                severity=Severity.PASSED.value,
                details={"content_type": content_type, "status_code": status_code},
            )]
        return [self._result(
            passed=False,
            message=f"Content-Type is '{content_type}' (expected '{self.EXPECTED_TYPE}') — page may not be served as HTML",
            severity=Severity.WARNING.value,
            recommendation="Ensure the server returns Content-Type: text/html; charset=utf-8 for HTML pages.",
            details={"content_type": content_type, "expected": self.EXPECTED_TYPE, "status_code": status_code},
        )]


__all__ = [
    "BrokenHTMLStructureRule",
    "ContentMimeTypeRule",
    "ContentReadingLevelRule",
    "ContentWordCountRule",
    "HeadingHierarchyRule",
    "HeadingLengthRule",
    "KeywordStuffingRule",
    "LinkDensityRule",
    "MetaDescriptionPixelWidthRule",
    "MetaTagsInBodyRule",
    "TextToHTMLRatioRule",
    "TitleH1DuplicationRule",
    "TitlePixelWidthRule",
]
