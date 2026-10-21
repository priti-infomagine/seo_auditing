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
    NormalizedResult,
    PageScore,
    PipelineEvent,
    RuleResult,
)


class PageNormalizer:
    """Normalizes a PageScore into a JSON-serializable structure."""

    def normalize_rule_result(self, result: RuleResult) -> dict[str, Any]:
        """Convert a single RuleResult into a flat dict."""
        return {
            "rule_id": result.rule_id,
            "name": result.name,
            "passed": result.passed,
            "severity": result.severity,
            "message": result.message,
            "recommendation": result.recommendation,
            "details": result.details or {},
        }

    def normalize_page(self, page: PageScore) -> dict[str, Any]:
        """Convert a PageScore into a normalized dict."""
        rule_results = [
            self.normalize_rule_result(r) for r in page.rule_results
        ]

        return {
            "url": page.url,
            "status": "completed",
            "passed": page.passed,
            "failed": page.failed,
            "total": page.total,
            "pass_percentage": page.pass_percentage,
            "results": rule_results,
        }


class AuditNormalizer:
    """Produces the final JSON-serializable audit report dict."""

    def __init__(self, page_normalizer: PageNormalizer | None = None):
        self.page_normalizer = page_normalizer or PageNormalizer()

    def normalize_event(self, event: PipelineEvent) -> dict[str, Any]:
        """Convert a PipelineEvent into a flat dict."""
        return {
            "event_type": event.event_type,
            "audit_id": event.audit_id,
            "url": event.url,
            "timestamp": event.timestamp,
            "payload": event.payload or event.data,
        }

    def normalize(
        self,
        report: AuditReport,
    ) -> NormalizedResult:
        """Convert an AuditReport dataclass into a NormalizedResult dict structure.

        If ``report.summary`` is populated (set by ``finalize_audit``),
        it is used directly. Otherwise it is computed from per-page results.
        """
        pages = [self.page_normalizer.normalize_page(p) for p in report.pages]

        if report.summary:
            summary = dict(report.summary)
        else:
            rules_passed = sum(p.passed for p in report.pages)
            rules_failed = sum(p.failed for p in report.pages)
            total_rules = rules_passed + rules_failed
            pass_pct = round(rules_passed / total_rules * 100, 1) if total_rules else 0.0
            summary = {
                "pages_total": report.total_pages,
                "pages_done": report.crawled_pages,
                "pages_failed": report.pages_failed,
                "rules_passed": rules_passed,
                "rules_failed": rules_failed,
                "pass_percentage": pass_pct,
            }

        events = [self.normalize_event(e) for e in report.events]

        return NormalizedResult(
            audit_id=report.audit_id,
            status=report.status,
            summary=summary,
            pages=pages,
            events=events,
            pass_percentage=summary.get("pass_percentage", 0.0),
        )

    def normalize_from_state(
        self,
        audit_id: str,
        overall_score: float,
        grade: str,
        events: list[PipelineEvent],
    ) -> NormalizedResult:
        """Build a NormalizedResult from audit state.

        Kept for backward compatibility — overall_score/grade are retained
        as informational fields.
        """
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
            pass_percentage=overall_score,
        )


def normalize_report(report: AuditReport) -> dict[str, Any]:
    """Convenience: normalize AuditReport → plain dict (fully JSON-serializable)."""
    normalizer = AuditNormalizer()
    result = normalizer.normalize(report)
    return {
        "audit_id": result.audit_id,
        "status": result.status,
        "summary": result.summary,
        "pages": result.pages,
        "events": result.events,
    }
__all__ = ["AuditNormalizer", "PageNormalizer", "normalize_report"]
