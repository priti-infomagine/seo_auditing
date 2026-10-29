"""
Content Category Check module.

Provides a Content Crawler Service that mirrors the Core SEO pipeline pattern:
discover → crawl → parse → run 13 content rules → summarize → finalize.

Events stream to a separate Redis namespace (content: prefix) so they are
isolated from core_seo events, while sharing the same audit_id for
combined WebSocket streaming.
"""
from __future__ import annotations

from typing import Any

from .config import ContentConfig, CONTENT_RULE_COUNT
from .events import ContentEventBus, ContentEventType, ContentPipelineEvent
from .page_parser import ContentPageParser
from .pipeline import ContentCrawlerService
from .rules.base import BaseRule
from .rules.checks import (
    BrokenHTMLStructureRule,
    ContentMimeTypeRule,
    ContentReadingLevelRule,
    ContentWordCountRule,
    HeadingHierarchyRule,
    HeadingLengthRule,
    KeywordStuffingRule,
    LinkDensityRule,
    MetaDescriptionPixelWidthRule,
    MetaTagsInBodyRule,
    TextToHTMLRatioRule,
    TitleH1DuplicationRule,
    TitlePixelWidthRule,
)
from .rules.registry import ContentRuleRegistry, default_content_registry
from .schema import (
    ContentAuditConfig,
    ContentAuditReportResponse,
    ContentCrawlStartedResponse,
    ContentCrawlStatusResponse,
    ContentRuleResultSchema,
    ContentPageScoreSchema,
)
from .db_models import ContentAuditCheck, ContentAuditStatus
from .storage import ContentWriteBehindStore
from .router import content_router

__all__ = [
    # Core
    "ContentCrawlerService",
    "ContentConfig",
    "ContentEventBus",
    "ContentEventType",
    "ContentPipelineEvent",
    "ContentPageParser",
    "ContentRuleRegistry",
    "BaseRule",
    "default_content_registry",
    "CONTENT_RULE_COUNT",
    # All 13 content checks
    "TextToHTMLRatioRule",
    "MetaDescriptionPixelWidthRule",
    "ContentReadingLevelRule",
    "KeywordStuffingRule",
    "HeadingHierarchyRule",
    "ContentWordCountRule",
    "HeadingLengthRule",
    "TitleH1DuplicationRule",
    "TitlePixelWidthRule",
    "BrokenHTMLStructureRule",
    "MetaTagsInBodyRule",
    "ContentMimeTypeRule",
    "LinkDensityRule",
    # Schema
    "ContentAuditConfig",
    "ContentCrawlStartedResponse",
    "ContentCrawlStatusResponse",
    "ContentAuditReportResponse",
    "ContentRuleResultSchema",
    "ContentPageScoreSchema",
    # DB
    "ContentAuditCheck",
    "ContentAuditStatus",
    # Storage
    "ContentWriteBehindStore",
    # Router
    "content_router",
    # Registration
    "register_with_app",
]


def register_with_app(app: Any) -> None:
    """Register all Content category routes on a FastAPI app."""
    from fastapi import FastAPI

    if isinstance(app, FastAPI):
        app.include_router(content_router)
