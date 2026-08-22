"""
Standardized SEOIssue model for rule evaluation results.

The rule engine produces RuleResult objects (one per rule per page). The
RuleResultToSEOIssueConverter (see issue_factory.py) normalizes each into a
SEOIssue — a single, consistent structure carrying the page URL, the specific
affected part, the factual evidence collected by the crawler/parser, and the
4-tier severity.

SEOIssue is the INTERNAL contract. Its public projection is the slim
`issues[]` array: {page_url, affected_part} only.
"""
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class SeverityTier(str, Enum):
    """Four-tier severity used in the unified audit response."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SEOIssue(BaseModel):
    """
    Standardized issue produced at the rule-engine boundary.

    One instance per (rule evaluation, page). `status="passed"` entries are
    retained for category roll-ups; only `status="failed"` entries surface in
    the public `issues[]` list (projected as {page_url, affected_part}).
    """

    rule_id: str = Field(..., description="Stable machine identifier, e.g. 'on_page_002'")
    severity: SeverityTier = Field(..., description="critical | high | medium | low")
    category: str = Field(..., description="Internal rule category, e.g. 'on_page'")
    status: str = Field(..., description="passed | failed")
    page_url: str = Field(..., description="URL of the affected page")
    affected_part: str = Field(
        ..., description="Specific element/location affected, e.g. 'meta_description'"
    )
    evidence: dict = Field(
        default_factory=dict, description="Factual evidence from crawler/parser (minimal)"
    )
    score_impact: float = Field(default=0.0, description="Penalty applied to score")
    message: Optional[str] = Field(
        default=None, description="Short human-readable description of the issue"
    )
    recommendation: Optional[str] = Field(
        default=None, description="Suggested fix text"
    )
    current_description: Optional[str] = Field(
        default=None, description="Current state/value of the checked element"
    )
    recommended: List[str] = Field(
        default_factory=list, description="Recommended values or actions with lengths"
    )

    page_id: Optional[str] = Field(default=None, description="DB page uuid (internal)")
    crawl_id: Optional[str] = Field(default=None, description="DB crawl uuid (internal)")
    project_id: Optional[str] = Field(default=None, description="DB project uuid (internal)")
