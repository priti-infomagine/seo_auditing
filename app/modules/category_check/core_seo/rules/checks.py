"""
Flat 18-rule SEO check implementations.

Each rule is self-contained: defines slug ``rule_id``, ``name``, optional
``severity`` override, and ``evaluate(data) -> list[RuleResult]``.
No category/weight/tags/score_impact — those concepts are removed.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from ..models import Severity
from ..url_normalizer import URLNormalizer
from .base import BaseRule


# ── Title ────────────────────────────────────────────────────────────────

class TitleTagPresentRule(BaseRule):
    rule_id = "title_present"
    name = "Title Tag Present"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        title = (data.get("title") or "").strip()
        if not title:
            return [self._result(
                passed=False,
                message="Page is missing a <title> tag",
                severity=Severity.WARNING.value,
                recommendation="Add a unique, descriptive <title> tag to the page.",
            )]
        return [self._result(
            passed=True,
            message=f'Title tag found: "{title[:80]}"',
            severity=Severity.PASSED.value,
            details={"title": title, "character_count": len(title)},
        )]


class TitleTagLengthRule(BaseRule):
    rule_id = "title_length"
    name = "Title Tag Length"

    RECOMMENDED_MIN = 30
    RECOMMENDED_MAX = 60

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        title = (data.get("title") or "").strip()
        title_length = len(title)
        if not title:
            return [self._result(
                passed=False,
                message="Page is missing a <title> tag, cannot evaluate length",
                severity=Severity.INFO.value,
                recommendation="Add a <title> tag first.",
            )]
        if title_length < self.RECOMMENDED_MIN:
            return [self._result(
                passed=False,
                message=f"Title length is {title_length} characters (too short, recommended: {self.RECOMMENDED_MIN}-{self.RECOMMENDED_MAX})",
                severity=Severity.WARNING.value,
                recommendation=f"Make the title at least {self.RECOMMENDED_MIN} characters.",
                details={"length": title_length},
            )]
        if title_length > self.RECOMMENDED_MAX:
            return [self._result(
                passed=False,
                message=f"Title length is {title_length} characters (too long, recommended: {self.RECOMMENDED_MIN}-{self.RECOMMENDED_MAX})",
                severity=Severity.WARNING.value,
                recommendation="Shorten the title to 30-60 characters to avoid SERP truncation.",
                details={"length": title_length},
            )]
        return [self._result(
            passed=True,
            message=f"Title length is {title_length} characters (good)",
            severity=Severity.PASSED.value,
            details={"length": title_length},
        )]


# ── Meta Description ─────────────────────────────────────────────────────

class MetaDescriptionPresentRule(BaseRule):
    rule_id = "meta_description_present"
    name = "Meta Description Present"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        desc = (data.get("description") or "").strip()
        if not desc:
            return [self._result(
                passed=False,
                message="Page is missing a <meta name='description'> tag",
                severity=Severity.WARNING.value,
                recommendation="Add a <meta name='description'> tag to the page.",
            )]
        return [self._result(
            passed=True,
            message=f"Meta description found ({len(desc)} characters)",
            severity=Severity.PASSED.value,
            details={"length": len(desc)},
        )]


class MetaDescriptionLengthRule(BaseRule):
    rule_id = "meta_description_length"
    name = "Meta Description Length"

    RECOMMENDED_MIN = 120
    RECOMMENDED_MAX = 160

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        desc = (data.get("description") or "").strip()
        desc_length = len(desc)
        if not desc:
            return [self._result(
                passed=False,
                message="Missing meta description",
                severity=Severity.INFO.value,
                recommendation="Add a meta description first.",
            )]
        if desc_length < self.RECOMMENDED_MIN:
            return [self._result(
                passed=False,
                message=f"Meta description length is {desc_length} characters (too short, recommended: {self.RECOMMENDED_MIN}-{self.RECOMMENDED_MAX})",
                severity=Severity.WARNING.value,
                recommendation=f"Make the description at least {self.RECOMMENDED_MIN} characters.",
                details={"length": desc_length},
            )]
        if desc_length > self.RECOMMENDED_MAX:
            return [self._result(
                passed=False,
                message=f"Meta description length is {desc_length} characters (too long, recommended: {self.RECOMMENDED_MIN}-{self.RECOMMENDED_MAX})",
                severity=Severity.WARNING.value,
                recommendation="Shorten the description to avoid SERP truncation.",
                details={"length": desc_length},
            )]
        return [self._result(
            passed=True,
            message=f"Meta description length is {desc_length} characters (good)",
            severity=Severity.PASSED.value,
            details={"length": desc_length},
        )]


# ── Headings ──────────────────────────────────────────────────────────────

class H1TagPresentRule(BaseRule):
    rule_id = "h1_present"
    name = "H1 Tag Present"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        heading_counts = data.get("heading_counts", {})
        h1_count = heading_counts.get("h1", 0) if heading_counts else 0
        h1_text = ""
        headings = data.get("headings", {})
        if headings and "h1" in headings:
            h1_list = headings["h1"]
            if h1_list:
                h1_text = h1_list[0]
        if h1_count == 0:
            return [self._result(
                passed=False,
                message="Page is missing an <h1> tag",
                severity=Severity.WARNING.value,
                recommendation="Add a single <h1> tag that describes the page's main topic.",
            )]
        return [self._result(
            passed=True,
            message=f'H1 tag found: "{h1_text[:80]}"',
            severity=Severity.PASSED.value,
            details={"h1_count": h1_count, "h1_text": h1_text[:200]},
        )]


class SingleH1TagRule(BaseRule):
    rule_id = "single_h1"
    name = "Single H1 Tag"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        heading_counts = data.get("heading_counts", {})
        h1_count = heading_counts.get("h1", 0) if heading_counts else 0
        if h1_count == 0:
            return [self._result(
                passed=False,
                message="Page does not have an <h1> tag",
                severity=Severity.WARNING.value,
                recommendation="Add exactly one <h1> tag.",
            )]
        if h1_count > 1:
            return [self._result(
                passed=False,
                message=f"Multiple <h1> tags found ({h1_count}) — pages should have exactly one H1 for clear heading hierarchy",
                severity=Severity.WARNING.value,
                recommendation="Use only one <h1> tag per page; use <h2>, <h3>, etc. for subheadings.",
                details={"h1_count": h1_count},
            )]
        return [self._result(
            passed=True,
            message="Page has exactly one <h1> tag (good)",
            severity=Severity.PASSED.value,
            details={"h1_count": h1_count},
        )]


# ── Canonical ────────────────────────────────────────────────────────────

class CanonicalURLPresentRule(BaseRule):
    rule_id = "canonical_present"
    name = "Canonical URL Present"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        canonical = (data.get("canonical") or "").strip()
        if not canonical:
            return [self._result(
                passed=False,
                message="Page is missing a <link rel='canonical'> tag",
                severity=Severity.WARNING.value,
                recommendation="Add <link rel='canonical' href='...'> to specify the preferred URL.",
            )]
        return [self._result(
            passed=True,
            message=f"Canonical URL found: {canonical}",
            severity=Severity.PASSED.value,
            details={"canonical": canonical},
        )]


class CanonicalURLValidRule(BaseRule):
    rule_id = "canonical_valid"
    name = "Canonical URL Valid"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        canonical = (data.get("canonical") or "").strip()
        if not canonical:
            return [self._result(
                passed=False,
                message="No canonical tag found",
                severity=Severity.INFO.value,
                recommendation="Add a canonical URL tag first.",
            )]
        try:
            normalized = URLNormalizer.normalize_url(canonical)
            parts = urlsplit(normalized)
            if parts.scheme in ("http", "https") and parts.netloc:
                return [self._result(
                    passed=True,
                    message=f"Canonical URL is valid: {normalized}",
                    severity=Severity.PASSED.value,
                    details={"canonical": normalized},
                )]
        except (ValueError, Exception):
            pass
        return [self._result(
            passed=False,
            message=f"Canonical URL is invalid: {canonical}",
            severity=Severity.WARNING.value,
            recommendation="Fix the canonical URL to be a valid absolute http/https URL.",
            details={"canonical": canonical},
        )]


class CanonicalLoopDetectionRule(BaseRule):
    rule_id = "canonical_loop"
    name = "Canonical Loop Detection"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        canonical = (data.get("canonical") or "").strip()
        page_url = data.get("url", "")
        if not canonical:
            return [self._result(
                passed=True,
                message="No canonical specified (nothing to loop)",
                severity=Severity.INFO.value,
            )]
        try:
            canonical_norm = URLNormalizer.normalize_url(canonical)
            page_norm = URLNormalizer.normalize_url(page_url)
        except (ValueError, Exception):
            canonical_norm = canonical.lower()
            page_norm = page_url.lower()
        if canonical_norm == page_norm:
            return [self._result(
                passed=True,
                message="Canonical URL points to the correct page (no loop detected)",
                severity=Severity.PASSED.value,
            )]
        return [self._result(
            passed=False,
            message=f"Canonical URL ({canonical}) points to a different location than the page URL (potential loop risk)",
            severity=Severity.WARNING.value,
            recommendation="Ensure canonical points to the page's own URL.",
            details={"canonical": canonical, "page_url": page_url},
        )]


class CanonicalHeaderValidationRule(BaseRule):
    rule_id = "canonical_header"
    name = "Canonical Header Validation"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        source_count = data.get("canonical_source_count", 0)
        canonical = data.get("canonical", "")
        if not canonical:
            return [self._result(
                passed=True,
                message="No canonical specified",
                severity=Severity.INFO.value,
            )]
        if source_count == 1:
            return [self._result(
                passed=True,
                message=f"Canonical URL found via single source ({source_count} source)",
                severity=Severity.PASSED.value,
                details={"source_count": source_count},
            )]
        return [self._result(
            passed=False,
            message=f"Multiple canonical sources found ({source_count} sources) — canonical defined both in <link> tag and HTTP header",
            severity=Severity.WARNING.value,
            recommendation="Specify canonical via only one source to avoid ambiguity.",
            details={"source_count": source_count},
        )]


class ConflictingCanonicalURLsRule(BaseRule):
    rule_id = "canonical_conflict"
    name = "Conflicting Canonical URLs"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        source_count = data.get("canonical_source_count", 0)
        if source_count == 0:
            return [self._result(
                passed=True,
                message="No canonical sources found (page does not use canonicalization)",
                severity=Severity.INFO.value,
            )]
        if source_count == 1:
            return [self._result(
                passed=True,
                message=f"At most one canonical source found ({source_count} source)",
                severity=Severity.PASSED.value,
                details={"source_count": source_count},
            )]
        return [self._result(
            passed=False,
            message=f"Conflicting canonical URLs: {source_count} sources found on the same page — search engines cannot determine the preferred URL",
            severity=Severity.WARNING.value,
            recommendation="Keep only one canonical URL source per page.",
            details={"source_count": source_count},
        )]


class CanonicalNotPointingToHomepageRule(BaseRule):
    rule_id = "canonical_not_homepage"
    name = "Canonical Not Pointing to Homepage"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        canonical = (data.get("canonical") or "").strip()
        page_url = data.get("url", "")
        if not canonical:
            return [self._result(
                passed=True,
                message="No canonical tag found (nothing to check)",
                severity=Severity.INFO.value,
            )]
        try:
            canonical_parts = urlsplit(URLNormalizer.normalize_url(canonical))
            page_parts = urlsplit(URLNormalizer.normalize_url(page_url))
        except (ValueError, Exception):
            canonical_parts = urlsplit(canonical)
            page_parts = urlsplit(page_url)
        canonical_path = canonical_parts.path.rstrip("/")
        page_path = page_parts.path.rstrip("/")
        is_homepage = canonical_path == ""
        is_current_page_homepage = page_path == ""
        if is_homepage and is_current_page_homepage:
            return [self._result(
                passed=True,
                message="This is the homepage — canonical correctly points to the homepage",
                severity=Severity.PASSED.value,
            )]
        if is_homepage and not is_current_page_homepage:
            return [self._result(
                passed=False,
                message=f"Canonical URL points to the homepage ({canonical}) from a non-homepage page — this dilutes page-level SEO value",
                severity=Severity.WARNING.value,
                recommendation="Canonical should point to the page's own URL, not the homepage.",
                details={"canonical": canonical, "is_homepage": is_homepage},
            )]
        return [self._result(
            passed=True,
            message=f"Canonical does not point to homepage (path: {canonical_path or '/'})",
            severity=Severity.PASSED.value,
            details={"canonical_path": canonical_path},
        )]


class CanonicalProtocolMatchRule(BaseRule):
    rule_id = "canonical_protocol_match"
    name = "Canonical Protocol Match"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        canonical = (data.get("canonical") or "").strip()
        page_url = data.get("url", "")
        if not canonical:
            return [self._result(
                passed=True,
                message="No canonical specified (nothing to compare)",
                severity=Severity.INFO.value,
            )]
        try:
            canonical_parts = urlsplit(canonical)
            page_parts = urlsplit(page_url)
        except (ValueError, Exception):
            return [self._result(
                passed=True,
                message="Could not compare protocols (invalid URL)",
                severity=Severity.INFO.value,
            )]
        canonical_proto = canonical_parts.scheme.lower()
        page_proto = page_parts.scheme.lower()
        if not canonical_proto:
            canonical_proto = "https"
        if canonical_proto == page_proto:
            return [self._result(
                passed=True,
                message=f"Canonical protocol ({canonical_proto}) matches page protocol",
                severity=Severity.PASSED.value,
                details={"canonical_protocol": canonical_proto, "page_protocol": page_proto},
            )]
        return [self._result(
            passed=False,
            message=f"Canonical protocol ({canonical_proto}) does not match page protocol ({page_proto})",
            severity=Severity.WARNING.value,
            recommendation="Ensure canonical uses the same protocol (http/https) as the page.",
            details={"canonical_protocol": canonical_proto, "page_protocol": page_proto},
        )]


class CanonicalAndNoindexConflictRule(BaseRule):
    rule_id = "canonical_noindex_conflict"
    name = "Canonical and Noindex Conflict"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        canonical = (data.get("canonical") or "").strip()
        robots_meta = (data.get("robots_meta") or "").strip().lower()
        page_url = data.get("url", "")
        has_noindex = "noindex" in robots_meta
        if not has_noindex:
            return [self._result(
                passed=True,
                message="Page does not have noindex directive",
                severity=Severity.PASSED.value,
            )]
        if not canonical:
            return [self._result(
                passed=True,
                message="noindex present but no canonical (no conflict)",
                severity=Severity.INFO.value,
            )]
        try:
            canonical_norm = URLNormalizer.normalize_url(canonical)
            page_norm = URLNormalizer.normalize_url(page_url)
            same_url = canonical_norm == page_norm
        except (ValueError, Exception):
            same_url = canonical.lower() == page_url.lower()
        if same_url:
            return [self._result(
                passed=False,
                message="Page has both a canonical (to itself) and noindex directive — conflicting signals sent to search engines",
                severity=Severity.WARNING.value,
                recommendation="Remove noindex if the page should be indexed, or remove canonical if it should not.",
                details={"canonical": canonical, "robots_meta": robots_meta},
            )]
        return [self._result(
            passed=True,
            message=f"noindex is present with an external canonical URL ({canonical}) — no conflict",
            severity=Severity.INFO.value,
            details={"canonical": canonical, "robots_meta": robots_meta},
        )]


# ── Technical ──────────────────────────────────────────────────────────────

class ViewportMetaTagRule(BaseRule):
    rule_id = "viewport_meta"
    name = "Viewport Meta Tag"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        viewport = (data.get("viewport") or "").strip()
        if not viewport:
            return [self._result(
                passed=False,
                message="Page is missing a viewport meta tag — may not render properly on mobile devices",
                severity=Severity.WARNING.value,
                recommendation="Add <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            )]
        return [self._result(
            passed=True,
            message=f'Viewport meta tag found: "{viewport}"',
            severity=Severity.PASSED.value,
            details={"viewport": viewport},
        )]


class FaviconPresentRule(BaseRule):
    rule_id = "favicon_present"
    name = "Favicon Present"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        favicon_urls: list[str] = data.get("favicon_urls", [])
        if not favicon_urls:
            return [self._result(
                passed=False,
                message="No favicon found",
                severity=Severity.INFO.value,
                recommendation="Add <link rel='icon' href='/favicon.ico'> to the page.",
            )]
        return [self._result(
            passed=True,
            message=f"Favicon(s) found: {len(favicon_urls)} detected — {favicon_urls[0][:80]}",
            severity=Severity.PASSED.value,
            details={"favicon_urls": favicon_urls[:5]},
        )]


class RobotsMetaDirectivesRule(BaseRule):
    rule_id = "robots_meta"
    name = "Robots Meta Directives"

    RESTRICTIVE_DIRECTIVES = {"noindex", "nofollow", "none", "noarchive", "nosnippet", "max-snippet:0"}

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        robots_meta = (data.get("robots_meta") or "").strip().lower()
        if not robots_meta:
            return [self._result(
                passed=True,
                message="No robots meta directives found (page is indexable by default)",
                severity=Severity.PASSED.value,
            )]
        found_directives = []
        for directive in self.RESTRICTIVE_DIRECTIVES:
            if directive in robots_meta:
                found_directives.append(directive)
        if not found_directives:
            return [self._result(
                passed=True,
                message=f"Robots meta present ({robots_meta}) but no restrictive directives found",
                severity=Severity.PASSED.value,
                details={"robots_meta": robots_meta},
            )]
        if "noindex" in found_directives:
            return [self._result(
                passed=False,
                message=f"Restrictive robots directives found ({', '.join(found_directives)}) — page will not be indexed by search engines",
                severity=Severity.WARNING.value,
                recommendation="Remove noindex/nofollow directives if the page should be indexed.",
                details={"directives": found_directives, "robots_meta": robots_meta},
            )]
        return [self._result(
            passed=False,
            message=f"Restrictive robots directives found ({', '.join(found_directives)}) — may affect crawling or indexing",
            severity=Severity.INFO.value,
            recommendation="Review robots directives for unintended restrictions.",
            details={"directives": found_directives, "robots_meta": robots_meta},
        )]


class NoSnippetBlockingRule(BaseRule):
    rule_id = "no_snippet_blocking"
    name = "No Snippet Blocking"

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        robots_meta = (data.get("robots_meta") or "").strip().lower()
        blocks_snippet = False
        if "nosnippet" in robots_meta:
            blocks_snippet = True
        elif "max-snippet" in robots_meta:
            match = re.search(r"max-snippet\s*:\s*0\b", robots_meta)
            if match:
                blocks_snippet = True
        if blocks_snippet:
            return [self._result(
                passed=False,
                message="Page has snippet-blocking directive (nosnippet or max-snippet:0) — search results will not show a description",
                severity=Severity.WARNING.value,
                recommendation="Remove nosnippet/max-snippet:0 to allow search snippets.",
                details={"robots_meta": robots_meta},
            )]
        return [self._result(
            passed=True,
            message="Page allows search snippets",
            severity=Severity.PASSED.value,
        )]


__all__ = [
    "CanonicalAndNoindexConflictRule",
    "CanonicalHeaderValidationRule",
    "CanonicalLoopDetectionRule",
    "CanonicalNotPointingToHomepageRule",
    "CanonicalURLPresentRule",
    "CanonicalURLValidRule",
    "CanonicalProtocolMatchRule",
    "ConflictingCanonicalURLsRule",
    "FaviconPresentRule",
    "H1TagPresentRule",
    "MetaDescriptionLengthRule",
    "MetaDescriptionPresentRule",
    "NoSnippetBlockingRule",
    "RobotsMetaDirectivesRule",
    "SingleH1TagRule",
    "TitleTagLengthRule",
    "TitleTagPresentRule",
    "ViewportMetaTagRule",
]
