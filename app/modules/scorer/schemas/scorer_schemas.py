"""
Pydantic schemas for Scorer API.
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class RuleResultSchema(BaseModel):
    """Schema for individual rule result."""
    rule_id: str
    name: str
    category: str
    severity: str
    passed: bool
    score_impact: float
    message: str
    recommendation: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    tags: List[str] = []


class CategoryScoreSchema(BaseModel):
    """Schema for category score breakdown."""
    category: str
    score: float
    max_score: float = 100.0
    weight: float
    rules_checked: int
    rules_passed: int
    rules_failed: int
    issues: List[RuleResultSchema] = []
    warnings: List[RuleResultSchema] = []
    passed_rules: List[RuleResultSchema] = []


class SeoScoreResponse(BaseModel):
    """Schema for SEO score API response."""
    overall_score: float
    grade: str
    categories: Dict[str, CategoryScoreSchema]
    total_rules: int
    total_passed: int
    total_failed: int
    critical_issues: int
    warnings: int
    summary: str
    top_issues: List[RuleResultSchema]


class ScoreRequest(BaseModel):
    """Schema for score request."""
    url: Optional[str] = Field(None, description="URL to score")
    parsed_data: Optional[Dict[str, Any]] = Field(None, description="Parsed data to score")
    domain: Optional[str] = Field(None, description="Domain to load crawl data from")
    test_number: Optional[int] = Field(None, description="Specific test number (latest if None)")


class RuleStatisticsResponse(BaseModel):
    """Schema for rule statistics."""
    total_rules: int
    categories: Dict[str, Dict[str, Any]]