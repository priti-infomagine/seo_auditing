"""
Core SEO Crawler Pipeline module.

Public API:
    CoreSEOCrawlerService  — main orchestrator for full audits
    crawl_page_task        — Celery task for single-page crawl
    run_audit              — Celery task for full audit
    AuditConfig            — pydantic request schema
    router                 — FastAPI router with /crawl, /status, /report, /rules, /ws
"""
from __future__ import annotations

from typing import Any

from .config import CoreSEOConfig
from .crawler import Crawler
from .error import (
    CoreSEOError,
    CrawlError,
    ValidationError,
    register_validation_handler,
)
from .events import EventBus
from .normalizer import AuditNormalizer, PageNormalizer, normalize_report
from .page_discoverer import PageDiscoverer
from .page_parser import PageParser
from .pipeline import CoreSEOCrawlerService
from .router import router as core_seo_router
from .rules.base import BaseRule
from .rules.checks import (
    CanonicalAndNoindexConflictRule,
    CanonicalHeaderValidationRule,
    CanonicalLoopDetectionRule,
    CanonicalNotPointingToHomepageRule,
    CanonicalProtocolMatchRule,
    CanonicalURLPresentRule,
    CanonicalURLValidRule,
    ConflictingCanonicalURLsRule,
    FaviconPresentRule,
    H1TagPresentRule,
    MetaDescriptionLengthRule,
    MetaDescriptionPresentRule,
    NoSnippetBlockingRule,
    RobotsMetaDirectivesRule,
    SingleH1TagRule,
    TitleTagLengthRule,
    TitleTagPresentRule,
    ViewportMetaTagRule,
)
from .rules.registry import RuleRegistry
from .schema import (
    AuditConfig,
    AuditReportResponse,
    CrawlStartedResponse,
    CrawlStatusResponse,
    RequestSchema,
    PageScoreSchema,
    RuleResultSchema,
)
from .summary import AuditSummary, PageSummary, summarize_audit, summarize_page
from .storage import WriteBehindStore
from .tasks import crawl_page_inline, crawl_page_task, run_audit, run_audit_inline
from .url_normalizer import URLNormalizer

# Content category exports are resolved lazily at attribute access time
# to avoid a circular import: core_seo.__init__ → content.__init__ →
# content.config → core_seo.__init__ (already in progress).
_LAZY_CONTENT_EXPORTS = {
    "ContentCrawlerService": "pipeline",
    "ContentConfig": "pipeline",
    "ContentEventBus": "events",
    "ContentRuleRegistry": "pipeline",
    "default_content_registry": "pipeline",
}


def __getattr__(name: str):
    if name in _LAZY_CONTENT_EXPORTS:
        module_name = _LAZY_CONTENT_EXPORTS[name]
        if module_name == "pipeline":
            from ..content.pipeline import ContentCrawlerService, ContentConfig
            from ..content.events import ContentEventBus
            from ..content.rules.registry import ContentRuleRegistry, default_content_registry
            _exports = {
                "ContentCrawlerService": ContentCrawlerService,
                "ContentConfig": ContentConfig,
                "ContentEventBus": ContentEventBus,
                "ContentRuleRegistry": ContentRuleRegistry,
                "default_content_registry": default_content_registry,
            }
            if name in _exports:
                globals()[name] = _exports[name]
                return _exports[name]
        elif module_name == "events":
            from ..content.events import ContentEventBus
            globals()["ContentEventBus"] = ContentEventBus
            return ContentEventBus
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def register_with_app(app: Any) -> None:
    """Register all Core SEO routes and exception handlers on a FastAPI app."""
    from fastapi import FastAPI

    if isinstance(app, FastAPI):
        app.include_router(core_seo_router)
        register_validation_handler(app)


__all__ = [
    # Core
    "CoreSEOCrawlerService",
    "CoreSEOConfig",
    "EventBus",
    "Crawler",
    "PageDiscoverer",
    "PageParser",
    "URLNormalizer",
    "AuditNormalizer",
    "PageNormalizer",
    "normalize_report",
    # Summary
    "AuditSummary",
    "PageSummary",
    "summarize_audit",
    "summarize_page",
    # Rules
    "BaseRule",
    "RuleRegistry",
    # All 18 checks
    "TitleTagPresentRule",
    "TitleTagLengthRule",
    "MetaDescriptionPresentRule",
    "MetaDescriptionLengthRule",
    "H1TagPresentRule",
    "SingleH1TagRule",
    "CanonicalURLPresentRule",
    "CanonicalURLValidRule",
    "CanonicalLoopDetectionRule",
    "CanonicalNotPointingToHomepageRule",
    "CanonicalProtocolMatchRule",
    "CanonicalAndNoindexConflictRule",
    "CanonicalHeaderValidationRule",
    "ConflictingCanonicalURLsRule",
    "ViewportMetaTagRule",
    "FaviconPresentRule",
    "RobotsMetaDirectivesRule",
    "NoSnippetBlockingRule",
    # Schema
    "AuditConfig",
    "CrawlStartedResponse",
    "CrawlStatusResponse",
    "AuditReportResponse",
    "RuleResultSchema",
    "PageScoreSchema",
    "RequestSchema",
    # Errors
    "CoreSEOError",
    "CrawlError",
    "ValidationError",
    "register_validation_handler",
    # Tasks
    "crawl_page_task",
    "run_audit",
    "crawl_page_inline",
    "run_audit_inline",
    # Storage / DB
    "WriteBehindStore",
    # Router
    "core_seo_router",
    # Registration
    "register_with_app",
    # Content category (imported lazily — see note above)
    "ContentCrawlerService",
    "ContentConfig",
    "ContentEventBus",
    "ContentRuleRegistry",
    "default_content_registry",
]
