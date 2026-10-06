from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from .model import BacklinkCheckStatus
from app.modules.seprate_checks.meta_check.validation import normalize_target_url


class BacklinkCheckRequest(BaseModel):
    target: str = Field(..., min_length=1, description="Domain or website URL")
    evidence_limit: int = Field(default=100, ge=1, le=1000)

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        _, domain = normalize_target_url(value)
        return domain


class BacklinkMetrics(BaseModel):
    target: str
    rank: int
    backlinks: int
    referringDomains: int
    referringMainDomains: int
    spamScore: int
    brokenBacklinks: int
    referringPages: int


class BacklinkEvidence(BaseModel):
    rank: list[str] = Field(default_factory=list)
    backlinks: list[str] = Field(default_factory=list)
    referringDomains: list[str] = Field(default_factory=list)
    referringMainDomains: list[str] = Field(default_factory=list)
    spamScore: list[str] = Field(default_factory=list)
    brokenBacklinks: list[str] = Field(default_factory=list)
    referringPages: list[str] = Field(default_factory=list)


class BacklinkReportItem(BaseModel):
    data: BacklinkMetrics
    cost: float
    evidence: BacklinkEvidence


class BacklinkCheckResponse(BaseModel):
    check_id: UUID
    target: str
    status: BacklinkCheckStatus
    result: list[BacklinkReportItem] = Field(default_factory=list)
    cost: Optional[float] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BacklinkCheckListResponse(BaseModel):
    items: list[BacklinkCheckResponse]
    total: int
