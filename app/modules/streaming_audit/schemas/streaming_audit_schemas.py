from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class StreamingAuditCreateRequest(BaseModel):
    url: str = Field(..., min_length=1, description="Seed URL to analyze")
    max_pages: int = Field(default=100, ge=1, le=5000)
    max_depth: int = Field(default=3, ge=0, le=10)
    concurrency: int = Field(default=5, ge=1, le=50)
    browser_concurrency: int = Field(default=2, ge=1, le=20)
    request_timeout: float = Field(default=30.0, gt=0)
    full_pipeline: bool = Field(default=False)


class StreamingAuditQueuedResponse(BaseModel):
    success: bool = True
    status: Literal["queued", "processing", "partial"] = "queued"
    message: str
    audit_id: str
    task_id: str
    status_url: str
    result_url: str


class StreamingAuditStatusResponse(BaseModel):
    audit_id: str
    status: str
    discovered_count: int = 0
    queued_count: int = 0
    processing_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    summary: dict[str, Any] | None = None


class StreamingPageResultPayload(BaseModel):
    page_score: float | None = None
    processed_url: str
    canonical_url: str | None = None
    status: str = "completed"
    rule_findings: list[dict[str, Any]] = Field(default_factory=list)
    discovered_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
