"""
Report Assembler - reshapes already-computed scorer check results into a
category-first, priority-sorted, human-readable SEO audit report.

This is a **pure** module: NO database access, NO network calls, NO LLM. It consumes a
contract of already-scored `CheckResult` items (produced by `check_result_adapter.py` from
the existing `ScorerService` / `ScoreCalculator` output) and reshapes them into an
`AuditReportResponse`.

Design contract (read once, then it's self-evident):
  * Scoring is NEVER redone here. `OverallScore.value`/`grade` and each
    `CategoryScore.value`/`grade` are passed through from `ScoreCalculator`. When the
    caller did not carry them (e.g. a synthetic mock), the assembler falls back to a
    weighted aggregation of the already-computed category scores — still never re-deriving
    per-check penalties.
  * Category order and status thresholds come from `score_calculator.py` (config), not
    hardcoded here, so the report structure can be tuned without touching logic.
  * Each issue carries FACTS + PROOF: `found_value` (what was observed), `expected_value`
    (the standard), and `evidence` (the concrete elements/links/images the rule collected).
  * Raw rule-evaluation exceptions are NEVER exposed: `ERROR`-severity checks are normalized
    to a normal `warning`-severity issue with a general description (see `_sanitize_description`).

Public entry point:
  `build_report_response(scan_id, url, site_category, scanned_at, pages_crawled, check_results)`
"""
from __future__ import annotations

import itertools
from typing import Dict, List, Optional, Tuple

from app.core.datetime_utils import utc_now
from app.schemas.report_schemas import (
    AffectedPage,
    AuditReportResponse,
    Category,
    CategoryScore,
    CheckResult,
    Issue,
    IssueCount,
    OverallScore,
)
from app.modules.scorer.services.score_calculator import (
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    CATEGORY_SITE_APPLICABILITY,
    ESTIMATED_IMPACT_TIERS,
    INTERNAL_TO_RESPONSE,
    SEVERITY_PRIORITY_MAP,
    STATUS_THRESHOLDS,
)

# Triage-priority rank for sorting issues within a category (high first).
_PRIORITY_RANK: Dict[str, int] = {"high": 0, "medium": 1, "low": 2}
# Estimated-impact rank for deterministic tie-breaking.
_IMPACT_RANK: Dict[str, int] = {"high": 0, "medium": 1, "low": 2}


def _resolve_category(category: str) -> str:
    """Map a scorer internal category id to a report response category id."""
    return INTERNAL_TO_RESPONSE.get(category, category)


def _category_relevance(category_id: str, site_category: str) -> bool:
    """True when `category_id` is relevant for `site_category`.

    Categories absent from `CATEGORY_SITE_APPLICABILITY` are relevant for every site.
    """
    allowed = CATEGORY_SITE_APPLICABILITY.get(category_id)
    return True if allowed is None else (site_category in allowed)


def _status(value: Optional[float]) -> Optional[str]:
    """Map a category score to a status (good / needs_attention / critical)."""
    if value is None:
        return None
    if value >= STATUS_THRESHOLDS["good"]:
        return "good"
    if value >= STATUS_THRESHOLDS["needs_attention"]:
        return "needs_attention"
    return "critical"


def _grade(value: float) -> str:
    """Mirror ScoreCalculator._get_grade so the report can grade standalone (e.g. mocks)."""
    if value >= 95:
        return "A+"
    if value >= 90:
        return "A"
    if value >= 85:
        return "B+"
    if value >= 80:
        return "B"
    if value >= 75:
        return "C+"
    if value >= 70:
        return "C"
    if value >= 60:
        return "D"
    if value >= 50:
        return "E"
    return "F"


