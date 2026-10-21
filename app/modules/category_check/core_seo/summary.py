"""
Summary module — replaces the old scorer.py.

Provides simple pass/fail ratio summaries for a single page or an entire
audit, replacing the weighted category scoring system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import RuleResult


@dataclass(slots=True)
class PageSummary:
    """Summary of rule results for a single page."""

    passed: int = 0
    failed: int = 0
    total: int = 0
    pass_percentage: float = 0.0
    rule_results: list[RuleResult] = field(default_factory=list)


@dataclass(slots=True)
class AuditSummary:
    """Aggregate summary for an entire audit."""

    pages_total: int = 0
    pages_done: int = 0
    pages_failed: int = 0
    rules_passed: int = 0
    rules_failed: int = 0
    rules_total: int = 0
    pass_percentage: float = 0.0


def summarize_page(results: list[RuleResult]) -> PageSummary:
    """Summarize a single page's rule results.

    Args:
        results: List of RuleResult objects from evaluating all rules on a page.

    Returns:
        PageSummary with pass/fail counts and pass percentage.
    """
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    pct = round(passed / total * 100, 1) if total else 0.0
    return PageSummary(
        passed=passed,
        failed=failed,
        total=total,
        pass_percentage=pct,
        rule_results=list(results),
    )


def summarize_audit(page_summaries: list[PageSummary]) -> AuditSummary:
    """Summarize an entire audit from per-page summaries.

    Args:
        page_summaries: List of PageSummary objects, one per processed page.

    Returns:
        AuditSummary with aggregate counts and pass percentage.
    """
    pages_total = len(page_summaries)
    pages_done = pages_total
    rules_passed = sum(p.passed for p in page_summaries)
    rules_failed = sum(p.failed for p in page_summaries)
    rules_total = rules_passed + rules_failed
    pct = round(rules_passed / rules_total * 100, 1) if rules_total else 0.0
    return AuditSummary(
        pages_total=pages_total,
        pages_done=pages_done,
        pages_failed=0,
        rules_passed=rules_passed,
        rules_failed=rules_failed,
        rules_total=rules_total,
        pass_percentage=pct,
    )


__all__ = ["AuditSummary", "PageSummary", "summarize_audit", "summarize_page"]
