"""
BaseRule — Abstract base class for SEO rules in the Core SEO pipeline.

Self-contained: does not import from app.modules.rule_engine or
app.modules.scorer. Each rule receives a parsed data dict and returns
RuleResult(s).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import RuleResult, Severity


class BaseRule(ABC):
    """Abstract base class for SEO rules.

    Subclasses define class-level metadata (rule_id, name, severity)
    and implement :meth:`evaluate`.
    """

    rule_id: str = ""
    name: str = ""
    severity: str = Severity.WARNING.value

    def __init__(self) -> None:
        if not self.rule_id:
            raise ValueError(f"Rule {self.__class__.__name__} must define rule_id")
        if not self.name:
            raise ValueError(f"Rule {self.__class__.__name__} must define name")

    @abstractmethod
    def evaluate(self, data: dict[str, Any]) -> list[RuleResult]:
        """Evaluate the rule against parsed page data.

        Args:
            data: Parsed SEO data dict (from PageParser.build_rule_data).

        Returns:
            List of RuleResult objects (usually one).
        """
        ...

    def _result(
        self,
        passed: bool,
        message: str,
        severity: str = Severity.WARNING.value,
        recommendation: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> RuleResult:
        """Helper to create a RuleResult with this rule's metadata."""
        return RuleResult(
            rule_id=self.rule_id,
            name=self.name,
            severity=severity,
            passed=passed,
            message=message,
            recommendation=recommendation,
            details=details,
        )


__all__ = ["BaseRule"]
