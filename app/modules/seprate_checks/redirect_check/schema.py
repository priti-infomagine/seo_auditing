"""Pydantic schemas for the redirect check API."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RedirectCheckRequest(BaseModel):
    """Request to queue a domain-level redirect check."""

    domain: str = Field(
        ...,
        min_length=1,
        description="Website origin to discover and check (e.g. https://example.com)",
    )
    max_urls: int = Field(default=500, ge=1, le=500, description="Maximum URLs to check")
    max_depth: int = Field(default=5, ge=0, le=8, description="Maximum crawl depth for URL discovery")
    max_hops: int = Field(default=10, ge=0, le=20, description="Maximum redirect hops to follow per URL")

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("domain must not be empty")
        if not cleaned.startswith(("http://", "https://")):
            cleaned = f"https://{cleaned}"
        return cleaned


class RedirectCheckQueuedResponse(BaseModel):
    """Returned immediately upon queuing the check (HTTP 202)."""

    check_id: UUID
    task_id: str | None = None
    domain: str
    status: str = "queued"
    max_urls: int
    max_depth: int = 5
    max_hops: int = 10
    created_at: str | None = None
    status_url: str
    stream_url: str


class RedirectCheckStatusResponse(BaseModel):
    """Polling response for redirect check progress."""

    check_id: UUID
    domain: str
    status: str
    progress: dict[str, Any] | None = None
    discovered_count: int = 0
    queued_count: int = 0
    processing_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    error: str | None = None


class RedirectHop(BaseModel):
    """A single HTTP redirect hop."""

    model_config = ConfigDict(populate_by_name=True)

    url: str
    status: int | None = None
    status_text: str | None = Field(default=None, alias="statusText")
    location: str | None = None
    resolved: str | None = None
    latency_ms: int | None = Field(default=None, alias="latencyMs")
    headers: list[dict[str, Any]] = Field(default_factory=list)


class RedirectUrlResult(BaseModel):
    """Redirect chain result for a single URL."""

    model_config = ConfigDict(populate_by_name=True)

    url: str
    hops: list[RedirectHop] = Field(default_factory=list)
    redirects: int = 0
    final_url: str | None = Field(default=None, alias="finalUrl")
    final_status: int | None = Field(default=None, alias="finalStatus")
    error: str | None = None
    redirect_count: int = 0
    chain: list[dict[str, Any]] = Field(default_factory=list)
    is_redirect: bool = False
    is_internal_redirect: bool = False
    is_external_redirect: bool = False
    is_broken: bool = False
    canonical: str | None = None
    meta_refresh: str | None = None
    robots_allowed: bool = True
    in_sitemap: bool = False
    source_pages: list[str] = Field(default_factory=list)


class RedirectSummary(BaseModel):
    """Aggregated summary of all redirect check results."""

    total_urls: int = 0
    redirects_found: int = 0
    redirect_chains: int = 0
    broken: int = 0
    internal_redirects: int = 0
    external_redirects: int = 0
    loops: int = 0
    meta_refresh: int = 0
    insecure: int = 0
    by_status_class: dict[str, int] = Field(default_factory=dict)


class RedirectFinding(BaseModel):
    """A single redirect-related finding/opportunity."""

    code: str
    severity: Literal["low", "medium", "high"]
    status: Literal["pass", "warning", "fail"]
    message: str
    evidence: str | None = None
    target_url: str
    redirect_count: int = 0
    final_status: int | None = None
    recommendation: dict[str, Any] | None = None


class RedirectRecommendation(BaseModel):
    code: str
    priority: Literal["critical", "high", "medium", "low", "info"]
    title: str
    message: str
    fix: str
    where_to_fix: Literal["source_pages", "server_config", "sitemap", "content", "cms"]
    evidence: str | None = None


class RedirectCheckResultResponse(BaseModel):
    """Complete redirect check result payload."""

    check_id: UUID
    domain: str
    status: str
    total_checked: int = 0
    results: list[RedirectUrlResult] = Field(default_factory=list)
    findings: list[RedirectFinding] = Field(default_factory=list)
    recommendations: list[RedirectRecommendation] = Field(default_factory=list)
    summary: RedirectSummary | None = None
    overall_status: str | None = None
    severity: str | None = None
    cost_seconds: float | None = None
    checked_at: str | None = None
