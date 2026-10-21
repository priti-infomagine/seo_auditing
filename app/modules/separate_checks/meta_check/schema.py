from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from .model import MetaCheckStatus
from .validation import normalize_target_url


class MetaCheckRequest(BaseModel):
    url: str = Field(..., min_length=1)
    max_pages: int = Field(default=30, ge=1, le=500)
    max_depth: int = Field(default=3, ge=0, le=5)
    respect_robots: bool = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalize_target_url(value)
        return value.strip()


class MetaCheckQueuedResponse(BaseModel):
    check_id: UUID
    task_id: Optional[str] = None
    url: str
    domain: str
    status: MetaCheckStatus
    max_pages: int
    max_depth: int
    created_at: Optional[str] = None


class MetaFinding(BaseModel):
    code: str
    severity: str
    status: str
    message: str
    evidence: Optional[str] = None


class MetaPageResult(BaseModel):
    url: str
    status_code: Optional[int] = None
    final_url: Optional[str] = None
    content_type: Optional[str] = None
    title: str = ""
    title_length: int = 0
    meta_description: str = ""
    meta_description_length: int = 0
    error: Optional[str] = None
    metadata: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[MetaFinding] = Field(default_factory=list)


class MetaSummary(BaseModel):
    pages_discovered: int = 0
    pages_checked: int = 0
    pages_failed: int = 0
    missing_titles: int = 0
    missing_descriptions: int = 0
    total_findings: int = 0


class MetaCheckStatusResponse(BaseModel):
    check_id: UUID
    url: str
    domain: str
    status: MetaCheckStatus
    progress: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class MetaCheckResultResponse(MetaCheckStatusResponse):
    checked_at: Optional[str] = None
    overall_status: Optional[str] = None
    severity: Optional[str] = None
    summary: Optional[MetaSummary] = None
    pages: list[MetaPageResult] = Field(default_factory=list)
    findings: list[MetaFinding] = Field(default_factory=list)
    cost_seconds: Optional[float] = None