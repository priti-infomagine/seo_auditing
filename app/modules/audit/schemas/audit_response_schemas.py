"""
Pydantic schemas for the unified audit API response.

`issues[]` carries rule-first nested page evidence, including additive,
versioned evidence envelopes. `UnifiedAuditResponse` collapses to 4 top-level
keys: `audit`, `summary`, `categories`, `issues`.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PageIssueEvidence(BaseModel):
    page_url: str
    current_value: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)
    classified_images: List[Dict[str, Any]] = Field(default_factory=list)


class RuleLevelIssue(BaseModel):
    rule_id: str
    category: str
    severity: str
    title: Optional[str] = None
    why: Optional[str] = None
    what: Optional[str] = None
    recommendation: Optional[str] = None
    affected_pages: int = 0
    occurrences: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: Optional[Dict[str, Any]] = None
    evidence_v1: List[Dict[str, Any]] = Field(default_factory=list)
    pages: List[PageIssueEvidence] = Field(default_factory=list)


class UnifiedAuditResponse(BaseModel):
    """Full unified SEO audit response (returned by /audit/analyze, /audit/score, /audit/result)."""

    model_config = ConfigDict(extra="allow")

    audit: Dict[str, Any]
    summary: Dict[str, Any]
    categories: List[Dict[str, Any]]
    issues: List[RuleLevelIssue] = Field(default_factory=list)
