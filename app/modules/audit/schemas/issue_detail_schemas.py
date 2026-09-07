"""
Pydantic schemas for the lazy-loaded detail endpoints of the new audit
read layer.

These complement the compact overview (`audit_summary_schemas.AuditOverview`)
by providing the heavy details on demand:

* `IssueDetailResponse`     — full rule metadata, recommendation, examples
* `IssueListResponse`       — paginated compact issue summaries
* `IssuePagesResponse`      — paginated affected pages for one issue
* `IssueEvidenceResponse`   — heavy evidence (links / images / rule_data)
* `PageDetailResponse`      — per-page breakdown
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.modules.audit.schemas.audit_summary_schemas import (
    IssuePageSample,
    TopIssueSummary,
)


class RuleMeta(BaseModel):
    """Rule metadata for the issue detail view."""

    id: str
    title: str
    description: Optional[str] = None
    fix: Optional[str] = None


class AffectedSummary(BaseModel):
    """Affected-page summary for a single issue."""

    pages: int = 0
    items: int = 0


class IssueDetailResponse(BaseModel):
    """Detailed view of one issue. Target < 50 KB."""

    id: str
    rule: RuleMeta
    severity: str
    impact: str
    affected: AffectedSummary
    fix: Optional[str] = None
    examples: List[IssuePageSample] = Field(default_factory=list)


class IssueListResponse(BaseModel):
    """Paginated compact issue list."""

    total: int
    limit: int
    offset: int
    items: List[TopIssueSummary] = Field(default_factory=list)


class IssuePageRow(BaseModel):
    """A single affected page row."""

    page_id: str
    url: str
    found: Optional[str] = None
    status: Optional[str] = None


class IssuePagesResponse(BaseModel):
    """Paginated affected pages for one issue."""

    total: int
    limit: int
    offset: int
    items: List[IssuePageRow] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """One evidence item — heavy, lazy-loaded."""

    page_id: str
    url: str
    found_value: Optional[str] = None
    expected_value: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)


class EvidenceLink(BaseModel):
    """A single link evidence row."""

    page_id: str
    url: str
    link_type: str = "internal"
    href: str
    anchor: Optional[str] = None
    nofollow: bool = False


class EvidenceImage(BaseModel):
    """A single image evidence row."""

    page_id: str
    url: str
    src: str
    alt: Optional[str] = None
    has_alt: bool = False
    width: Optional[int] = None
    height: Optional[int] = None


class IssueEvidenceResponse(BaseModel):
    """Heavy evidence for one issue — paginated for links and images."""

    rule_id: str
    items: List[EvidenceItem] = Field(default_factory=list)
    links: List[EvidenceLink] = Field(default_factory=list)
    images: List[EvidenceImage] = Field(default_factory=list)
    total_links: int = 0
    total_images: int = 0
    total_items: int = 0


class PageDetailResponse(BaseModel):
    """Per-page breakdown for one page."""

    page_id: str
    url: str
    status: Optional[int] = None
    score: Optional[float] = None
    grade: Optional[str] = None
    issues: List[IssuePageRow] = Field(default_factory=list)
    facts: Optional[Dict[str, Any]] = None
