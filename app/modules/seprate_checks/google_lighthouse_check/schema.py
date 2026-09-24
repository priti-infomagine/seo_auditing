from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

from app.modules.seprate_checks.google_lighthouse_check.validation import (
    DEFAULT_CATEGORIES,
    normalize_categories,
    normalize_device,
    validate_max_pages,
    validate_url,
)


class LighthouseCheckRequest(BaseModel):
    url: str = Field(
        ...,
        description="The seed URL to crawl and run Lighthouse checks against",
    )
    device: str = Field(
        ...,
        description="The device type for the check ('mobile' or 'desktop')",
    )
    category: Optional[List[str]] = Field(
        None,
        description=(
            "Lighthouse categories to include [performance, seo, "
            "best-practices, accessibility]. Defaults to all four."
        ),
    )
    version: Optional[str] = Field(
        None,
        description="Lighthouse version hint (currently unused)",
    )
    max_pages: Optional[int] = Field(
        None,
        description="Cap on total pages to crawl and check",
    )

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return validate_url(v)

    @field_validator("device")
    @classmethod
    def _validate_device(cls, v: str) -> str:
        return normalize_device(v)

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        normalized = normalize_categories(v)
        return normalized or None

    @field_validator("max_pages")
    @classmethod
    def _validate_max_pages(cls, v: Optional[int]) -> Optional[int]:
        return validate_max_pages(v)

    @property
    def effective_category(self) -> List[str]:
        return self.category or list(DEFAULT_CATEGORIES)


class LighthouseRecommendation(BaseModel):
    audit_id: str = Field(..., description="Stable Lighthouse audit identifier")
    category: str = Field(..., description="Lighthouse category, such as Performance")
    category_weight: Optional[float] = Field(
        None,
        description="Weight of this audit in its Lighthouse category score",
    )
    title: str = Field(..., description="Human-readable audit title")
    score: Optional[int] = Field(None, description="Audit score from 0 to 100")
    score_display_mode: Optional[str] = Field(
        None,
        description="Lighthouse score display mode, such as metricSavings or binary",
    )
    display_value: Optional[str] = Field(None, description="Lighthouse display value")
    numeric_value: Optional[float] = Field(
        None,
        description="Raw Lighthouse numeric audit value",
    )
    numeric_unit: Optional[str] = Field(
        None,
        description="Unit for numeric_value, such as millisecond or byte",
    )
    description: Optional[str] = Field(None, description="What Lighthouse detected")
    explanation: Optional[str] = Field(
        None,
        description="Lighthouse explanation of the detected issue",
    )
    details_type: Optional[str] = Field(
        None,
        description="Lighthouse details type, such as opportunity or diagnostic",
    )
    estimated_savings_ms: Optional[int] = Field(
        None,
        description="Estimated time savings when Lighthouse provides overallSavingsMs",
    )
    estimated_savings_bytes: Optional[int] = Field(
        None,
        description="Estimated byte savings when Lighthouse provides overallSavingsBytes",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings returned by Lighthouse for this audit",
    )
    error_message: Optional[str] = Field(
        None,
        description="Error returned by Lighthouse for this audit, if any",
    )
    evidence: list[dict] = Field(
        default_factory=list,
        description="Structured URLs, selectors, sources, snippets, and node labels from audit details",
    )
    where_to_fix: str = Field(
        ...,
        description="URL, selector, source, or node identified by Lighthouse",
    )
    recommendation: str = Field(..., description="Actionable fix recommendation")


