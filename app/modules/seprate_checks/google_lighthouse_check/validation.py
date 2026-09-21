"""
Lighthouse check input validation.

Canonical source of allowed values for the request payload, shared between
the Pydantic schema (parse-time validation) and the Celery task / service
layer (runtime / test-time validation without an HTTP request).
"""
from typing import List, Optional

from app.shared.utils.url_utils import normalize_url

# ── Allowed device strategies (PageSpeed Insights `strategy` param) ─────
ALLOWED_DEVICES: tuple[str, ...] = ("mobile", "desktop")

# ── Allowed Lighthouse categories (PageSpeed `category` param) ──────────
ALLOWED_CATEGORIES: tuple[str, ...] = (
    "performance",
    "seo",
    "best-practices",
    "accessibility",
)

# Default when the caller omits `category` (pagespeed_client.fetch default).
DEFAULT_CATEGORIES: List[str] = list(ALLOWED_CATEGORIES)

# Reasonable upper bound for max_pages in this lightweight check flow.
MAX_PAGES_LIMIT: int = 100
MIN_PAGES: int = 1


class LighthouseValidationError(ValueError):
    """Raised when a lighthouse check input fails validation."""


def normalize_categories(category: Optional[List[str]]) -> List[str]:
    """
    Normalize + validate the ``category`` request field.

    Returns the canonical list of categories (lower-cased, validated). When
    ``category`` is None / empty, returns the full default set so that the
    behavior matches ``PagespeedClient.fetch`` (which defaults to all four).
    """
    if category is None or len(category) == 0:
        return list(DEFAULT_CATEGORIES)

    normalized: List[str] = []
    for cat in category:
        if not isinstance(cat, str):
            raise LighthouseValidationError(f"category entry must be a string, got {type(cat).__name__}")
        lower = cat.strip().lower()
        if lower not in ALLOWED_CATEGORIES:
            raise LighthouseValidationError(
                f"Invalid category '{cat}'. Allowed: {', '.join(ALLOWED_CATEGORIES)}"
            )
        normalized.append(lower)
    return normalized


def normalize_device(device: str) -> str:
    """Validate + normalize the device strategy."""
    if not isinstance(device, str):
        raise LighthouseValidationError("device must be a string")
    lower = device.strip().lower()
    if lower not in ALLOWED_DEVICES:
        raise LighthouseValidationError(
            f"Invalid device '{device}'. Allowed: {', '.join(ALLOWED_DEVICES)}"
        )
    return lower


def validate_url(url: str) -> str:
    """
    Validate the seed URL and return a normalized form.

    Raises LighthouseValidationError (ValueError subclass) on invalid input
    so the router can map it to HTTP 400.
    """
    if not isinstance(url, str) or not url.strip():
        raise LighthouseValidationError("url must be a non-empty string")
    try:
        return normalize_url(url.strip())
    except ValueError as exc:
        raise LighthouseValidationError(f"Invalid url: {exc}") from exc


def validate_max_pages(max_pages: Optional[int]) -> int:
    """Validate max_pages, returning a clamped integer."""
    if max_pages is None:
        return MAX_PAGES_LIMIT
    if not isinstance(max_pages, int) or isinstance(max_pages, bool):
        raise LighthouseValidationError("max_pages must be an integer")
    if max_pages < MIN_PAGES:
        raise LighthouseValidationError(f"max_pages must be >= {MIN_PAGES}")
    if max_pages > MAX_PAGES_LIMIT:
        raise LighthouseValidationError(f"max_pages must be <= {MAX_PAGES_LIMIT}")
    return max_pages


def validate_lighthouse_request(
    url: str,
    device: str,
    category: Optional[List[str]],
    max_pages: Optional[int],
) -> dict:
    """
    Validate a full lighthouse check request.

    Returns a normalized dict:
        {url, device, category (list[str]), max_pages (int)}
    """
    return {
        "url": validate_url(url),
        "device": normalize_device(device),
        "category": normalize_categories(category),
        "max_pages": validate_max_pages(max_pages),
    }
