"""
RuleRegistry — collects and runs all BaseRule subclasses.

Rules are registered explicitly via :meth:`register` or pre-loaded via
:meth:`default_registry`. The registry provides fault-tolerant batch execution.
"""
from __future__ import annotations

import inspect
from typing import Any

from .base import BaseRule
from .checks import (
    CanonicalAndNoindexConflictRule,
    CanonicalHeaderValidationRule,
    CanonicalLoopDetectionRule,
    CanonicalNotPointingToHomepageRule,
    CanonicalProtocolMatchRule,
    CanonicalURLPresentRule,
    CanonicalURLValidRule,
    ConflictingCanonicalURLsRule,
    FaviconPresentRule,
    H1TagPresentRule,
    MetaDescriptionLengthRule,
    MetaDescriptionPresentRule,
    NoSnippetBlockingRule,
    RobotsMetaDirectivesRule,
    SingleH1TagRule,
    TitleTagLengthRule,
    TitleTagPresentRule,
    ViewportMetaTagRule,
)
from ..models import RuleResult, Severity


ALL_RULES: list[type[BaseRule]] = [
    TitleTagPresentRule,
    TitleTagLengthRule,
    MetaDescriptionPresentRule,
    MetaDescriptionLengthRule,
    H1TagPresentRule,
    SingleH1TagRule,
    CanonicalURLPresentRule,
    CanonicalURLValidRule,
    CanonicalLoopDetectionRule,
    CanonicalHeaderValidationRule,
    ConflictingCanonicalURLsRule,
    CanonicalNotPointingToHomepageRule,
    CanonicalProtocolMatchRule,
    CanonicalAndNoindexConflictRule,
    ViewportMetaTagRule,
    FaviconPresentRule,
    RobotsMetaDirectivesRule,
    NoSnippetBlockingRule,
]


class RuleRegistry:
    """Registry that collects rule classes and instantiates/runs them.

    Rules are registered explicitly via :meth:`register` or
    :meth:`register_instance`.
    """

    def __init__(self) -> None:
        self._rules: list[BaseRule] = []
        self._rule_classes: dict[str, type[BaseRule]] = {}

    def register(self, rule_class: type[BaseRule]) -> None:
        """Register a rule class (instantiates immediately)."""
        if not inspect.isclass(rule_class) or not issubclass(rule_class, BaseRule):
            raise TypeError(f"{rule_class} is not a BaseRule subclass")
        if rule_class.rule_id in self._rule_classes:
            return
        instance = rule_class()
        self._rules.append(instance)
        self._rule_classes[rule_class.rule_id] = rule_class

    def register_instance(self, instance: BaseRule) -> None:
        """Register a pre-instantiated rule."""
        if instance.rule_id in self._rule_classes:
            return
        self._rules.append(instance)
        self._rule_classes[instance.rule_id] = instance.__class__

    def get_rules(self) -> list[BaseRule]:
        """Return all registered rules."""
        return list(self._rules)

    def run_all(self, data: dict[str, Any]) -> list[Any]:
        """Run every registered rule, fault-tolerant per-rule.

        Returns:
            List of RuleResult objects.
        """
        results: list[Any] = []
        for rule in self._rules:
            try:
                rule_results = rule.evaluate(data)
                if rule_results is None:
                    continue
                if isinstance(rule_results, list):
                    results.extend(rule_results)
                else:
                    results.append(rule_results)
            except Exception:
                results.append(_fallback_result(rule))
        return results

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def __len__(self) -> int:
        return len(self._rules)

    def __iter__(self):
        return iter(self._rules)


def _fallback_result(rule: BaseRule) -> Any:
    """Create an error RuleResult when a rule raises an exception."""
    return RuleResult(
        rule_id=rule.rule_id,
        name=rule.name,
        severity=Severity.ERROR.value,
        passed=False,
        message=f"Rule evaluation failed: {rule.name}",
        recommendation="Check rule implementation for data mismatch",
        details={"error": True},
    )


def default_registry() -> RuleRegistry:
    """Build a RuleRegistry pre-loaded with all 18 built-in checks."""
    registry = RuleRegistry()
    for rule_class in ALL_RULES:
        registry.register(rule_class)
    return registry


__all__ = ["ALL_RULES", "RuleRegistry", "default_registry"]
