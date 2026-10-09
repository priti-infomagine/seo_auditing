from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RedirectUrlCheckRequest(BaseModel):
    domain: str = Field(min_length=1, description="Domain or website URL to audit")
    max_urls: int = Field(default=5, ge=1, le=100)
    max_depth: int = Field(default=5, ge=0, le=8)
    max_hops: int = Field(default=10, ge=0, le=20)

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("domain must not be empty")
        if "://" not in cleaned:
            cleaned = f"https://{cleaned}"
        try:
            parts = urlsplit(cleaned)
            hostname = parts.hostname
            port = parts.port
        except ValueError as exc:
            raise ValueError("domain must be a valid HTTP or HTTPS URL") from exc
        if (
            parts.scheme.lower() not in {"http", "https"}
            or not hostname
            or parts.username
            or parts.password
            or port not in {None, 80, 443}
        ):
            raise ValueError("domain must be a valid HTTP or HTTPS URL")
        try:
            hostname = hostname.encode("idna").decode("ascii").lower().rstrip(".")
        except UnicodeError as exc:
            raise ValueError("domain contains an invalid hostname") from exc
        formatted_host = f"[{hostname}]" if ":" in hostname else hostname
        netloc = f"{formatted_host}:{port}" if port else formatted_host
        return urlunsplit((parts.scheme.lower(), netloc, "/", "", ""))


class RedirectHop(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str
    status: int | None = None
    status_text: str | None = Field(default=None, alias="statusText")
    location: str | None = None
    resolved: str | None = None
    latency_ms: int | None = Field(default=None, alias="latencyMs")
    headers: list[dict[str, str]] = Field(default_factory=list)


class RedirectUrlResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str
    hops: list[RedirectHop] = Field(default_factory=list)
    redirects: int = 0
    final_url: str | None = Field(default=None, alias="finalUrl")
    final_status: int | None = Field(default=None, alias="finalStatus")
    error: str | None = None
    error_type: str | None = None
    latency_ms: int | None = None
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
    crawl_depth: int | None = None


class RedirectGraphNode(BaseModel):
    id: str
    url: str
    kind: Literal["page", "redirect_target"]
    status: int | None = None
    error: str | None = None


class RedirectGraphEdge(BaseModel):
    source: str
    target: str
    kind: Literal["link", "redirect"]
    status: int | None = None
    hop: int | None = None


class RedirectGraph(BaseModel):
    nodes: list[RedirectGraphNode] = Field(default_factory=list)
    edges: list[RedirectGraphEdge] = Field(default_factory=list)


class RedirectFinding(BaseModel):
    code: str
    severity: Literal["low", "medium", "high"]
    status: Literal["pass", "warning", "fail"]
    message: str
    target_url: str
    evidence: str | None = None
    redirect_count: int = 0
    final_status: int | None = None


class RedirectRecommendation(BaseModel):
    code: str
    priority: Literal["critical", "high", "medium", "low", "info"]
    title: str
    message: str
    fix: str
    where_to_fix: Literal["source_pages", "server_config", "sitemap", "content", "cms"]
    evidence: str | None = None


class RedirectSummary(BaseModel):
    total_urls: int = 0
    redirects_found: int = 0
    redirect_chains: int = 0
    broken: int = 0
    loops: int = 0
    internal_redirects: int = 0
    external_redirects: int = 0
    total_redirect_hops: int = 0
    hop_limit_exceeded: int = 0
    meta_refresh: int = 0
    insecure: int = 0
    by_status_class: dict[str, int] = Field(
        default_factory=lambda: {"ok": 0, "redirect": 0, "broken": 0, "unverified": 0}
    )


class RedirectCheckQueuedResponse(BaseModel):
    check_id: UUID
    task_id: str | None = None
    domain: str
    status: str = "queued"
    max_urls: int
    max_depth: int = 5
    max_hops: int = 10
    status_url: str
    stream_url: str


class RedirectCheckStatusResponse(BaseModel):
    check_id: UUID
    domain: str
    status: str
    progress: dict[str, Any] = Field(default_factory=dict)
    discovered_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    max_depth: int = 5
    max_hops: int = 10
    error: str | None = None


class RedirectCheckResultResponse(BaseModel):
    check_id: UUID
    domain: str
    status: str
    total_checked: int = 0
    discovered_count: int = 0
    max_depth: int = 5
    max_hops: int = 10
    results: list[RedirectUrlResult] = Field(default_factory=list)
    graph: RedirectGraph = Field(default_factory=RedirectGraph)
    findings: list[RedirectFinding] = Field(default_factory=list)
    recommendations: list[RedirectRecommendation] = Field(default_factory=list)
    discovery_errors: list[str] = Field(default_factory=list)
    summary: RedirectSummary = Field(default_factory=RedirectSummary)
    overall_status: str = "unverified"
    severity: str = "none"
    error: str | None = None
    cost_seconds: float | None = None
    checked_at: str | None = None
