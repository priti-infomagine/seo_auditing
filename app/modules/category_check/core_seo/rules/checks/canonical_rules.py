"""
Canonical URL SEO rules.

Eight rules covering canonical presence, validity, loop detection,
protocol match, homepage pointing, header validation, conflict resolution,
and noindex canonical conflicts.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from ...models import Severity
from ...url_normalizer import URLNormalizer
from ..base import BaseRule


class CanonicalURLPresentRule(BaseRule):
    """Check that a canonical URL is specified."""

    rule_id = "technical_001"
    name = "Canonical URL Present"
    category = "technical"
    description = "Page should specify a canonical URL via <link rel='canonical'>."
    weight = 1.0
    tags = ["technical", "canonical", "critical"]

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        canonical = (data.get("canonical") or "").strip()

        if not canonical:
            return [self._result(
                passed=False,
                message="Page is missing a <link rel='canonical'> tag",
                severity=Severity.WARNING.value,
                score_impact=-5,
                recommendation="Add <link rel='canonical' href='...'> to specify the preferred URL.",
            )]

        return [self._result(
            passed=True,
            message=f"Canonical URL found: {canonical}",
            severity=Severity.PASSED.value,
            score_impact=0,
            data={"canonical": canonical},
        )]


class CanonicalURLValidRule(BaseRule):
    """Check that the canonical URL is a valid, well-formed URL."""

    rule_id = "technical_002"
    name = "Canonical URL Valid"
    category = "technical"
    description = "Canonical URL must be a valid absolute http/https URL."
    weight = 0.8
    tags = ["technical", "canonical"]

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        canonical = (data.get("canonical") or "").strip()

        if not canonical:
            return [self._result(
                passed=False,
                message="No canonical tag found",
                severity=Severity.INFO.value,
                score_impact=-2,
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
                    score_impact=0,
                    data={"canonical": normalized},
                )]
        except (ValueError, Exception):
            pass

        return [self._result(
            passed=False,
            message=f"Canonical URL is invalid: {canonical}",
            severity=Severity.WARNING.value,
            score_impact=-4,
            recommendation="Fix the canonical URL to be a valid absolute http/https URL.",
            data={"canonical": canonical},
        )]


class CanonicalLoopDetectionRule(BaseRule):
    """Detect potential canonical loops (canonical points to a different URL)."""

    rule_id = "technical_003"
    name = "Canonical Loop Detection"
    category = "technical"
    description = "Canonical should point to the page's own URL to avoid loops."
    weight = 0.7
    tags = ["technical", "canonical"]

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        canonical = (data.get("canonical") or "").strip()
        page_url = data.get("url", "")

        if not canonical:
            return [self._result(
                passed=True,
                message="No canonical specified (nothing to loop)",
                severity=Severity.INFO.value,
                score_impact=0,
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
                score_impact=0,
            )]

        return [self._result(
            passed=False,
            message=f"Canonical URL ({canonical}) points to a different location than the page URL (potential loop risk)",
            severity=Severity.WARNING.value,
            score_impact=-3,
            recommendation="Ensure canonical points to the page's own URL.",
            data={"canonical": canonical, "page_url": page_url},
        )]


class CanonicalNotPointingToHomepageRule(BaseRule):
    """Check canonical doesn't point to the homepage (unless the page IS the homepage)."""

    rule_id = "technical_006"
    name = "Canonical Not Pointing to Homepage"
    category = "technical"
    description = "Non-homepage pages should not canonicalize to the site homepage."
    weight = 0.7
    tags = ["technical", "canonical"]

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        canonical = (data.get("canonical") or "").strip()
        page_url = data.get("url", "")

        if not canonical:
            return [self._result(
                passed=True,
                message="No canonical tag found (nothing to check)",
                severity=Severity.INFO.value,
                score_impact=0,
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
                score_impact=0,
            )]

        if is_homepage and not is_current_page_homepage:
            return [self._result(
                passed=False,
                message=f"Canonical URL points to the homepage ({canonical}) from a non-homepage page — this dilutes page-level SEO value",
                severity=Severity.WARNING.value,
                score_impact=-5,
                recommendation="Canonical should point to the page's own URL, not the homepage.",
                data={"canonical": canonical, "is_homepage": is_homepage},
            )]

        return [self._result(
            passed=True,
            message=f"Canonical does not point to homepage (path: {canonical_path or '/'})",
            severity=Severity.PASSED.value,
            score_impact=0,
            data={"canonical_path": canonical_path},
        )]


