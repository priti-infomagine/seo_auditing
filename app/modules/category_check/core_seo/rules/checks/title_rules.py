"""
Title tag SEO rules: presence and length checks.
"""
from __future__ import annotations

from typing import Any

from ...models import Severity
from ..base import BaseRule


class TitleTagPresentRule(BaseRule):
    """Check that a <title> tag exists and is non-empty."""

    rule_id = "on_page_001"
    name = "Title Tag Present"
    category = "on_page"
    description = "Each page must have a <title> tag with non-empty content."
    weight = 1.5
    tags = ["on_page", "title", "critical"]

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        title = (data.get("title") or "").strip()

        if not title:
            return [self._result(
                passed=False,
                message="Missing <title> tag",
                severity=Severity.WARNING.value,
                score_impact=-8,
                recommendation="Add a unique, descriptive <title> tag to the page.",
            )]

        return [self._result(
            passed=True,
            message=f"Title tag found: \"{title[:80]}\"",
            severity=Severity.PASSED.value,
            score_impact=0,
            data={"title": title, "character_count": len(title)},
        )]


class TitleTagLengthRule(BaseRule):
    """Check title tag length is within recommended range (30-60 characters)."""

    rule_id = "on_page_002"
    name = "Title Tag Length"
    category = "on_page"
    description = "Title tag should be 30-60 characters for optimal SEO."
    weight = 1.0
    tags = ["on_page", "title"]

    RECOMMENDED_MIN = 30
    RECOMMENDED_MAX = 60

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        title = (data.get("title") or "").strip()
        title_length = len(title)

        if not title:
            return [self._result(
                passed=False,
                message="Missing title tag",
                severity=Severity.INFO.value,
                score_impact=-5,
                recommendation="Add a <title> tag first.",
            )]

        if title_length < self.RECOMMENDED_MIN:
            return [self._result(
                passed=False,
                message=f"Title is too short ({title_length} characters, recommended: {self.RECOMMENDED_MIN}-{self.RECOMMENDED_MAX})",
                severity=Severity.WARNING.value,
                score_impact=-4,
                recommendation=f"Make the title at least {self.RECOMMENDED_MIN} characters.",
                data={"length": title_length},
            )]

        if title_length > self.RECOMMENDED_MAX:
            return [self._result(
                passed=False,
                message=f"Title is too long ({title_length} characters, recommended: {self.RECOMMENDED_MIN}-{self.RECOMMENDED_MAX})",
                severity=Severity.WARNING.value,
                score_impact=-3,
                recommendation="Shorten the title to 30-60 characters to avoid SERP truncation.",
                data={"length": title_length},
            )]

        return [self._result(
            passed=True,
            message=f"Title length is optimal ({title_length} characters)",
            severity=Severity.PASSED.value,
            score_impact=0,
            data={"length": title_length},
        )]


__all__ = ["TitleTagLengthRule", "TitleTagPresentRule"]
