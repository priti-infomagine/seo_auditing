"""Constants for the link_analysis module.

Includes enums, severity maps, generic-anchor lists, and asset-extension
sets used across the crawler, analyzer, and recommendations layers.
"""
from __future__ import annotations

import enum
from typing import Dict, List, Set

from app.core.config import settings
from app.modules.seprate_checks.link_analysis.model import (
    FindingCategory,
    FindingType,
    LinkAnalysisSeverity,
    LinkStatusClass,
    WhereToFix,
)


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

EVIDENCE_SOURCE_CAP: int = settings.LINK_ANALYSIS_EVIDENCE_SOURCE_CAP
GENERIC_ANCHORS: Set[str] = {
    "click here", "here", "read more", "learn more", "this link",
    "more", "continue", "download", "view more", "go to", "link",
    "this page", "details", "more info", "more information",
}

ASSET_EXTENSIONS: Set[str] = {
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".rtf", ".odt", ".ods", ".odp", ".csv",
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".bmp", ".tiff", ".tif",
    # Audio / Video
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".ogg", ".webm",
    ".flv", ".wmv", ".m4a", ".m4v",
    # Archives / Binaries
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2",
    ".exe", ".dmg", ".iso", ".deb", ".rpm",
    # Styles / Scripts
    ".css", ".js",
    # Data
    ".json", ".xml", ".yaml", ".yml",
}

NON_HTTP_SCHEMES: Set[str] = {
    "mailto", "tel", "javascript", "data", "ftp", "ftps", "skype",
}

RETRYABLE_STATUS_CODES: Set[int] = {408, 425, 429, 500, 502, 503, 504}

STATUS_CLASS_MAP: Dict[LinkStatusClass, int] = {
    LinkStatusClass.OK: 200,
    LinkStatusClass.REDIRECT: 300,
    LinkStatusClass.BROKEN: 400,
    LinkStatusClass.UNVERIFIED: 0,
}

UNVERIFIED_STATUS_CODES: Set[int] = {
    401, 403, 405, 407, 429, 999,
}

UNVERIFIED_ERROR_TYPES: Set[str] = {
    "timeout", "connection_error", "tls_error", "ssrf_blocked",
}

SEVERITY_ORDER: List[LinkAnalysisSeverity] = [
    LinkAnalysisSeverity.CRITICAL,
    LinkAnalysisSeverity.HIGH,
    LinkAnalysisSeverity.MEDIUM,
    LinkAnalysisSeverity.LOW,
    LinkAnalysisSeverity.NONE,
]

SEVERITY_RANK: Dict[LinkAnalysisSeverity, int] = {
    sev: idx for idx, sev in enumerate(SEVERITY_ORDER)
}

RECOMMENDATION_CATALOG: Dict[FindingType, dict] = {
    FindingType.BROKEN_INTERNAL: {
        "title": "Fix broken internal links",
        "priority": "high",
        "where_to_fix": WhereToFix.SOURCE_PAGES.value,
    },
    FindingType.BROKEN_EXTERNAL: {
        "title": "Update or remove broken external links",
        "priority": "medium",
        "where_to_fix": WhereToFix.SOURCE_PAGES.value,
    },
    FindingType.REDIRECT_INTERNAL: {
        "title": "Update internal links to point to final URLs",
        "priority": "low",
        "where_to_fix": WhereToFix.SOURCE_PAGES.value,
    },
    FindingType.REDIRECT_EXTERNAL: {
        "title": "Update external links to final destinations",
        "priority": "low",
        "where_to_fix": WhereToFix.SOURCE_PAGES.value,
    },
    FindingType.ORPHAN: {
        "title": "Add internal links to orphan pages",
        "priority": "medium",
        "where_to_fix": WhereToFix.SOURCE_PAGES.value,
    },
    FindingType.SITEMAP_URL_ERROR: {
        "title": "Fix broken URLs in sitemap",
        "priority": "medium",
        "where_to_fix": WhereToFix.SITEMAP.value,
    },
    FindingType.DEEP_PAGE: {
        "title": "Reduce click-depth for key pages",
        "priority": "low",
        "where_to_fix": WhereToFix.CONTENT.value,
    },
    FindingType.DEAD_END_PAGE: {
        "title": "Add navigation links to dead-end pages",
        "priority": "low",
        "where_to_fix": WhereToFix.CONTENT.value,
    },
    FindingType.WEAKLY_LINKED_PAGE: {
        "title": "Strengthen internal linking for weakly-linked page",
        "priority": "low",
        "where_to_fix": WhereToFix.CONTENT.value,
    },
    FindingType.EMPTY_ANCHOR: {
        "title": "Add descriptive anchor text to links",
        "priority": "low",
        "where_to_fix": WhereToFix.SOURCE_PAGES.value,
    },
    FindingType.GENERIC_ANCHOR: {
        "title": "Replace generic anchor text with descriptive text",
        "priority": "low",
        "where_to_fix": WhereToFix.SOURCE_PAGES.value,
    },
    FindingType.NOFOLLOW_INTERNAL: {
        "title": "Remove nofollow from internal links",
        "priority": "low",
        "where_to_fix": WhereToFix.SOURCE_PAGES.value,
    },
    FindingType.INSECURE_LINK: {
        "title": "Use HTTPS for all internal links",
        "priority": "medium",
        "where_to_fix": WhereToFix.SOURCE_PAGES.value,
    },
    FindingType.EXCESSIVE_OUTLINKS: {
        "title": "Reduce number of links per page",
        "priority": "low",
        "where_to_fix": WhereToFix.CONTENT.value,
    },
}


__all__ = [
    "USER_AGENT",
    "GENERIC_ANCHORS",
    "ASSET_EXTENSIONS",
    "NON_HTTP_SCHEMES",
    "RETRYABLE_STATUS_CODES",
    "STATUS_CLASS_MAP",
    "UNVERIFIED_STATUS_CODES",
    "UNVERIFIED_ERROR_TYPES",
    "SEVERITY_ORDER",
    "SEVERITY_RANK",
    "RECOMMENDATION_CATALOG",
]