class CanonicalProtocolMatchRule(BaseRule):
    """Check that canonical protocol matches the page protocol."""

    rule_id = "technical_007"
    name = "Canonical Protocol Match"
    category = "technical"
    description = "Canonical URL protocol (http/https) should match the page protocol."
    weight = 0.5
    tags = ["technical", "canonical"]

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        canonical = (data.get("canonical") or "").strip()
        page_url = data.get("url", "")

        if not canonical:
            return [self._result(
                passed=True,
                message="No canonical specified (nothing to compare)",
                severity=Severity.INFO.value,
                score_impact=0,
            )]

        try:
            canonical_parts = urlsplit(canonical)
            page_parts = urlsplit(page_url)
        except (ValueError, Exception):
            return [self._result(
                passed=True,
                message="Could not compare protocols (invalid URL)",
                severity=Severity.INFO.value,
                score_impact=0,
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
                score_impact=0,
                data={"canonical_protocol": canonical_proto, "page_protocol": page_proto},
            )]

        return [self._result(
            passed=False,
            message=f"Canonical protocol ({canonical_proto}) does not match page protocol ({page_proto})",
            severity=Severity.WARNING.value,
            score_impact=-3,
            recommendation="Ensure canonical uses the same protocol (http/https) as the page.",
            data={"canonical_protocol": canonical_proto, "page_protocol": page_proto},
        )]


class CanonicalAndNoindexConflictRule(BaseRule):
    """Check for conflict between canonical and noindex directive."""

    rule_id = "technical_008"
    name = "Canonical and Noindex Conflict"
    category = "technical"
    description = "A page with noindex should not have a canonical pointing to itself."
    weight = 0.8
    tags = ["technical", "canonical", "critical"]

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
                score_impact=0,
            )]

        if not canonical:
            return [self._result(
                passed=True,
                message="noindex present but no canonical (no conflict)",
                severity=Severity.INFO.value,
                score_impact=0,
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
                score_impact=-8,
                recommendation="Remove noindex if the page should be indexed, or remove canonical if it should not.",
                data={"canonical": canonical, "robots_meta": robots_meta},
            )]

        return [self._result(
            passed=True,
            message=f"noindex is present with an external canonical URL ({canonical}) — no conflict",
            severity=Severity.INFO.value,
            score_impact=0,
            data={"canonical": canonical, "robots_meta": robots_meta},
        )]


class CanonicalHeaderValidationRule(BaseRule):
    """Check that canonical is specified via a single source."""

    rule_id = "technical_004"
    name = "Canonical Header Validation"
    category = "technical"
    description = "Canonical should be specified via a single source (link tag or HTTP header)."
    weight = 0.6
    tags = ["technical", "canonical"]

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        source_count = data.get("canonical_source_count", 0)
        canonical = data.get("canonical", "")

        if not canonical:
            return [self._result(
                passed=True,
                message="No canonical specified",
                severity=Severity.INFO.value,
                score_impact=0,
            )]

        if source_count == 0:
            return [self._result(
                passed=True,
                message="Canonical URL found via single source",
                severity=Severity.PASSED.value,
                score_impact=0,
            )]

        if source_count == 1:
            return [self._result(
                passed=True,
                message=f"Canonical URL found via single source ({source_count} source)",
                severity=Severity.PASSED.value,
                score_impact=0,
                data={"source_count": source_count},
            )]

        return [self._result(
            passed=False,
            message=f"Multiple canonical sources found ({source_count} sources) — canonical defined both in <link> tag and HTTP header",
            severity=Severity.WARNING.value,
            score_impact=-3,
            recommendation="Specify canonical via only one source to avoid ambiguity.",
            data={"source_count": source_count},
        )]


class ConflictingCanonicalURLsRule(BaseRule):
    """Check that at most one canonical source is found."""

    rule_id = "technical_005"
    name = "Conflicting Canonical URLs"
    category = "technical"
    description = "At most one canonical URL should be specified per page."
    weight = 0.6
    tags = ["technical", "canonical"]

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        source_count = data.get("canonical_source_count", 0)

        if source_count == 0:
            return [self._result(
                passed=True,
                message="No canonical sources found (page does not use canonicalization)",
                severity=Severity.INFO.value,
                score_impact=0,
            )]

        if source_count == 1:
            return [self._result(
                passed=True,
                message=f"At most one canonical source found ({source_count} source)",
                severity=Severity.PASSED.value,
                score_impact=0,
                data={"source_count": source_count},
            )]

        return [self._result(
            passed=False,
            message=f"Conflicting canonical URLs: {source_count} sources found on the same page — search engines cannot determine the preferred URL",
            severity=Severity.WARNING.value,
            score_impact=-5,
            recommendation="Keep only one canonical URL source per page.",
            data={"source_count": source_count},
        )]


__all__ = [
    "CanonicalAndNoindexConflictRule",
    "CanonicalHeaderValidationRule",
    "CanonicalLoopDetectionRule",
    "CanonicalNotPointingToHomepageRule",
    "CanonicalProtocolMatchRule",
    "CanonicalURLPresentRule",
    "CanonicalURLValidRule",
    "ConflictingCanonicalURLsRule",
]
