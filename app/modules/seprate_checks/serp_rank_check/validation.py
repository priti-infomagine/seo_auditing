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
    if host.startswith("www."):
        host = host[4:]
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
    domain: str,
    location_code: int,
    language_code: str,
    device: str,
    depth: int,
    include_preview: bool,
) -> str:
    """sha256 over the canonical JSON of the normalized inputs."""
    payload = {
        "keyword": keyword,
        "domain": domain,
        "location_code": location_code,
        "language_code": language_code,
        "device": device,
        "depth": depth,
        "include_preview": include_preview,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_device(raw: Any) -> str:
    if not isinstance(raw, str) or raw not in DEVICES:
        raise ValueError("device must be 'desktop' or 'mobile'")
    return raw


def validate_depth(raw: Any) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError("depth must be one of 10, 20, 50, 100")
    if raw not in DEPTHS:
        raise ValueError("depth must be one of 10, 20, 50, 100")
    return raw
