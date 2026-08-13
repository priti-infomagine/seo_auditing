"""
Crawler Core Data Types and State Enum.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID


class CrawlStateEnum(str, Enum):
    DISCOVERED = "discovered"
    QUEUED = "queued"
    FETCHING = "fetching"
    FETCHED = "fetched"
    RENDERING = "rendering"
    RENDERED = "rendered"
    EXTRACTING = "extracting"
    PERSISTING = "persisting"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(slots=True)
class RedirectInfo:
    url: str
    status_code: int
    location: Optional[str] = None


@dataclass(slots=True)
class FetchResult:
    url: str
    normalized_url: str
    status_code: int
    content: bytes
    headers: Dict[str, str]
    final_url: str
    content_type: Optional[str]
    content_length: int
    response_time_ms: int
    redirect_chain: List[RedirectInfo]
    success: bool
    error: Optional[str] = None
    error_type: Optional[str] = None
    render_mode: str = "http"
    render_reason: str = "default_http"


@dataclass(slots=True)
class RenderResult:
    requested_url: str
    final_url: str
    status_code: int
    html: str
    headers: Dict[str, str]
    response_time_ms: int
    render_mode: str = "browser"
    render_reason: str = "insufficient_http_content"
    console_errors: List[str] = field(default_factory=list)
    js_errors: List[str] = field(default_factory=list)
    failed_requests: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class DiscoveredURL:
    url: str
    normalized_url: str
    source_url: str
    source_type: str  # seed, html_link, sitemap, robots, canonical, hreflang, rendered_dom
    depth: int = 0
    parent_page_id: Optional[UUID] = None
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
