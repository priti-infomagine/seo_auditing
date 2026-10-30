"""
Data models for the Core SEO crawler pipeline.

All models are dataclasses with slots=True for memory efficiency.
These are self-contained — no imports from app.modules.crawler or
app.modules.scorer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.datetime_utils import utc_now


class Severity(str, Enum):
    """Issue severity levels for rule results."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    PASSED = "passed"
    ERROR = "error"


@dataclass(slots=True)
class DiscoveredURL:
    """A URL discovered during page discovery (sitemap or BFS)."""

    url: str
    normalized_url: str
    source_type: str = "seed"
    depth: int = 0


@dataclass(slots=True)
class CrawlResult:
    """Result of crawling a single page via Playwright."""

    url: str
    html: str = ""
    status_code: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    response_time_ms: int = 0
    final_url: str = ""
    error: str | None = None
    console_errors: list[str] = field(default_factory=list)
    js_errors: list[str] = field(default_factory=list)
    failed_requests: list[dict[str, Any]] = field(default_factory=list)
    success: bool = False


@dataclass(slots=True)
class LinkInfo:
    """Information about a single <a> link found on a page."""

    href: str
    text: str = ""
    internal: bool = False


@dataclass(slots=True)
class ImageInfo:
    """Information about a single <img> tag found on a page."""

    src: str
    alt: str = ""
    has_alt: bool = False
    width: int | None = None
    height: int | None = None


@dataclass(slots=True)
class HeadingInfo:
    """Information about a heading level."""

    level: int
    texts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedPage:
    """Fully parsed representation of a crawled page."""

    url: str
    title: str = ""
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    headings: dict[str, list[str]] = field(default_factory=dict)
    heading_counts: dict[str, int] = field(default_factory=dict)
    heading_hierarchy: list[int] = field(default_factory=list)
    links: list[LinkInfo] = field(default_factory=list)
    internal_links: list[LinkInfo] = field(default_factory=list)
    external_links: list[LinkInfo] = field(default_factory=list)
    images: list[ImageInfo] = field(default_factory=list)
    content_text: str = ""
    word_count: int = 0
    char_count: int = 0
    paragraph_count: int = 0
    content_hash: str = ""
    canonical: str = ""
    canonical_source_count: int = 0
    robots_meta: str = ""
    viewport: str = ""
    favicon_urls: list[str] = field(default_factory=list)
    structured_data: list[dict[str, Any]] = field(default_factory=list)
    open_graph: dict[str, str] = field(default_factory=dict)
    social: dict[str, Any] = field(default_factory=dict)
    charset: str = ""
    language: str = ""
    doctype: str = ""
    http_status: int = 0
    final_url: str = ""
    content_type: str = ""
    has_h1: bool = False
    has_h2: bool = False


@dataclass(slots=True)
class RuleResult:
    """Result of a single rule evaluation on a page."""

    rule_id: str
    name: str
    passed: bool = False
    severity: str = Severity.WARNING.value
    message: str = ""
    recommendation: str | None = None
    details: dict[str, Any] | None = None


@dataclass(slots=True)
class PageScore:
    """Per-page score summary (no overall/grade/category scores)."""

    url: str = ""
    passed: int = 0
    failed: int = 0
    total: int = 0
    pass_percentage: float = 0.0
    rule_results: list[RuleResult] = field(default_factory=list)


@dataclass(slots=True)
class PageResult:
    """Per-page result stored in an audit."""

    url: str
    normalized_url: str
    status_code: int = 0
    response_time_ms: int = 0
    success: bool = False
    error: str | None = None
    passed: int = 0
    failed: int = 0
    total_rules: int = 0
    pass_percentage: float = 0.0
    rule_results: list[dict[str, Any]] = field(default_factory=list)
    crawled_at: str = field(default_factory=lambda: utc_now().isoformat())


@dataclass(slots=True)
class NormalizedResult:
    """Normalized per-audit result ready for JSON serialization."""

    audit_id: str = ""
    status: str = ""
    summary: dict[str, Any] = field(default_factory=dict)
    pages: list[dict[str, Any]] = field(default_factory=list)
    content_pages: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    page_url: str = ""
    normalized_url: str = ""
    pass_percentage: float = 0.0
    issues: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""
    rule_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class AuditReport:
    """Aggregate report for an entire audit run."""

    audit_id: str = ""
    domain: str = ""
    status: str = "pending"
    start_url: str = ""
    total_pages: int = 0
    crawled_pages: int = 0
    pages_crawled: int = 0
    pages_done: int = 0
    pages_failed: int = 0
    pages_skipped: int = 0
    started_at: str = field(default_factory=lambda: utc_now().isoformat())
    completed_at: str | None = None
    total_time_seconds: float = 0.0
    page_results: list[PageResult] = field(default_factory=list)
    pages: list[PageScore] = field(default_factory=list)
    events: list[PipelineEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


class CoreSEOEventType(str, Enum):
    """Types of events emitted during the SEO crawl pipeline."""

    AUDIT_STARTED = "audit_started"
    CRAWL_STARTED = "crawl_started"
    PAGE_DISCOVERED = "page_discovered"
    PAGE_QUEUED = "page_queued"
    PAGE_STARTED = "page_started"
    FETCH_STARTED = "fetch_started"
    RENDERED = "rendered"
    PARSED = "parsed"
    RULE_CHECKED = "rule_checked"
    PAGE_COMPLETED = "page_completed"
    PAGE_FAILED = "page_failed"
    AUDIT_COMPLETED = "audit_completed"
    AUDIT_FAILED = "audit_failed"


@dataclass(slots=True)
class PipelineEvent:
    """An event emitted at a pipeline stage."""

    event_type: str
    audit_id: str
    url: str = ""
    timestamp: str = field(default_factory=lambda: utc_now().isoformat())
    data: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.data:
            self.data = self.payload
        if not self.payload:
            self.payload = self.data


__all__ = [
    "AuditReport",
    "CoreSEOEventType",
    "CrawlResult",
    "DiscoveredURL",
    "HeadingInfo",
    "ImageInfo",
    "LinkInfo",
    "NormalizedResult",
    "PageResult",
    "PageScore",
    "ParsedPage",
    "PipelineEvent",
    "RuleResult",
    "Severity",
]
