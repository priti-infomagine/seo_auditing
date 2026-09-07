"""
Compact Pydantic schemas for the new audit read layer.

These models are the contract for the additive `/audits/{audit_id}/...`
endpoints. They are deliberately smaller than the legacy
`audit_response_schemas.UnifiedAuditResponse`: no per-page evidence,
no nested issue objects in categories, no raw headers/links/images.

The legacy response shape is preserved untouched for backward
compatibility — see `audit_response_schemas.py` and the existing
`/audit/result/{crawl_id}` endpoint.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IssueTierCounts(BaseModel):
    """Per-severity issue counts."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    total: int = 0


class CheckCounts(BaseModel):
    """Passed / failed rule counts."""

    passed: int = 0
    failed: int = 0
    total: int = 0


class PagesBlock(BaseModel):
    """Compact page counts for an audit."""

    crawled: int = 0
    analyzed: int = 0
    failed: int = 0


class AuditMeta(BaseModel):
    """Audit metadata for the compact overview."""

    id: str
    url: Optional[str] = None
    status: Optional[str] = None
    pages: PagesBlock = Field(default_factory=PagesBlock)
    duration_ms: Optional[int] = None


class AuditSummary(BaseModel):
    """Top-line summary for the compact overview."""

    score: float = 0.0
    grade: Optional[str] = None
    health: str = "unknown"
    issues: IssueTierCounts = Field(default_factory=IssueTierCounts)
    checks: CheckCounts = Field(default_factory=CheckCounts)


class CategorySummary(BaseModel):
    """Per-category aggregate only — no nested issue objects."""

    id: str
    name: str
    score: float = 0.0
    status: str = "not_available"
    issues: IssueTierCounts = Field(default_factory=IssueTierCounts)
    checks_total: int = 0
    checks_passed: int = 0
    checks_failed: int = 0


class IssuePageSample(BaseModel):
    """One affected page sample (max 3 in compact top issues)."""

    url: str
    found: Optional[str] = None


class TopIssueSummary(BaseModel):
    """Compact issue summary used in overview and issue list."""

    id: str
    rule_id: str
    category: str
    severity: str
    impact: str
    affected_pages: int = 0
    sample: List[IssuePageSample] = Field(default_factory=list)


class AuditOverview(BaseModel):
    """Compact audit overview response. Target 5–20 KB."""

    audit: AuditMeta
    summary: AuditSummary
    categories: List[CategorySummary] = Field(default_factory=list)
    top_issues: List[TopIssueSummary] = Field(default_factory=list)
