"""Pydantic schemas for the SERP rank check API."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RankCheckRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=700)
    domain: str | None = Field(default=None, max_length=253)
    location: str = Field(min_length=1, max_length=200)
    location_code: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Optional DataForSEO location_code. When provided it targets "
            "the exact location (e.g. a specific City) and takes "
            "precedence over location_name; location_name is still "
            "required for display and backward compatibility."
        ),
    )
    language: str = Field(min_length=1, max_length=100)
    device: Literal["desktop", "mobile"] = "desktop"
    depth: Literal[10, 20, 50, 100] = 10

    @field_validator("keyword", "location", "language")
    @classmethod
    def strip_input(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @field_validator("domain")
    @classmethod
    def normalize_domain_input(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class RankCheckCreateResponse(BaseModel):
    id: UUID
    status: str


class SerpMatch(BaseModel):
    position: int | None = None
    absolute_position: int | None = None
    url: str = ""
    domain: str = ""
    title: str = ""


class SerpTopResult(BaseModel):
    position: int | None = None
    domain: str = ""
    url: str = ""
    title: str = ""
    snippet: str = ""


class RankCheckResult(BaseModel):
    found: bool
    status: str = "pending"
    best_position: int | None = None
    best_absolute_position: int | None = None
    matches: list[SerpMatch] = Field(default_factory=list)
    serp_features: list[str] = Field(default_factory=list)
    top_results: list[SerpTopResult] = Field(default_factory=list)
    partial: bool = False


class RankCheckStatusResponse(BaseModel):
    id: UUID
    keyword: str
    domain: str | None = None
    location: str
    location_code: int | None = None
    language: str
    device: str
    depth: int
    deep_tracking: bool
    status: str
    result: RankCheckResult | None = None
    error_code: str | None = None
    provider_cost: float | None = None
    created_at: str | None = None
    updated_at: str | None = None


class RankCheckListResponse(BaseModel):
    items: list[RankCheckStatusResponse]
    total: int
    limit: int
    offset: int


class LocationOption(BaseModel):
    """A single DataForSEO location returned by the `/locations` search."""

    code: int
    name: str
    type: str | None = None


class SERPResponseSchema(BaseModel):
    """Unified response model for the synchronous SERP rank-check endpoint."""

    audit_id: str
    keyword: str
    domain: str | None = None
    location: str
    location_code: int | None = None
    language: str
    device: str
    deep_tracking: bool
    position: int | None
    ranking_url: str | None
    status: str
    checked_at: str


# Backward-compatible alias
SERPRequestSchema = RankCheckRequest