def _tier_for_severity(severity: str, impact: float) -> Tuple[str, str, str]:
    """Derive (issue_severity, priority, estimated_impact) for a failed check.

    `severity` is the source severity (may be 'error'). The returned `issue_severity` is
    always one of critical/warning/info (errors are folded to 'warning'); `priority` uses
    the raw severity so rule-infra failures stay high priority.
    """
    sev = (severity or "").lower()
    priority = SEVERITY_PRIORITY_MAP.get(sev, "medium")
    issue_severity = {"critical": "critical", "warning": "warning", "info": "info"}.get(sev, "warning")
    abs_impact = abs(impact)
    if abs_impact >= ESTIMATED_IMPACT_TIERS["high"]:
        estimated_impact = "high"
    elif abs_impact >= ESTIMATED_IMPACT_TIERS["medium"]:
        estimated_impact = "medium"
    else:
        estimated_impact = "low"
    return issue_severity, priority, estimated_impact


def _sanitize_description(severity: str, title: str, description: Optional[str]) -> str:
    """Guarantee the exposed description is a general message, never a raw exception."""
    if (severity or "").lower() == "error":
        return f"{title or 'This check'} could not be fully evaluated."
    if description and "rule evaluation failed" in description.lower():
        return f"{title or 'This check'} could not be fully evaluated."
    return description or ""


def _build_issues(
    failed_checks: List[CheckResult], counter: "itertools.count"
) -> List[Issue]:
    """Group failed checks by check_id into Issues; one Issue may span many pages."""
    grouped: Dict[str, List[CheckResult]] = {}
    for check in failed_checks:
        grouped.setdefault(check.check_id, []).append(check)

    issues: List[Issue] = []
    for check_id, group in grouped.items():
        head = group[0]
        issue_severity, priority, estimated_impact = _tier_for_severity(
            head.severity, head.score_impact
        )
        affected_pages = [
            AffectedPage(
                url=c.page_url,
                found_value=c.found_value,
                expected_value=c.expected_value,
                evidence=c.evidence,
            )
            for c in group
        ]
        issues.append(
            Issue(
                issue_id="",
                check_id=check_id,
                severity=issue_severity,
                title=head.title,
                description=_sanitize_description(head.severity, head.title, head.description),
                recommendation=head.recommendation,
                priority=priority,
                estimated_impact=estimated_impact,
                affected_page_count=len(group),
                affected_pages=affected_pages,
            )
        )

    # Sort by priority desc, then estimated impact, then check_id for determinism.
    issues.sort(
        key=lambda i: (
            _PRIORITY_RANK.get(i.priority, 99),
            _IMPACT_RANK.get(i.estimated_impact, 99),
            i.check_id,
        )
    )
    # Assign sequential ids AFTER sorting so ids mirror display order (stable within a response).
    for issue in issues:
        issue.issue_id = f"iss_{next(counter):04d}"
    return issues


def _build_category(
    category_id: str,
    checks: List[CheckResult],
    site_category: str,
    counter: "itertools.count",
) -> Category:
    """Build a single Category (applicable or skipped) from its checks."""
    order = CATEGORY_ORDER.get(category_id, 999)
    label = CATEGORY_LABELS.get(category_id, category_id)
    applicable_checks = [c for c in checks if c.applicable]
    relevant = _category_relevance(category_id, site_category)
    cat_applicable = relevant and len(applicable_checks) > 0

    if not cat_applicable:
        reason = (
            f"site_category '{site_category}' does not require {label.lower()} signals."
            if not relevant
            else f"no applicable checks configured for {label.lower()}."
        )
        return Category(
            id=category_id,
            label=label,
            order=order,
            applicable=False,
            reason_not_applicable=reason,
            weight=0.0,
            score=None,
            status=None,
            issue_count=None,
            issues=[],
        )

    weight = round(sum(c.weight for c in applicable_checks), 4)

    # Category score: prefer the precomputed value from compute.py (no recompute);
    # fall back to a weighted aggregation of already-computed per-check scores.
    cat_value: Optional[float] = None
    cat_grade: Optional[str] = None
    for c in applicable_checks:
        if c.category_score is not None:
            cat_value = c.category_score
            cat_grade = c.category_grade
            break
    if cat_value is None:
        scored = [c for c in applicable_checks if c.score is not None]
        if scored:
            wsum = sum(c.weight for c in scored) or 1.0
            cat_value = round(sum(c.score * c.weight for c in scored) / wsum, 1)
            cat_grade = _grade(cat_value)

    score = CategoryScore(
        value=cat_value if cat_value is not None else 0.0,
        grade=cat_grade or _grade(cat_value or 0.0),
    )
    failed = [c for c in applicable_checks if not c.passed]
    issues = _build_issues(failed, counter)
    counts = IssueCount(
        critical=sum(1 for i in issues if i.severity == "critical"),
        warning=sum(1 for i in issues if i.severity == "warning"),
        info=sum(1 for i in issues if i.severity == "info"),
    )
    return Category(
        id=category_id,
        label=label,
        order=order,
        applicable=True,
        reason_not_applicable=None,
        weight=weight,
        score=score,
        status=_status(cat_value),
        issue_count=counts,
        issues=issues,
    )


