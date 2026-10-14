"""Pydantic schemas for the SERP rank check API."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RankCheckRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=700)
    domain: str = Field(min_length=1, max_length=253)
    location: str = Field(min_length=1, max_length=200)
    language: str = Field(min_length=1, max_length=100)
    device: Literal["desktop", "mobile"] = "desktop"
    depth: int = Field(default=10, ge=10, le=200)
    include_preview: bool = True

    @field_validator("keyword", "domain", "location", "language")
    @classmethod
    def strip_input(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value


class RankCheckCreateResponse(BaseModel):
    id: UUID
    status: str


class SerpMatch(BaseModel):
    position: int | None = None
    absolute_position: int | None = None
    url: str = ""
    title: str = ""


class SerpTopResult(BaseModel):
    position: int | None = None
    domain: str = ""
    url: str = ""
    title: str = ""
    snippet: str = ""


class RankCheckResult(BaseModel):
    found: bool
    best_position: int | None = None
    best_absolute_position: int | None = None
    matches: list[SerpMatch] = Field(default_factory=list)
    serp_features: list[str] = Field(default_factory=list)
    top_results: list[SerpTopResult] = Field(default_factory=list)
    partial: bool = False


class RankCheckStatusResponse(BaseModel):
    id: UUID
    keyword: str
    domain: str
    location: str
    language: str
    device: str
    depth: int
    include_preview: bool
    status: str
    result: RankCheckResult | None = None
    preview_status: str
    preview_html_url: str | None = None
    preview_image_url: str | None = None
    error_code: str | None = None
    provider_cost: float | None = None
    created_at: str | None = None
    updated_at: str | None = None


class RankCheckListResponse(BaseModel):
    items: list[RankCheckStatusResponse]
    total: int
    limit: int
    offset: int


class SERPResponseSchema(BaseModel):
    """Unified response model for the synchronous SERP rank-check endpoint."""

    audit_id: str
    keyword: str
    domain: str
    location: str
    language: str
    device: str
    position: int | None
    ranking_url: str | None
    status: str
    checked_at: str


# Backward-compatible alias
SERPRequestSchema = RankCheckRequest
