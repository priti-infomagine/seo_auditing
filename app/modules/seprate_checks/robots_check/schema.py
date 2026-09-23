"""
Pydantic schemas for the robots check API.

Follows the *Request / Response / Finding* shape convention established by
``google_lighthouse_check/schema.py``.
"""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.seprate_checks.robots_check.validation import validate_domain


class RobotsCheckRequest(BaseModel):
    domain: str = Field(
        ..., description="The bare domain to check robots.txt for (e.g. 'example.com')"
    )

    @field_validator("domain")
    @classmethod
    def _validate_domain(cls, v: str) -> str:
        return validate_domain(v)


class RobotsFinding(BaseModel):
    code: str = Field(..., description="Stable machine identifier for the finding, e.g. 'robots_site_block'")
    severity: str = Field(..., description="none | low | medium | high | critical")
    status: str = Field(..., description="pass | warning | fail | not_applicable")
    message: str = Field(..., description="Human-readable description of the finding")
    evidence: Optional[str] = Field(default=None, description="Supporting evidence string")


class RobotsCheckResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(..., description="Unique identifier for this robots check result")
    domain: str = Field(..., description="The domain that was checked")
    checked_at: Optional[str] = Field(default=None, description="ISO timestamp of the check")

    exists: bool = Field(..., description="Whether a robots.txt file was found")
    status_code: Optional[int] = Field(default=None, description="HTTP status code of the fetch")
    fetch_status: str = Field(..., description="success | not_found | unreachable")
    fetch_url: Optional[str] = Field(default=None, description="Final URL after redirects")
    size_bytes: Optional[int] = Field(default=None, description="Response body size in bytes")

    sitemaps_declared: list[str] = Field(
        default_factory=list, description="Sitemap URLs declared in robots.txt"
    )
    sitemap_reachability: list[dict] = Field(
        default_factory=list, description="Reachability results for each declared sitemap"
    )
    syntax_warnings: list[str] = Field(
        default_factory=list, description="Non-fatal warnings detected during parsing"
    )

    findings: list[RobotsFinding] = Field(
        default_factory=list, description="List of individual findings"
    )

    overall_status: str = Field(..., description="pass | warning | fail | not_applicable")
    severity: str = Field(..., description="Aggregated severity: none | low | medium | high | critical")

    why: Optional[str] = Field(default=None, description="Impact explanation")
    recommendation: Optional[str] = Field(default=None, description="Suggested fix")