def _build_overall_score(
    check_results: List[CheckResult], categories: List[Category]
) -> OverallScore:
    """Aggregate overall summary from check_results + precomputed category scores."""
    checks_run = len(check_results)
    checks_applicable = sum(1 for c in check_results if c.applicable)
    checks_excluded = checks_run - checks_applicable
    critical_issues = sum(c.issue_count.critical for c in categories if c.issue_count)
    warnings = sum(c.issue_count.warning for c in categories if c.issue_count)
    passed = sum(1 for c in check_results if c.applicable and c.passed)

    value: Optional[float] = next(
        (c.overall_value for c in check_results if c.overall_value is not None), None
    )
    grade: Optional[str] = next(
        (c.overall_grade for c in check_results if c.overall_grade is not None), None
    )
    if value is None:
        scored_cats = [c for c in categories if c.applicable and c.score]
        wsum = sum(c.weight for c in scored_cats)
        value = (
            round(sum(c.score.value * c.weight for c in scored_cats) / wsum, 1)
            if scored_cats and wsum
            else 0.0
        )
    if grade is None:
        grade = _grade(value or 0.0)

    return OverallScore(
        value=value or 0.0,
        grade=grade or "F",
        checks_run=checks_run,
        checks_applicable=checks_applicable,
        checks_excluded=checks_excluded,
        critical_issues=critical_issues,
        warnings=warnings,
        passed=passed,
    )


def build_report_response(
    scan_id: str,
    url: str,
    site_category: str,
    scanned_at: str,
    pages_crawled: int,
    check_results: List[CheckResult],
) -> AuditReportResponse:
    """Build the standardized, category-first audit report from already-scored checks.

    Args:
        scan_id: Identifier of the scan/audit run.
        url: Root URL that was audited.
        site_category: Business type of the site (e.g. 'ecommerce', 'blog', 'local_business').
            Drives per-category applicability/reasons.
        scanned_at: ISO timestamp of the scan.
        pages_crawled: Number of pages crawled for this scan.
        check_results: Already-scored check contract items (see `CheckResult`).

    Returns:
        A deterministic `AuditReportResponse`: overall summary -> ordered categories ->
        priority-sorted issues, each carrying per-page facts + proof. Pure / no I/O.
    """
    counter = itertools.count(1)

    # Group checks by their resolved REPORT category id (maps internal -> friendly id).
    groups: Dict[str, List[CheckResult]] = {}
    for check in check_results:
        groups.setdefault(_resolve_category(check.category), []).append(check)

    # Emit every configured category in order (skip the reserved 'overall_summary').
    ordered_ids = sorted(CATEGORY_ORDER.keys(), key=lambda k: CATEGORY_ORDER[k])
    categories: List[Category] = [
        _build_category(cat_id, groups.get(cat_id, []), site_category, counter)
        for cat_id in ordered_ids
        if cat_id != "overall_summary"
    ]

    # Append any check results whose resolved category was not in CATEGORY_ORDER
    # (defensive: never silently drop a failing check).
    extras = sorted(
        (k for k in groups if k not in CATEGORY_ORDER and k != "overall_summary")
    )
    for cat_id in extras:
        categories.append(_build_category(cat_id, groups.get(cat_id, []), site_category, counter))

    overall_score = _build_overall_score(check_results, categories)
    return AuditReportResponse(
        scan_id=scan_id,
        url=url,
        site_category=site_category,
        scanned_at=scanned_at,
        pages_crawled=pages_crawled,
        overall_score=overall_score,
        categories=categories,
    )


