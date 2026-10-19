"""
Normalizer — converts internal dataclass models into JSON-serializable dicts.

Provides:
    PageNormalizer — flatten a PageScore into a serializable dict.
    AuditNormalizer — produce the final JSON-friendly audit report dict.
"""
from __future__ import annotations

from typing import Any

from .models import (
    AuditReport,
    CategoryScore,
    NormalizedResult,
    PageScore,
    PipelineEvent,
    RuleResult,
)
from .scorer import Scorer


class PageNormalizer:
    """Normalizes a PageScore into a JSON-serializable structure."""

    def normalize_rule_result(self, result: RuleResult) -> dict[str, Any]:
        """Convert a single RuleResult into a flat dict."""
        return {
            "rule_id": result.rule_id,
            "rule_name": result.name,
            "category": result.category,
            "passed": result.passed,
            "severity": result.severity,
            "message": result.message,
            "recommendation": result.recommendation,
            "score_impact": result.score_impact,
            "data": result.data or {},
        }

    def normalize_page(self, page: PageScore) -> dict[str, Any]:
        """Convert a PageScore into a normalized dict."""
        rule_results = [
            self.normalize_rule_result(r)
            for r in page.rule_results.values()
        ]

        return {
            "url": page.url,
            "score": page.score,
            "on_page_score": page.on_page_score,
            "technical_score": page.technical_score,
            "rules": rule_results,
            "passed_rules": sum(1 for r in rule_results if r["passed"]),
            "failed_rules": sum(1 for r in rule_results if not r["passed"]),
        }


class AuditNormalizer:
    """Produces the final JSON-serializable audit report dict."""

    def __init__(self, page_normalizer: PageNormalizer | None = None):
        self.page_normalizer = page_normalizer or PageNormalizer()

    def normalize_category(self, cat: CategoryScore) -> dict[str, Any]:
        return {
            "category": cat.category,
            "score": cat.score,
            "weight": cat.weight,
            "rule_count": cat.rule_count,
            "passed_rules": cat.passed_rules,
        }

    def normalize_event(self, event: PipelineEvent) -> dict[str, Any]:
        return {
            "id": event.timestamp,
            "event_type": event.event_type.value if hasattr(event.event_type, "value") else event.event_type,
            "audit_id": event.audit_id,
            "url": event.url,
            "timestamp": event.timestamp,
            "payload": event.payload or event.data,
        }

    def normalize(
        self,
        report: AuditReport,
        scorer: Scorer | None = None,
    ) -> NormalizedResult:
        """Convert an AuditReport dataclass into a NormalizedResult dict structure.

        Args:
            report: The AuditReport dataclass with raw page scores.
            scorer: Optional scorer to produce audit-level summary. If None,
                    a default Scorer is constructed.

        Returns:
            NormalizedResult with the JSON-serializable structure.
        """
        if scorer is None:
            scorer = Scorer()

        pages = [self.page_normalizer.normalize_page(p) for p in report.pages]
        categories = [
            self.normalize_category(c) for c in report.categories
        ]

        if report.pages:
            overall_score = round(
                sum(p.score for p in report.pages if p.score is not None) / len(report.pages),
                2,
            )
        else:
            overall_score = report.overall_score

        events = [self.normalize_event(e) for e in report.events]

        summary: dict[str, Any] = {
            "overall_score": overall_score,
            "grade": scorer.calculator.determine_grade(overall_score) if pages else report.grade,
            "page_count": len(pages),
            "categories": categories,
        }

        return NormalizedResult(
            audit_id=report.audit_id,
            status=report.status,
            summary=summary,
            pages=pages,
            events=events,
        )

    def normalize_from_state(
        self,
        audit_id: str,
        overall_score: float,
        grade: str,
        events: list[PipelineEvent],
    ) -> NormalizedResult:
        """Build a NormalizedResult from in-memory audit state (for get_report)."""
        event_list = [self.normalize_event(e) for e in events]
        summary = {
            "overall_score": overall_score,
            "grade": grade,
            "page_count": len(event_list),
        }
        return NormalizedResult(
            audit_id=audit_id,
            status="completed",
            summary=summary,
            pages=[],
            events=event_list,
        )


def normalize_report(
    report: AuditReport,
    scorer: Scorer | None = None,
) -> dict[str, Any]:
    """Convenience: normalize AuditReport → plain dict (fully JSON-serializable)."""
    normalizer = AuditNormalizer()
    result = normalizer.normalize(report, scorer)
    return {
        "audit_id": result.audit_id,
        "status": result.status,
        "summary": result.summary,
        "pages": result.pages,
        "events": result.events,
    }


__all__ = ["AuditNormalizer", "PageNormalizer", "normalize_report"]
