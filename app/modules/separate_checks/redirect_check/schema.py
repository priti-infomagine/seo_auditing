"""Pydantic schemas for the redirect check API."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RedirectCheckRequest(BaseModel):
    """Request to queue a domain-level redirect check."""

    domain: str = Field(
        ...,
        min_length=1,
        description="Website origin to discover and check (e.g. https://example.com)",
    )
    max_urls: int = Field(default=50, ge=1, le=50, description="Maximum URLs to check")
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
    """One request in the chain. ``location`` is the absolute URL the hop leads to."""

    url: str
    status: int | None = None
    location: str | None = None
    kind: Literal["http", "client"] | None = Field(
        default=None,
        description="http = 3xx + Location header; client = meta refresh / JS navigation seen by the browser",
    )
    latency_ms: int | None = None


class RedirectUrlResult(BaseModel):
    """Redirect check result for a single URL (no duplicated or derived-only fields)."""

    url: str
    state: Literal["ok", "redirected", "broken", "unreachable", "loop", "too_many_redirects"] = "ok"
    redirect_count: int = Field(default=0, description="3xx hops + confirmed client-side redirects; the final 200 is not counted")
    redirect_type: Literal["none", "internal", "external"] = "none"
    final_url: str | None = None
    final_status: int | None = None
    error: str | None = None
    error_type: str | None = None
    client_redirect: Literal["suspected", "confirmed"] | None = None
    hops: list[RedirectHop] = Field(default_factory=list)
    canonical: str | None = None
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
    client_redirects: int = 0
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
    message: str | None = None
    fix: str
    where_to_fix: str = "server_config"
    evidence: str | None = None
    affected_count: int = 0
    examples: list[str] = Field(default_factory=list)


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
