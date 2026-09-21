"""
Pydantic schemas for URL ignore pattern API endpoints.
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class UrlIgnorePatternBase(BaseModel):
    """Base schema for pattern fields."""
    model_config = ConfigDict(from_attributes=True)
    scope: str = Field(..., description="Scope: global, performance, accessibility, bestpractices, seo")
    match_type: Optional[str] = Field(None, description="Match type: path, prefix, extension, query_param, regex, scheme, host")
    pattern: Optional[str] = Field(None, description="Pattern to match")
    reason: str = Field(..., description="Skip reason code")
    description: Optional[str] = Field(None, description="Human-readable description")
    sort_order: int = Field(0, description="Order for matching precedence")
    is_active: bool = Field(True, description="Whether pattern is active")
    is_default: bool = Field(True, description="Whether pattern is a system default")


class UrlIgnorePatternCreate(UrlIgnorePatternBase):
    """Schema for creating a pattern."""
    pass


class UrlIgnorePatternUpdate(BaseModel):
    """Schema for updating a pattern."""
    model_config = ConfigDict(from_attributes=True)
    match_type: Optional[str] = None
    pattern: Optional[str] = None
    reason: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class UrlIgnorePatternResponse(UrlIgnorePatternBase):
    """Response schema for pattern definitions."""
    id: UUID
    record_type: str = "pattern"
    created_at: str
    updated_at: str


class UrlIgnoreSkipRecordResponse(BaseModel):
    """Response schema for skip records."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    record_type: str = "skip"
    audit_id: UUID
    url: str
    normalized_url: str
    reason: str
    scope: str
    matched_pattern_id: Optional[UUID] = None
    recorded_at: str


class UrlIgnorePatternListResponse(BaseModel):
    """Response for listing patterns."""
    total: int
    patterns: List[UrlIgnorePatternResponse]


class UrlIgnoreSkipListResponse(BaseModel):
    """Response for listing skip records."""
    total: int
    skips: List[UrlIgnoreSkipRecordResponse]


class SkipBreakdownResponse(BaseModel):
    """Skip reason breakdown for an audit."""
    audit_id: str
    total_skipped: int
    by_reason: Dict[str, int]
    by_scope: Dict[str, int]


class UrlIgnorePatternDisableRequest(BaseModel):
    """Request to disable a pattern."""
    pattern_ids: List[UUID] = Field(..., description="Pattern IDs to disable")