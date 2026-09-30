"""Schemas for the link_analysis API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, conint

from .model import (
    FindingCategory,
    FindingType,
    LinkAnalysisCheckStatus,
    LinkAnalysisOverallStatus,
    LinkAnalysisSeverity,
    LinkStatusClass,
)


class LinkAnalysisRequest(BaseModel):
    url: str = Field(
        ...,
        min_length=1,
        description="Website URL or bare domain to analyze",
    )
    max_pages: Optional[int] = Field(
        default=None,
        ge=1,
        le=5000,
        description="Maximum number of pages to crawl and analyze",
    )

    def validate_url(self) -> str:
        normalized = self.url.strip()
        if not normalized:
            raise ValueError("url must not be empty")
        return normalized


class LinkAnalysisQueuedResponse(BaseModel):
    check_id: UUID
    task_id: Optional[str] = None
    url: str
    domain: str
    status: LinkAnalysisCheckStatus
    max_pages: Optional[int] = None
    created_at: Optional[str] = None


class SourceReference(BaseModel):
    source_url: str
    anchor_text: Optional[str] = ""
    rel: List[str] = Field(default_factory=list)


class FindingResponse(BaseModel):
    category: FindingCategory
    type: FindingType
    severity: LinkAnalysisSeverity
    target_url: str
    status_code: Optional[int] = None
    final_url: Optional[str] = None
    total_sources: int = 0
    sources: List[SourceReference] = Field(default_factory=list)
    recommendation: Optional[Union[str, Dict[str, Any]]] = None
    evidence: Optional[Dict[str, Any]] = None


class PageAnalysisItem(BaseModel):
    url: str
    status_code: Optional[int] = None
    depth: int = 0
    inbound_internal_links: int = 0
    outbound_internal_links: int = 0
    outbound_external_links: int = 0
    total_links: int = 0
    unique_links: int = 0
    unique_internal_targets: int = 0
    unique_external_targets: int = 0
    broken_internal_links: int = 0
    broken_external_links: int = 0
    internal_links: List[Dict[str, Any]] = Field(default_factory=list)
    external_links: List[Dict[str, Any]] = Field(default_factory=list)
    is_orphan: bool = False
    is_dead_end: bool = False
    issues: List[str] = Field(default_factory=list)


class LinkAnalysisSummary(BaseModel):
    pages_crawled: int = 0
    crawl_truncated: bool = False
    blocked_by_robots: int = 0
    internal_link_occurrences: int = 0
    unique_internal_targets: int = 0
    unique_external_targets: int = 0
    external_link_occurrences: int = 0
    broken_internal_link_occurrences: int = 0
    broken_external_link_occurrences: int = 0
    unverified_links: int = 0
    broken_links: int = 0
    counts_by_category: Optional[Dict[str, int]] = None
    counts_by_type: Optional[Dict[str, int]] = None
    counts_by_severity: Optional[Dict[str, int]] = None
    total_issues: int = 0
    total_opportunities: int = 0


class LinkAnalysisProgress(BaseModel):
    phase: str
    pages_crawled: int = 0
    max_pages: int = 0
    message: str = ""


class LinkAnalysisCheckResponse(BaseModel):
    check_id: UUID
    url: str
    domain: str
    status: LinkAnalysisCheckStatus
    task_id: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    # Completed-only fields
    checked_at: Optional[str] = None
    overall_status: Optional[str] = None
    severity: Optional[str] = None
    cost_seconds: Optional[float] = None
    summary: Optional[LinkAnalysisSummary] = None
    pages: List[PageAnalysisItem] = Field(default_factory=list)
    findings: List[FindingResponse] = Field(default_factory=list)
    total_findings: int = 0


class PaginatedFindings(BaseModel):
    findings: List[FindingResponse]
    page: int
    page_size: int
    total: int
    has_next: bool


__all__ = [
    "LinkAnalysisRequest",
    "LinkAnalysisQueuedResponse",
    "SourceReference",
    "PageAnalysisItem",
    "FindingResponse",
    "LinkAnalysisSummary",
    "LinkAnalysisProgress",
    "LinkAnalysisCheckResponse",
    "PaginatedFindings",
    "FindingCategory",
    "FindingType",
    "LinkAnalysisCheckStatus",
    "LinkAnalysisOverallStatus",
    "LinkAnalysisSeverity",
    "LinkStatusClass",
]

