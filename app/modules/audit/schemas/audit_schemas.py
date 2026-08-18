"""
Schemas for the combined crawl + parse + score (full audit) API endpoint.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List


class AuditRequest(BaseModel):
    """Request schema for running a combined crawl + parse audit."""
    
    url: str = Field(
        ...,
        description="URL or website name to audit (e.g., 'https://example.com' or 'example.com')",
        examples=["https://example.com"]
    )
    deep_crawl: bool = Field(
        False,
        description="Mock flag: whether to simulate a deep crawl (more pages/resources)",
        examples=[False]
    )
    
    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        url = v.strip()
        if not url:
            raise ValueError("URL cannot be empty")
        
        # Auto-prepend https:// if no protocol
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        
        return url


class MockCrawlResult(BaseModel):
    """Mock result of the crawling phase."""
    
    status_code: int = Field(..., description="Mock HTTP status code")
    html_size_bytes: int = Field(..., description="Mock HTML size in bytes")
    response_time_ms: float = Field(..., description="Mock response time in milliseconds")
    pages_crawled: int = Field(..., description="Mock number of pages crawled")


class MockParseResult(BaseModel):
    """Mock result of the parsing phase."""
    
    title: str = Field(..., description="Mock extracted page title")
    meta_description: str = Field(..., description="Mock extracted meta description")
    word_count: int = Field(..., description="Mock extracted word count")
    total_links: int = Field(..., description="Mock extracted link count")
    total_images: int = Field(..., description="Mock extracted image count")
    seo_score: int = Field(..., description="Mock calculated SEO score (0-100)")
    seo_grade: str = Field(..., description="Mock SEO grade (A-F)")


class AuditResponse(BaseModel):
    """Response schema for the combined crawl + parse audit."""
    
    success: bool = Field(..., description="Whether the audit was successful")
    message: str = Field(..., description="Status message")
    url: str = Field(..., description="The audited URL")
    domain: str = Field(..., description="Extracted domain name")
    crawl: MockCrawlResult = Field(..., description="Mock crawl phase result")
    parse: MockParseResult = Field(..., description="Mock parse phase result")
    mock: bool = Field(True, description="Indicates this is a mock API result")


class AuditError(BaseModel):
    """Error response schema."""
    
    success: bool = False
    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")


class AuditAnalyzeRequest(BaseModel):
    """Request schema for running a complete crawl → parse → score audit."""
    
    url: str = Field(
        ...,
        description="URL to audit (e.g., 'https://example.com')",
        examples=["https://example.com"]
    )
    
    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        url = v.strip()
        if not url:
            raise ValueError("URL cannot be empty")
        
        # Auto-prepend https:// if no protocol
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        
        return url


class CrawlSummarySchema(BaseModel):
    """Summary of crawl phase."""
    url: str
    domain: str
    status_code: int
    response_time: float
    html_size_bytes: int
    test_number: int
    file_path: str
    crawled_at: str


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


class SeoScoreSchema(BaseModel):
    """Schema for SEO score results."""
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


class AuditAnalyzeResponse(BaseModel):
    """Response schema for the complete crawl → parse → score audit."""
    
    success: bool = Field(..., description="Whether the audit was successful")
    message: str = Field(..., description="Status message")
    url: str = Field(..., description="The audited URL")
    domain: str = Field(..., description="Extracted domain name")
    crawl: CrawlSummarySchema = Field(..., description="Crawl phase summary")
    seo_score: Dict[str, Any] = Field(..., description="SEO scoring results")
    parsed_data: Optional[Dict[str, Any]] = Field(None, description="Full parsed data")
    pages: Optional[List[Dict[str, Any]]] = Field(
        None, description="Page-centric grouping of results, one entry per crawled page"
    )


class AuditAnalyzeError(BaseModel):
    """Error response schema."""
    
    success: bool = False
    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")