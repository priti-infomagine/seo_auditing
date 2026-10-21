"""
Technical SEO rules: viewport, favicon, robots meta, and snippet blocking.
"""
from __future__ import annotations

import re
from typing import Any

from ...models import Severity
from ..base import BaseRule


class ViewportMetaTagRule(BaseRule):
    """Check that a viewport meta tag is present for mobile-friendliness."""

    rule_id = "technical_009"
    name = "Viewport Meta Tag"
    category = "technical"
    description = "Page should have a viewport meta tag for mobile devices."
    weight = 0.7
    tags = ["technical", "mobile", "critical"]

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        viewport = (data.get("viewport") or "").strip()

        if not viewport:
            return [self._result(
                passed=False,
                message="Page is missing a viewport meta tag — may not render properly on mobile devices",
                severity=Severity.WARNING.value,
                score_impact=-5,
                recommendation="Add <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            )]

        return [self._result(
            passed=True,
            message=f"Viewport meta tag found: \"{viewport}\"",
            severity=Severity.PASSED.value,
            score_impact=0,
            data={"viewport": viewport},
        )]


class FaviconPresentRule(BaseRule):
    """Check that a favicon is specified."""

    rule_id = "technical_010"
    name = "Favicon Present"
    category = "technical"
    description = "Page should declare a favicon for browser tabs and bookmarks."
    weight = 0.3
    tags = ["technical", "favicon"]

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        favicon_urls: list[str] = data.get("favicon_urls", [])

        if not favicon_urls:
            return [self._result(
                passed=False,
                message="No favicon found",
                severity=Severity.INFO.value,
                score_impact=-1,
                recommendation="Add <link rel='icon' href='/favicon.ico'> to the page.",
            )]

        return [self._result(
            passed=True,
            message=f"Favicon(s) found: {len(favicon_urls)} detected — {favicon_urls[0][:80]}",
            severity=Severity.PASSED.value,
            score_impact=0,
            data={"favicon_urls": favicon_urls[:5]},
        )]


class RobotsMetaDirectivesRule(BaseRule):
    """Check for restrictive robots meta directives."""

    rule_id = "technical_011"
    name = "Robots Meta Directives"
    category = "technical"
    description = "Pages should not have restrictive robots directives (noindex, nofollow)."
    weight = 0.9
    tags = ["technical", "indexing", "critical"]

    RESTRICTIVE_DIRECTIVES = {"noindex", "nofollow", "none", "noarchive", "nosnippet", "max-snippet:0"}

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        robots_meta = (data.get("robots_meta") or "").strip().lower()

        if not robots_meta:
            return [self._result(
                passed=True,
                message="No robots meta directives found (page is indexable by default)",
                severity=Severity.PASSED.value,
                score_impact=0,
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
                score_impact=0,
                data={"robots_meta": robots_meta},
            )]

        if "noindex" in found_directives:
            return [self._result(
                passed=False,
                message=f"Restrictive robots directives found ({', '.join(found_directives)}) — page will not be indexed by search engines",
                severity=Severity.WARNING.value,
                score_impact=-10,
                recommendation="Remove noindex/nofollow directives if the page should be indexed.",
                data={"directives": found_directives, "robots_meta": robots_meta},
            )]

        return [self._result(
            passed=False,
            message=f"Restrictive robots directives found ({', '.join(found_directives)}) — may affect crawling or indexing",
            severity=Severity.INFO.value,
            score_impact=-2,
            recommendation="Review robots directives for unintended restrictions.",
            data={"directives": found_directives, "robots_meta": robots_meta},
        )]


class NoSnippetBlockingRule(BaseRule):
    """Check that the page does not block search snippets."""

    rule_id = "on_page_007"
    name = "No Snippet Blocking"
    category = "on_page"
    description = "Page should not have nosnippet or max-snippet:0 directives."
    weight = 0.6
    tags = ["on_page", "social", "critical"]

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
                score_impact=-5,
                recommendation="Remove nosnippet/max-snippet:0 to allow search snippets.",
                data={"robots_meta": robots_meta},
            )]

        return [self._result(
            passed=True,
            message="Page allows search snippets",
            severity=Severity.PASSED.value,
            score_impact=0,
        )]


__all__ = [
    "FaviconPresentRule",
    "NoSnippetBlockingRule",
    "RobotsMetaDirectivesRule",
    "ViewportMetaTagRule",
]
