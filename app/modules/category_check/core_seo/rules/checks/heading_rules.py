"""
Heading-based SEO rules: H1 presence and single-H1 validation.
"""
from __future__ import annotations

from typing import Any

from ...models import Severity
from ..base import BaseRule


class H1TagPresentRule(BaseRule):
    """Check that at least one H1 tag exists on the page."""

    rule_id = "on_page_005"
    name = "H1 Tag Present"
    category = "on_page"
    description = "Page should have at least one <h1> tag."
    weight = 1.3
    tags = ["on_page", "headings", "critical"]

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
                score_impact=-6,
                recommendation="Add a single <h1> tag that describes the page's main topic.",
            )]

        return [self._result(
            passed=True,
            message=f"H1 tag found: \"{h1_text[:80]}\"",
            severity=Severity.PASSED.value,
            score_impact=0,
            data={"h1_count": h1_count, "h1_text": h1_text[:200]},
        )]


class SingleH1TagRule(BaseRule):
    """Check that the page has exactly one H1 tag."""

    rule_id = "on_page_006"
    name = "Single H1 Tag"
    category = "on_page"
    description = "Page should have exactly one H1 tag for clear hierarchy."
    weight = 0.8
    tags = ["on_page", "headings"]

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        heading_counts = data.get("heading_counts", {})
        h1_count = heading_counts.get("h1", 0) if heading_counts else 0

        if h1_count == 0:
            return [self._result(
                passed=False,
                message="Page does not have an <h1> tag",
                severity=Severity.WARNING.value,
                score_impact=-6,
                recommendation="Add exactly one <h1> tag.",
            )]

        if h1_count > 1:
            return [self._result(
                passed=False,
                message=f"Multiple <h1> tags found ({h1_count}) — pages should have exactly one H1 for clear heading hierarchy",
                severity=Severity.WARNING.value,
                score_impact=-4,
                recommendation="Use only one <h1> tag per page; use <h2>, <h3>, etc. for subheadings.",
                data={"h1_count": h1_count},
            )]

        return [self._result(
            passed=True,
            message="Page has exactly one <h1> tag (good)",
            severity=Severity.PASSED.value,
            score_impact=0,
            data={"h1_count": h1_count},
        )]


__all__ = ["H1TagPresentRule", "SingleH1TagRule"]
