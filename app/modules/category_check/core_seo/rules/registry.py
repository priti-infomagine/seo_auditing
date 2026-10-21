"""
RuleRegistry — collects and runs all BaseRule subclasses.

Auto-discovers rule subclasses via registry. The registry maintains
instances and provides fault-tolerant batch execution.
"""
from __future__ import annotations

import inspect
from typing import Any

from .base import BaseRule


class RuleRegistry:
    """Registry that collects rule classes and instantiates/runs them.

    Rules are registered explicitly via :meth:`register` or auto-discovered
    via :meth:`discover` (subclass scan of a target module).
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

    def discover(self, module: Any) -> None:
        """Auto-discover all BaseRule subclasses in *module* and its submodules."""
        import importlib
        import pkgutil

        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseRule) and obj is not BaseRule:
                if obj.__module__.startswith(module.__name__):
                    self.register(obj)

        for _finder, modname, ispkg in pkgutil.iter_modules(getattr(module, "__path__", [])):
            if modname.startswith("_"):
                continue
            try:
                submodule = importlib.import_module(f"{module.__name__}.{modname}")
                for _subname, obj in inspect.getmembers(submodule, inspect.isclass):
                    if issubclass(obj, BaseRule) and obj is not BaseRule:
                        if obj.__module__.startswith(submodule.__name__):
                            self.register(obj)
            except Exception:
                continue

    def get_rules(self, category: str | None = None) -> list[BaseRule]:
        """Return all registered rules, optionally filtered by category."""
        if category is None:
            return list(self._rules)
        return [r for r in self._rules if r.category == category]

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
                results.append(
                    type(results[0]) if results else _fallback_result(rule)
                )
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
    from ..models import RuleResult, Severity

    return RuleResult(
        rule_id=rule.rule_id,
        name=rule.name,
        category=rule.category,
        severity=Severity.ERROR.value,
        passed=False,
        message=f"Rule evaluation failed: {rule.name}",
        recommendation="Check rule implementation for data mismatch",
        data={"error": True},
        tags=list(rule.tags),
        score_impact=0.0,
    )


def default_registry() -> RuleRegistry:
    """Build a RuleRegistry pre-loaded with all built-in checks."""
    from . import checks as checks_module

    registry = RuleRegistry()
    registry.discover(checks_module)
    return registry


__all__ = ["RuleRegistry", "default_registry"]
