"""
Pydantic schemas for the standardized, category-first SEO audit report.

These models are the public shape of the audit response returned to API callers (and to
the future chatbot retrieval layer). They are intentionally separate from the scorer's
internal models in `app/modules/rule_engine/models/rule_result.py` so that the response
shape can evolve without touching the rule engine.

NOTE on naming: `CategoryScore` is also defined in `rule_engine/models/rule_result.py`
with a DIFFERENT shape (it carries `issues`/`warnings`/`passed_rules`). The model here is
the *report* shape (`value`, `grade`, `max_possible`). They live in different modules and
are not imported together, so there is no collision.

The `CheckResult` model is an internal input contract for `report_assembler.build_*`; it
documents the per-check shape the assembler reshapes (it is not part of the public response).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AffectedPage(BaseModel):
    """A page affected by an issue, carrying the concrete FACT found and PROOF collected."""

    url: str = Field(..., description="Page URL where the check was run / issue observed.")
    found_value: Optional[Any] = Field(
        None,
        description="Concrete value the crawler observed for this check (the 'fact').",
    )
    expected_value: Optional[Any] = Field(
        None,
        description="The standard/requirement that was expected (the 'what should have been').",
    )
    evidence: Optional[Dict[str, Any]] = Field(
        None,
        description="Structured proof collected by the rule (image srcs, link hrefs, counts, etc.).",
    )


class Issue(BaseModel):
    """One failed check, grouped by check_id, spanning every affected page."""

    issue_id: str = Field(..., description="Report-wide sequential id, e.g. 'iss_0001'.")
    check_id: str = Field(..., description="Rule/check identifier (e.g. 'images_001').")
    severity: str = Field(..., description="critical | warning | info (sanitized; never 'error').")
    title: str = Field(..., description="Human-readable rule name (from the check).")
    description: str = Field(
        ...,
        description="General scorer message describing the failure (raw exceptions are never exposed).",
    )
    recommendation: Optional[str] = Field(None, description="How to fix the issue.")
    priority: str = Field(..., description="high | medium | low — triage priority for the issue.")
    estimated_impact: str = Field(..., description="high | medium | low — score-impact tier.")
    affected_page_count: int = Field(..., description="Distinct pages affected by this check.")
    affected_pages: List[AffectedPage] = Field(
        default_factory=list,
        description="Per-page facts + proof. Multiple entries when a check fails on several pages.",
    )


class CategoryScore(BaseModel):
    """Precomputed category score (reshaped, not recomputed by the report layer)."""

    value: float
    grade: str
    max_possible: float = Field(default=100, description="Maximum possible category score.")


class IssueCount(BaseModel):
    """Count of failed checks by severity within a category."""

    critical: int = 0
    warning: int = 0
    info: int = 0


class Category(BaseModel):
    """One SEO category bucket in the report, ordered by config (see CATEGORY_ORDER)."""

    id: str
    label: str
    order: int
    applicable: bool
    reason_not_applicable: Optional[str] = Field(
        None,
        description="Why this category was skipped for this site_category (when applicable=False).",
    )
    weight: float = 0.0
    score: Optional[CategoryScore] = Field(None, description="Precomputed score (None if not applicable).")
    status: Optional[str] = Field(None, description="good | needs_attention | critical")
    issue_count: Optional[IssueCount] = Field(
        None,
        description="Count of failed checks (zeros when applicable-but-clean; None when skipped).",
    )
    issues: List[Issue] = Field(default_factory=list)


class OverallScore(BaseModel):
    """Top-level report summary. `value`/`grade` are passed through from the scorer (no re-scoring)."""

    value: float
    grade: str
    max_possible: float = Field(default=100, description="Maximum possible overall score.")
    checks_run: int
    checks_applicable: int
    checks_excluded: int
    critical_issues: int
    warnings: int
    passed: int


class AuditReportResponse(BaseModel):
    """Standard, category-first SEO audit report.

    Shape (mirroring a readable SEO auditor): overall summary → ordered categories →
    priority-sorted issues, each issue rich with the offending page URL and structured proof.
    """

    scan_id: str
    url: str
    site_category: str
    scanned_at: str
    pages_crawled: int
    overall_score: OverallScore
    categories: List[Category]


class CheckResult(BaseModel):
    """Input contract for the report assembler: one already-scored rule evaluation.

    The adapter (`check_result_adapter.py`) builds these from the existing ScorerService
    output. All scoring numbers (`score`, `category_score`, `overall_value`) are computed
    upstream by `ScoreCalculator`; this layer only reshapes them.
    """

    check_id: str
    category: str = Field(..., description="Internal scorer category id (e.g. 'on_page').")
    weight: float = Field(default=1.0, description="Per-check weight (from BaseRule).")
    applicable: bool = Field(default=True, description="Whether this check applies to the site.")
    passed: bool
    severity: str = Field(
        ...,
        description="critical | warning | info | error | passed (source severity; 'error' is sanitized in output).",
    )
    score_impact: float = Field(default=0.0, description="Impact on category score (negative = penalty).")
    score: Optional[float] = Field(
        None,
        description="Per-check 0-100 score (already computed; derived by adapter if absent).",
    )
    category_score: Optional[float] = Field(
        None,
        description="Precomputed category score from compute.py (no recompute).",
    )
    category_grade: Optional[str] = None
    overall_value: Optional[float] = Field(
        None,
        description="Precomputed overall score (passed through from compute.py when available).",
    )
    overall_grade: Optional[str] = None
    page_url: str
    title: str = Field(..., description="Human-readable rule name.")
    description: Optional[str] = Field(None, description="General scorer message (raw exceptions sanitized at assembly).")
    recommendation: Optional[str] = None
    found_value: Optional[Any] = Field(None, description="Concrete fact observed (populated by adapter; used in output).")
    expected_value: Optional[Any] = Field(None, description="Required standard (populated by adapter; used in output).")
    evidence: Optional[Dict[str, Any]] = Field(
        None,
        description="Structured proof from RuleResult.data (image srcs, link hrefs, counts, ...).",
    )