class LighthouseCheckResponse(BaseModel):
    id: UUID = Field(
        ...,
        description="The unique identifier for the Lighthouse check result",
    )
    url: str = Field(
        ...,
        description="The URL that was checked",
    )
    device: str = Field(
        ...,
        description="The device type for the check (e.g., 'mobile' or 'desktop')",
    )
    status: str = Field(
        ...,
        description="The status of the Lighthouse check (e.g., 'success', 'failed', 'skipped')",
    )
    reason: Optional[str] = Field(
        None,
        description="The reason for the status if applicable (e.g., skip reason or error message)",
    )
    performance_score: Optional[int] = Field(
        None,
        description="The performance score from the Lighthouse check (0-100)",
    )
    seo_score: Optional[int] = Field(
        None,
        description="The SEO score from the Lighthouse check (0-100)",
    )
    fcp_ms: Optional[int] = Field(
        None,
        description="First Contentful Paint in milliseconds",
    )
    lcp_ms: Optional[int] = Field(
        None,
        description="Largest Contentful Paint in milliseconds",
    )
    tbt_ms: Optional[int] = Field(
        None,
        description="Total Blocking Time in milliseconds",
    )
    cls: Optional[float] = Field(
        None,
        description="Cumulative Layout Shift score",
    )
    recommendations: list[LighthouseRecommendation] = Field(
        default_factory=list,
        description=(
            "Actionable Lighthouse recommendations with category, evidence, "
            "estimated savings, and where to fix the issue"
        ),
    )


class LighthouseCheckQueuedResponse(BaseModel):
    success: bool = Field(
        True,
        description="Always true for a successfully accepted request",
    )
    status: str = Field(
        "queued",
        description="The initial status of the check (queued)",
    )
    message: str = Field(
        ...,
        description="Human-readable status message",
    )
    check_id: UUID = Field(
        ...,
        description=(
            "The unique identifier for this Lighthouse check. Use it to poll "
            "GET /api/v1/lighthouse/status/{check_id} and fetch results at "
            "GET /api/v1/lighthouse/results/{check_id}"
        ),
    )
    task_id: str = Field(
        ...,
        description="The Celery task id backing this check",
    )
    url: str = Field(
        ...,
        description="The seed URL that was accepted for checking",
    )
    domain: str = Field(
        ...,
        description="The domain name extracted from the seed URL",
    )
    device: str = Field(
        ...,
        description="The device strategy for the check (mobile/desktop)",
    )
    categories: List[str] = Field(
        ...,
        description="The Lighthouse categories requested",
    )
    status_url: str = Field(
        ...,
        description="URL to poll for progress: /api/v1/lighthouse/status/{check_id}",
    )
    result_url: str = Field(
        ...,
        description="URL to fetch final results: /api/v1/lighthouse/results/{check_id}",
    )


class LighthouseCheckStatusResponse(BaseModel):
    check_id: UUID = Field(
        ...,
        description="The unique identifier for this Lighthouse check",
    )
    task_id: Optional[str] = Field(
        None,
        description="The backing Celery task id (if still available)",
    )
    status: str = Field(
        ...,
        description="Overall check status (queued/crawling/completed/failed)",
    )
    phase: str = Field(
        ...,
        description="Current phase (queued/crawl/pagespeed/completed/failed)",
    )
    domain: str = Field(
        ...,
        description="The domain name being checked",
    )
    device: str = Field(
        ...,
        description="The device strategy for the check",
    )
    categories: List[str] = Field(
        ...,
        description="The Lighthouse categories requested",
    )
    pages_discovered: int = Field(
        ...,
        description="Total pages discovered for the domain",
    )
    pages_crawled: int = Field(
        ...,
        description="Pages successfully crawled via the crawler",
    )
    pagespeed_total: int = Field(
        ...,
        description="Number of pages queued for PageSpeed API checks",
    )
    pagespeed_checked: int = Field(
        ...,
        description="PageSpeed API checks completed (succeeded + failed)",
    )
    pagespeed_succeeded: int = Field(
        ...,
        description="PageSpeed API checks that succeeded",
    )
    pagespeed_failed: int = Field(
        ...,
        description="PageSpeed API checks that failed",
    )
    progress_percent: Optional[int] = Field(
        None,
        description="Overall progress percentage (0-100)",
    )
    started_at: Optional[str] = Field(
        None,
        description="ISO timestamp when the check started",
    )
    completed_at: Optional[str] = Field(
        None,
        description="ISO timestamp when the check completed",
    )
    duration_ms: Optional[int] = Field(
        None,
        description="Total duration in milliseconds (crawl + pagespeed)",
    )
    error: Optional[str] = Field(
        None,
        description="Error message if the check failed",
    )
    result_url: str = Field(
        ...,
        description="URL to fetch final results: /api/v1/lighthouse/results/{check_id}",
    )
