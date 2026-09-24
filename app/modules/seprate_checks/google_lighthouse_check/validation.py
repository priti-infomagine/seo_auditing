"""
Lighthouse check input validation.

Canonical source of allowed values for the request payload, shared between
the Pydantic schema (parse-time validation) and the Celery task / service
layer (runtime / test-time validation without an HTTP request).
"""
from typing import List, Optional
from typing import Union
import re

from app.shared.utils.url_utils import normalize_url

# ── Allowed device strategies (PageSpeed Insights `strategy` param) ─────
ALLOWED_DEVICES: tuple[str, ...] = ("mobile", "desktop")
DEFAULT_DEVICES: List[str] = list(ALLOWED_DEVICES)

# ── Allowed Lighthouse versions ─────────────────
ALLOWED_VERSIONS: tuple[str, ...] = ("1", "2", "3", "4", "5", "6", "7","8", "9", "10", "11")
DEFAULT_VERSIONS: List[str] = list(ALLOWED_VERSIONS)
_VERSION_PATTERN = re.compile(r"^[1-9][0-9]*$")

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


def normalize_devices(
    device: Union[str, List[str]]
) -> List[str]:
    """
    Normalize + validate the ``device`` request field.

    Accepts either a single string ("mobile") or a list of strings
    (["mobile", "desktop"]).  Returns a deduplicated, validated list of
    device strategies.  When ``device`` is None / empty, returns the full
    default set so behavior matches the original single-string default.
    """
    if device is None:
        return list(DEFAULT_DEVICES)

    # Single string -> wrap in a list
    if isinstance(device, str):
        devices = [device]
    elif isinstance(device, (list, tuple)):
        devices = list(device)
    else:
        raise LighthouseValidationError(
            f"device must be a string or list of strings, got {type(device).__name__}"
        )

    if len(devices) == 0:
        return list(DEFAULT_DEVICES)

    normalized: List[str] = []
    for dev in devices:
        if not isinstance(dev, str):
            raise LighthouseValidationError(
                f"device entry must be a string, got {type(dev).__name__}"
            )
        lower = dev.strip().lower()
        if lower not in ALLOWED_DEVICES:
            raise LighthouseValidationError(
                f"Invalid device '{dev}'. Allowed: {', '.join(ALLOWED_DEVICES)}"
            )
        if lower not in normalized:
            normalized.append(lower)

    return normalized

def normalize_version(version: str) -> str:
    version = version.strip().lower()

    if version.startswith("v"):
        version = version[1:]

    if not version.isdigit() or int(version) <= 0:
        raise ValueError(
            f"Invalid version '{version}'. Must be a positive integer as a string."
        )

    return version


def validate_versions(
    version: Optional[Union[str, List[str]]]
) -> Optional[List[str]]:
    """
    Validate and normalize the ``version`` field.

    Accepts:
        "11"
        "v11"
        ["11", "10", "9"]
        ["v11", "v10", "v9"]

    Returns:
        Deduplicated list of normalized version strings, or None when
        no version is specified.
    """
    if version is None:
        return None

    # Single string -> wrap in a list
    if isinstance(version, str):
        versions = [version]
    elif isinstance(version, (list, tuple)):
        versions = list(version)
    else:
        raise LighthouseValidationError(
            f"version must be a string or list of strings, "
            f"got {type(version).__name__}"
        )

    if not versions:
        return None

    normalized: List[str] = []

    for ver in versions:
        if not isinstance(ver, str):
            raise LighthouseValidationError(
                f"version entry must be a string, got {type(ver).__name__}"
            )

        stripped = ver.strip()

        # Accept both "11" and "v11"
        if stripped.lower().startswith("v"):
            stripped = stripped[1:].strip()

        if not _VERSION_PATTERN.fullmatch(stripped):
            raise LighthouseValidationError(
                f"Invalid version '{ver}'. "
                "Must be a positive integer as a string."
            )

        if stripped not in ALLOWED_VERSIONS:
            raise LighthouseValidationError(
                f"Invalid version '{ver}'. "
                f"Allowed: {', '.join(ALLOWED_VERSIONS)}"
            )

        if stripped not in normalized:
            normalized.append(stripped)

    return normalized



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
    device: Union[str, List[str]],
    category: Optional[List[str]],
    max_pages: Optional[int],
    version: Optional[Union[str, List[str]]] = None,
) -> dict:
    """
    Validate a full lighthouse check request.

    Returns a normalized dict:
        {url, device (list[str]), category (list[str]), max_pages (int), version (list[str] or None)}
    """
    return {
        "url": validate_url(url),
        "device": normalize_devices(device),
        "category": normalize_categories(category),
        "max_pages": validate_max_pages(max_pages),
        "version": validate_versions(version),
    }
