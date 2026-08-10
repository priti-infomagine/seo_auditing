"""
Technical analysis service - analyzes technical HTTP/network evidence.

This service:
1. Receives TechnicalFacts from extractor
2. Generates content checksum
3. Classifies security headers
4. Collects performance indicators
5. Returns TechnicalAnalysisResult

It does NOT:
- Write to PostgreSQL
- Calculate SEO scores
"""
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from app.modules.crawler.extractors.technical_extractor import TechnicalFacts
from app.shared.utils.checksum import generate_checksum


@dataclass
class TechnicalAnalysisResult:
    """Structured technical analysis result."""
    status_code: int = 0
    content_type: str = ""
    content_length: int = 0
    response_time_ms: int = 0
    headers: dict = field(default_factory=dict)
    redirects: list = field(default_factory=list)
    security: dict = field(default_factory=dict)
    performance: dict = field(default_factory=dict)
    accessibility: dict = field(default_factory=dict)
    json_ld: list = field(default_factory=list)
    checksum: Optional[str] = None
    is_https: bool = False


class TechnicalAnalysisService:
    """Service for technical analysis."""

    async def analyze(
        self,
        technical: TechnicalFacts,
        content_bytes: Optional[bytes] = None,
    ) -> TechnicalAnalysisResult:
        """
        Analyze technical facts.

        Args:
            technical: TechnicalFacts from technical_extractor
            content_bytes: Raw content bytes for checksum

        Returns:
            TechnicalAnalysisResult with analysis
        """
        checksum = None
        if content_bytes:
            checksum = generate_checksum(content_bytes)

        is_https = technical.headers.get("scheme", "") == "https" or str(
            technical.headers.get("content-type", "")
        ).startswith("https")

        return TechnicalAnalysisResult(
            status_code=technical.status_code,
            content_type=technical.content_type,
            content_length=technical.content_length,
            response_time_ms=technical.response_time_ms,
            headers=technical.headers,
            redirects=technical.redirects,
            security=technical.security,
            performance=technical.performance,
            accessibility=technical.accessibility,
            json_ld=technical.json_ld,
            checksum=checksum,
            is_https=is_https,
        )
