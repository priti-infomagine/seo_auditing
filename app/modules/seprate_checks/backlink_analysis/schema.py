from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from .model import BacklinkCheckStatus
from app.modules.seprate_checks.meta_check.validation import normalize_target_url


class BacklinkCheckRequest(BaseModel):
    target: str = Field(..., min_length=1, description="Domain or website URL")

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        _, domain = normalize_target_url(value)
        return domain


class BacklinkEvidence(BaseModel):
    referringPages: list[str] = Field(default_factory=list, max_length=5)
    brokenBacklinks: list[str] = Field(default_factory=list, max_length=5)


class BacklinkReport(BaseModel):
    domain: str
    domainRank: int | None = None
    backlinks: int | None = None
    referringDomains: int | None = None
    referringMainDomains: int | None = None
    referringPages: int | None = None
    brokenBacklinks: int | None = None
    backlinksSpamScore: int | None = None
    cost: float | None = None
    evidence: BacklinkEvidence = Field(default_factory=BacklinkEvidence)


class BacklinkCheckResponse(BaseModel):
    check_id: UUID
    target: str
    status: BacklinkCheckStatus
    result: BacklinkReport | None = None
    cost: Optional[float] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BacklinkCheckListResponse(BaseModel):
    items: list[BacklinkCheckResponse]
    total: int
