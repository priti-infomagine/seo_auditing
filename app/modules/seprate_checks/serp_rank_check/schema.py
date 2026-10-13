"""Pydantic schemas for the SERP rank check API."""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RankCheckRequest(BaseModel):
    keyword: str
    domain: str
    location_code: int
    language_code: str
    device: str
    depth: int
    include_preview: bool = True


class RankCheckCreateResponse(BaseModel):
    id: UUID
    status: str


class SerpMatch(BaseModel):
    position: Optional[int] = None
    absolute_position: Optional[int] = None
    url: str = ""
    title: str = ""


class SerpTopResult(BaseModel):
    position: Optional[int] = None
    domain: str = ""
    url: str = ""
    title: str = ""
    snippet: str = ""


class RankCheckResult(BaseModel):
    found: bool
    best_position: Optional[int] = None
    best_absolute_position: Optional[int] = None
    matches: list[SerpMatch] = Field(default_factory=list)
    serp_features: list[str] = Field(default_factory=list)
    top_results: list[SerpTopResult] = Field(default_factory=list)
    partial: bool = False


class RankCheckStatusResponse(BaseModel):
    id: UUID
    keyword: str
    domain: str
    location_code: int
    language_code: str
    device: str
    depth: int
    include_preview: bool
    status: str
    result: Optional[RankCheckResult] = None
    preview_status: str
    preview_html_url: Optional[str] = None
    preview_image_url: Optional[str] = None
    error_code: Optional[str] = None
    provider_cost: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RankCheckListResponse(BaseModel):
    items: list[RankCheckStatusResponse]
    total: int
    limit: int
    offset: int


class SerpLocationResponse(BaseModel):
    location_code: int
    name: str
    country_iso: Optional[str] = None
    location_type: Optional[str] = None


class SerpLocationListResponse(BaseModel):
    items: list[SerpLocationResponse]
    total: int
    limit: int
    offset: int


class SerpLanguageResponse(BaseModel):
    language_code: str
    name: str


class SerpLanguageListResponse(BaseModel):
    items: list[SerpLanguageResponse]
    total: int
    limit: int
    offset: int
