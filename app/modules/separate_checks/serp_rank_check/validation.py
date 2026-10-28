"""Input normalization and validation for SERP rank checks."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urlparse

import tldextract

_WHITESPACE_RE = re.compile(r"\s+")

DEVICES = ("desktop", "mobile")
DEPTHS = (10, 20, 50, 100)


def normalize_keyword(raw: Any) -> str:
    """Trim and collapse internal whitespace; enforce 1-100 chars."""
    if not isinstance(raw, str):
        raise ValueError("keyword must be a string")
    normalized = _WHITESPACE_RE.sub(" ", raw.strip())
    if not normalized:
        raise ValueError("keyword must not be empty")
    if len(normalized) > 100:
        raise ValueError("keyword must be at most 100 characters")
    return normalized


def normalize_domain(raw: Any) -> str:
    """Normalize to the registrable domain (eTLD+1).

    Strips the scheme, ``www.`` prefix, port, path and query, then
    extracts the registrable domain with ``tldextract``. Invalid
    domains (IP addresses, single-label hosts, empty input) are
    rejected.
    """
    if not isinstance(raw, str):
        raise ValueError("domain must be a string")
    cleaned = raw.strip()
    if not cleaned:
        raise ValueError("domain must not be empty")

    host = cleaned
    if "://" in host:
        parsed = urlparse(host)
        host = parsed.hostname or ""
    else:
        # bare host or host/path — drop the path portion
        host = host.split("/", 1)[0]
    host = host.strip().lower()
    host = host.removeprefix("www.")
    # strip a port if present (ignore IPv6 bracket hosts)
    if ":" in host and not host.startswith("["):
        host = host.rsplit(":", 1)[0]

    if not host:
        raise ValueError(f"invalid domain: {raw!r}")

    registered = tldextract.extract(host).registered_domain
    if not registered:
        raise ValueError(f"invalid domain: {raw!r}")
    return registered


def compute_fingerprint(
    *,
    keyword: str,
    domain: str | None,
    location_name: str,
    location_code: int | None,
    language_name: str,
    device: str,
    depth: int,
    deep_tracking: bool = False,
) -> str:
    """sha256 over the canonical JSON of the normalized inputs.

    Uses ``location_name`` and ``language_name`` (strings accepted
    directly by the DataForSEO API) instead of integer codes.

    ``location_code`` is included so that a search targeting the same
    keyword from two *different* location codes (e.g. the City
    "Jaipur" vs. the Sub District "Jaipur" which share a name but
    have distinct codes) are not mistakenly de-duplicated as the same
    in-flight check.

    The fingerprint identifies a *search configuration*, not an
    individual check — repeated checks with the same configuration
    get different rows but share a fingerprint, which is used for
    in-flight deduplication.

    ``deep_tracking`` is included because it changes the API call
    parameters (depth, stop_crawl_on_match, find_targets_in), even
    when depth happens to overlap.
    """
    payload = {
        "keyword": keyword,
        "domain": domain,
        "location_name": location_name,
        "location_code": location_code,
        "language_name": language_name,
        "device": device,
        "depth": depth,
        "deep_tracking": deep_tracking,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_device(raw: Any) -> str:
    if not isinstance(raw, str) or raw not in DEVICES:
        raise ValueError("device must be 'desktop' or 'mobile'")
    return raw


def validate_depth(raw: Any) -> int:
    if not isinstance(raw, int):
        raise ValueError("depth must be one of 10, 20, 50, 100")
    if raw not in DEPTHS:
        raise ValueError("depth must be one of 10, 20, 50, 100")
    return raw
