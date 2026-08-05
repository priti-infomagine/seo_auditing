"""
Rule result models for the scorer service.
"""
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Issue severity levels."""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    PASSED = "passed"


class RuleResult(BaseModel):
    """Result of a single rule check."""
    rule_id: str = Field(..., description="Unique rule identifier")
    name: str = Field(..., description="Human-readable rule name")
    category: str = Field(..., description="Rule category (e.g., 'on_page', 'technical')")
    severity: Severity = Field(..., description="Issue severity level")
    passed: bool = Field(..., description="Whether the rule passed")
    score_impact: float = Field(default=0.0, description="Impact on overall score (negative = penalty)")
    message: str = Field(..., description="Result message")
    recommendation: Optional[str] = Field(None, description="How to fix the issue")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional rule-specific data")
    tags: List[str] = Field(default_factory=list, description="Rule tags for filtering")


class CategoryScore(BaseModel):
    """Score breakdown for a category."""
    category: str = Field(..., description="Category name")
    score: float = Field(..., description="Category score (0-100)")
    max_score: float = Field(default=100.0, description="Maximum possible score")
    weight: float = Field(..., description="Weight in overall score calculation")
    rules_checked: int = Field(..., description="Total rules checked")
    rules_passed: int = Field(..., description="Rules that passed")
    rules_failed: int = Field(..., description="Rules that failed")
    issues: List[RuleResult] = Field(default_factory=list, description="Failed rules")
    warnings: List[RuleResult] = Field(default_factory=list, description="Warning rules")
    passed_rules: List[RuleResult] = Field(default_factory=list, description="Passed rules")


class SeoScore(BaseModel):
    """Complete SEO score report."""
    overall_score: float = Field(..., description="Overall SEO score (0-100)")
    grade: str = Field(..., description="Letter grade (A-F)")
    categories: Dict[str, CategoryScore] = Field(..., description="Score breakdown by category")
    total_rules: int = Field(..., description="Total rules evaluated")
    total_passed: int = Field(..., description="Total rules passed")
    total_failed: int = Field(..., description="Total rules failed")
    critical_issues: int = Field(..., description="Number of critical issues")
    warnings: int = Field(..., description="Number of warnings")
    summary: str = Field(..., description="Human-readable summary")
    top_issues: List[RuleResult] = Field(..., description="Top priority issues to fix")