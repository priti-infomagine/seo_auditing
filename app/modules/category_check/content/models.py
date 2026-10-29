"""
Data models for the Content category check pipeline.

ContentEventType uses the same string values as CoreSEOEventType so that
both categories emit compatible event types. A separate enum class allows
the ContentEventBus to reference its own type namespace while remaining
wire-compatible with core_seo events.

ContentPipelineEvent is a structurally identical mirror of core_seo's
PipelineEvent but uses its own class so the content EventBus operates
on a distinct type.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.datetime_utils import utc_now


class ContentEventType(str, Enum):
    """Types of events emitted during the Content check pipeline.

    Uses identical string values to CoreSEOEventType for wire compatibility.
    """

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
class ContentPipelineEvent:
    """An event emitted at a content pipeline stage.

    Structurally identical to core_seo's PipelineEvent. Kept as a separate
    class so ContentEventBus operates on its own type namespace.
    """

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


# Re-export shared dataclass models to avoid duplication.
# These are structurally identical to core_seo's models.
from app.modules.category_check.core_seo.models import (  # noqa: E402
    AuditReport,
    CrawlResult,
    DiscoveredURL,
    HeadingInfo,
    ImageInfo,
    LinkInfo,
    NormalizedResult,
    PageResult,
    PageScore,
    ParsedPage,
    RuleResult,
    Severity,
)

__all__ = [
    "AuditReport",
    "ContentEventType",
    "ContentPipelineEvent",
    "CrawlResult",
    "DiscoveredURL",
    "HeadingInfo",
    "ImageInfo",
    "LinkInfo",
    "NormalizedResult",
    "PageResult",
    "PageScore",
    "ParsedPage",
    "RuleResult",
    "Severity",
]