def _demo() -> None:
    """Self-contained usage example with a mock, multi-page check_results list.

    Run directly: `python app/modules/scorer/report_assembler.py`
    """
    from datetime import datetime, timezone

    checks = [
        # Failed 'Mobile Viewport' check on TWO pages -> one Issue, two AffectedPages.
        CheckResult(
            check_id="technical_002", category="technical", weight=1.0, applicable=True,
            passed=False, severity="warning", score_impact=-5, score=95.0,
            category_score=85.0, category_grade="B",
            page_url="https://example.com/page1", title="Mobile Viewport",
            description="No mobile viewport tag found",
            recommendation="Add a <meta name='viewport'> tag.",
            found_value={"viewport_present": False}, expected_value="<meta name='viewport'>",
            evidence={"viewport": None, "doctype": "<!DOCTYPE html>"},
        ),
        CheckResult(
            check_id="technical_002", category="technical", weight=1.0, applicable=True,
            passed=False, severity="warning", score_impact=-5, score=95.0,
            category_score=85.0, category_grade="B",
            page_url="https://example.com/page2", title="Mobile Viewport",
            description="No mobile viewport tag found",
            recommendation="Add a <meta name='viewport' tag.",
            found_value={"viewport_present": False}, expected_value="<meta name='viewport'>",
            evidence={"viewport": None},
        ),
        # Failed 'Title Tag' check (critical), single page.
        CheckResult(
            check_id="on_page_001", category="on_page", weight=1.5, applicable=True,
            passed=False, severity="critical", score_impact=-15, score=85.0,
            category_score=70.0, category_grade="C",
            page_url="https://example.com/page1", title="Title Tag",
            description="Missing page title tag",
            recommendation="Add a descriptive <title> tag (30-60 characters).",
            found_value={"title": ""}, expected_value="30-60 characters",
            evidence={"title_length": 0},
        ),
        # A passing check (should NOT appear as an issue, but counts toward `passed`).
        CheckResult(
            check_id="on_page_002", category="on_page", weight=1.0, applicable=True,
            passed=True, severity="passed", score_impact=1, score=100.0,
            category_score=70.0, category_grade="C",
            page_url="https://example.com/page1", title="Meta Description",
            description="Meta description length is optimal (155 characters).",
        ),
        # A rule that ERRORED during evaluation -> sanitized to a normal warning issue,
        # no raw exception string leaks into the response.
        CheckResult(
            check_id="seo_001", category="technical", weight=0.9, applicable=True,
            passed=False, severity="error", score_impact=0.0, score=0.0,
            category_score=85.0, category_grade="B",
            page_url="https://example.com/page1", title="Security Headers",
            description="Rule evaluation failed: KeyError('strict-transport-security')",
            recommendation="Check rule implementation for data mismatch",
        ),
        # Local SEO check, marked not-applicable for an ecommerce site.
        CheckResult(
            check_id="local_001", category="local_seo", weight=1.0, applicable=False,
            passed=False, severity="warning", score_impact=-1, score=99.0,
            page_url="https://example.com/page1", title="Local Business Schema",
            description="Not applicable for this site.",
        ),
    ]

    report = build_report_response(
        scan_id="scan_demo_001",
        url="https://example.com",
        site_category="ecommerce",
        scanned_at=utc_now().isoformat(),
        pages_crawled=2,
        check_results=checks,
    )
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    _demo()
