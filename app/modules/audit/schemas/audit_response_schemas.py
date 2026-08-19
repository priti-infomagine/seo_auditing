"""
Pydantic schemas for the unified audit API response.

`issues[]` is strictly {page_url, affected_part} — enforced via `extra="forbid"` so no
verbose prose can leak into the public issue list.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SEOIssueResponse(BaseModel):
    """
    Public projection of an issue.

    Carries the rule_id scheme (e.g. 'on_page_002') so every entry is
    traceable to `recommendations[]` / `priorities{}`; `severity` matches the
    priorities buckets (critical/high/medium/low) and `message` is a short
    human-readable description.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Stable machine identifier, e.g. 'on_page_002'")
    severity: str = Field(
        ..., description="critical | high | medium | low (matches priorities buckets)"
    )
    message: Optional[str] = Field(
        None, description="Short human-readable description of the issue"
    )
    page_url: str = Field(..., description="URL of the page with the issue")
    affected_part: str = Field(
        ..., description="Specific element/location affected, e.g. 'meta_description'"
    )


class _Metric(BaseModel):
    available: bool
    value: Optional[Any] = None
    reason: Optional[str] = None


class _StatusScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    score: Optional[float] = None


class UnifiedAuditResponse(BaseModel):
    """Full unified SEO audit response (returned by /audit/analyze, /audit/score, /audit/result)."""

    model_config = ConfigDict(extra="allow")

    audit: Dict[str, Any]
    summary: Dict[str, Any]
    categories: List[Dict[str, Any]]
    issues: List[SEOIssueResponse]
    category_results: Dict[str, Any]
    crawl: Dict[str, Any]
    indexation: Dict[str, Any]
    performance: Dict[str, Any]
    structured_data: Dict[str, Any]
    links: Dict[str, Any]
    images: Dict[str, Any]
    content: Any  # dict of metrics or mixed available-value dicts
    priorities: Dict[str, List[str]]
    recommendations: List[Dict[str, Any]]
    external_dependencies: List[Dict[str, Any]]
    errors: List[Dict[str, Any]]
    metadata: Dict[str, Any]
