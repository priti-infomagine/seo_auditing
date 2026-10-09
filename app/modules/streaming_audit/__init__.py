"""Experimental streaming page-level SEO audit architecture.

This package intentionally isolates the experimental page-by-page execution
model from the existing production crawl/analyze pipeline.
"""

__all__ = ["StreamingAuditRun", "StreamingPageResult"]
