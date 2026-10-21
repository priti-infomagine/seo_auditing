"""
Meta description SEO rules: presence and length checks.
"""
from __future__ import annotations

from typing import Any

from ...models import Severity
from ..base import BaseRule


class MetaDescriptionPresentRule(BaseRule):
    """Check that a meta description tag exists and is non-empty."""

    rule_id = "on_page_003"
    name = "Meta Description Present"
    category = "on_page"
    description = "Each page should have a meta description tag."
    weight = 1.2
    tags = ["on_page", "meta"]

    def evaluate(self, data: dict[str, Any]) -> list[Any]:
        desc = (data.get("description") or "").strip()

        if not desc:
            return [self._result(
                passed=False,
                message="Page is missing a <meta name='description'> tag",
                severity=Severity.WARNING.value,
                score_impact=-10,
                recommendation="Add a <meta name='description'> tag to the page.",
            )]

        return [self._result(
            passed=True,
            message=f"Meta description found ({len(desc)} characters)",
            severity=Severity.PASSED.value,
            score_impact=0,
            data={"length": len(desc)},
        )]


class MetaDescriptionLengthRule(BaseRule):
    """Check meta description length is within recommended range (120-160 characters)."""

    rule_id = "on_page_004"
    name = "Meta Description Length"
    category = "on_page"
    description = "Meta description should be 120-160 characters for optimal SEO."
    weight = 1.0
    tags = ["on_page", "meta"]

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
                score_impact=-5,
                recommendation="Add a meta description first.",
            )]

        if desc_length < self.RECOMMENDED_MIN:
            return [self._result(
                passed=False,
                message=f"Meta description length is {desc_length} characters (too short, recommended: {self.RECOMMENDED_MIN}-{self.RECOMMENDED_MAX})",
                severity=Severity.WARNING.value,
                score_impact=-5,
                recommendation=f"Make the description at least {self.RECOMMENDED_MIN} characters.",
                data={"length": desc_length},
            )]

        if desc_length > self.RECOMMENDED_MAX:
            return [self._result(
                passed=False,
                message=f"Meta description length is {desc_length} characters (too long, recommended: {self.RECOMMENDED_MIN}-{self.RECOMMENDED_MAX})",
                severity=Severity.WARNING.value,
                score_impact=-3,
                recommendation="Shorten the description to avoid SERP truncation.",
                data={"length": desc_length},
            )]

        return [self._result(
            passed=True,
            message=f"Meta description length is {desc_length} characters (good)",
            severity=Severity.PASSED.value,
            score_impact=0,
            data={"length": desc_length},
        )]


__all__ = ["MetaDescriptionLengthRule", "MetaDescriptionPresentRule"]
