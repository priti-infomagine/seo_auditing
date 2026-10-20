"""
Core SEO Crawler Pipeline module.

Public API:
    CoreSEOCrawlerService  — main orchestrator for full audits
    crawl_page_task        — Celery task for single-page crawl
    run_audit              — Celery task for full audit
    AuditConfig            — pydantic request schema
    router                 — FastAPI router with /crawl, /status, /report, /rules

Example usage:

    # Inline (no Celery):
    service = CoreSEOCrawlerService()
    audit_id = await service.start_audit("https://example.com")

    # Via Celery:
    from app.modules.category_check.core_seo.tasks import run_audit
    run_audit.delay(start_url="https://example.com", audit_id=audit_id)
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
)
from .scorer import ScoreCalculator, Scorer
from .storage import WriteBehindStore
from .tasks import crawl_page_inline, crawl_page_task, run_audit, run_audit_inline
from .url_normalizer import URLNormalizer


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
    "Scorer",
    "ScoreCalculator",
    "URLNormalizer",
    "AuditNormalizer",
    "PageNormalizer",
    "normalize_report",
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
]
