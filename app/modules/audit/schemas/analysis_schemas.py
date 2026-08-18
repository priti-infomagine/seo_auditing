"""
Pydantic schemas for the DB-backed analysis pipeline API endpoints.

All schemas use `project_id` as the main tracking key alongside `crawl_id`.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field


class ParseTriggerRequest(BaseModel):
    """Request to trigger DB-backed parsing for a crawl."""

    project_id: Optional[UUID] = Field(
        None,
        description="Project identifier. If None, a new UUID is generated from the crawl_id.",
    )
    force: bool = Field(
        False,
        description="If True, re-parse pages that already have parsed facts.",
    )


class EvaluateTriggerRequest(BaseModel):
    """Request to trigger rule evaluation for a crawl."""

    project_id: UUID = Field(
        ...,
        description="Project identifier — links to parsed facts from the parse phase.",
    )
    force: bool = Field(
        False,
        description="If True, re-evaluate rules even if results already exist.",
    )


class ScoreTriggerRequest(BaseModel):
    """Request to trigger scoring for a crawl."""

    project_id: UUID = Field(
        ...,
        description="Project identifier — links to rule evaluation results.",
    )
    force: bool = Field(
        False,
        description="If True, re-score even if analysis already exists.",
    )


class PipelineStatusResponse(BaseModel):
    """Status of all pipeline stages for a project."""

    project_id: str = Field(..., description="Project identifier")
    crawl_id: str = Field(..., description="Crawl job identifier")
    parse_status: str = Field(..., description="pending | completed | failed | missing")
    evaluate_status: str = Field(..., description="pending | completed | failed | missing")
    score_status: str = Field(..., description="pending | completed | failed | missing")
    pages_parsed: int = Field(0, description="Number of pages with parsed facts")
    rules_evaluated: int = Field(0, description="Number of rule result rows")
    overall_score: Optional[float] = Field(None, description="Overall SEO score (0-100)")
    grade: Optional[str] = Field(None, description="Letter grade")
    output_file_path: Optional[str] = Field(None, description="Path to output JSON file")


class StageSummary(BaseModel):
    """Summary of a single pipeline stage."""

    status: str
    count: int = 0
    completed_at: Optional[str] = None


class ParseStageSummary(StageSummary):
    pages_parsed: int = 0
    pages_failed: int = 0
    pages_skipped: int = 0


class EvaluateStageSummary(StageSummary):
    total_results: int = 0
    rules_run: int = 0
    error_count: int = 0


class ScoreStageSummary(StageSummary):
    overall_score: Optional[float] = None
    grade: Optional[str] = None
    total_pages_scored: int = 0
    critical_issues: int = 0
    output_file_path: Optional[str] = None


class PipelineSummaryResponse(BaseModel):
    """Full pipeline summary for a project."""

    project_id: str
    crawl_id: str
    domain: str
    parse: ParseStageSummary
    evaluate: EvaluateStageSummary
    score: ScoreStageSummary


class PageScoreDetail(BaseModel):
    """Per-page score details."""

    page_id: str
    url: str
    overall_score: float
    grade: str
    rules_passed: int
    rules_failed: int
    critical_issues: int


class SeoAnalysisResponse(BaseModel):
    """Full SEO analysis result for a project."""

    project_id: str
    crawl_id: str
    domain: str
    overall_score: float
    grade: str
    total_pages_scored: int
    total_rules_evaluated: int
    total_passed: int
    total_failed: int
    critical_issues: int
    warnings: int
    error_pages: int
    error_summary: Optional[Dict[str, Any]] = None
    summary: str
    category_scores: Dict[str, Any]
    top_issues: List[Dict[str, Any]]
    per_page: List[Dict[str, Any]]
    output_file_path: Optional[str] = None
    scored_at: str
    analysis_status: str


class SeoAnalysisSummary(BaseModel):
    """Summary of an analysis run for history listing."""

    project_id: str
    crawl_id: str
    domain: str
    overall_score: float
    grade: str
    total_pages_scored: int
    critical_issues: int
    scored_at: str


class PaginatedAnalyses(BaseModel):
    """Paginated list of analysis runs."""

    total: int
    limit: int
    offset: int
    results: List[SeoAnalysisSummary]


class AnalysisError(BaseModel):
    """Error response for analysis endpoints."""

    success: bool = False
    error: str
    detail: str
