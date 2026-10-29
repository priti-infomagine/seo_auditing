"""
ContentRuleRegistry — collects and runs all 13 content BaseRule subclasses.

Mirrors core_seo.rules.registry.RuleRegistry but loads content checks
only. Reuses the same BaseRule class from core_seo for a shared base.
"""
from __future__ import annotations

import inspect
from typing import Any

from app.modules.category_check.core_seo.models import RuleResult, Severity
from app.modules.category_check.core_seo.rules.base import BaseRule
from .checks import (
    BrokenHTMLStructureRule,
    ContentMimeTypeRule,
    ContentReadingLevelRule,
    ContentWordCountRule,
    HeadingHierarchyRule,
    HeadingLengthRule,
    KeywordStuffingRule,
    LinkDensityRule,
    MetaDescriptionPixelWidthRule,
    MetaTagsInBodyRule,
    TextToHTMLRatioRule,
    TitleH1DuplicationRule,
    TitlePixelWidthRule,
)

ALL_CONTENT_RULES: list[type[BaseRule]] = [
    TextToHTMLRatioRule,
    ContentWordCountRule,
    LinkDensityRule,
    ContentReadingLevelRule,
    KeywordStuffingRule,
    HeadingHierarchyRule,
    HeadingLengthRule,
    TitleH1DuplicationRule,
    TitlePixelWidthRule,
    MetaDescriptionPixelWidthRule,
    BrokenHTMLStructureRule,
    MetaTagsInBodyRule,
    ContentMimeTypeRule,
]

CONTENT_RULE_COUNT = len(ALL_CONTENT_RULES)


class ContentRuleRegistry:
    """Registry that collects content rule classes and instantiates/runs them.

    Fault-tolerant per-rule, mirroring core_seo's RuleRegistry.
    """

    def __init__(self) -> None:
        self._rules: list[BaseRule] = []
        self._rule_classes: dict[str, type[BaseRule]] = {}

    def register(self, rule_class: type[BaseRule]) -> None:
        if not inspect.isclass(rule_class) or not issubclass(rule_class, BaseRule):
            raise TypeError(f"{rule_class} is not a BaseRule subclass")
        if rule_class.rule_id in self._rule_classes:
            return
        instance = rule_class()
        self._rules.append(instance)
        self._rule_classes[rule_class.rule_id] = rule_class

    def register_instance(self, instance: BaseRule) -> None:
        if instance.rule_id in self._rule_classes:
            return
        self._rules.append(instance)
        self._rule_classes[instance.rule_id] = instance.__class__

    def get_rules(self) -> list[BaseRule]:
        return list(self._rules)

    def run_all(self, data: dict[str, Any]) -> list[Any]:
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
    return RuleResult(
        rule_id=rule.rule_id,
        name=rule.name,
        severity=Severity.ERROR.value,
        passed=False,
        message=f"Rule evaluation failed: {rule.name}",
        recommendation="Check rule implementation for data mismatch",
        details={"error": True},
    )


def default_content_registry() -> ContentRuleRegistry:
    """Build a ContentRuleRegistry pre-loaded with all 13 content checks."""
    registry = ContentRuleRegistry()
    for rule_class in ALL_CONTENT_RULES:
        registry.register(rule_class)
    return registry


__all__ = [
    "ALL_CONTENT_RULES",
    "CONTENT_RULE_COUNT",
    "ContentRuleRegistry",
    "default_content_registry",
]
