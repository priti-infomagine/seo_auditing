"""Domain preview extraction for SERP rank checks.

Fetches a **single** target domain's live HTML page and extracts:
site name, favicon, page title, and meta description.  This is a
best-effort enrichment — failures (timeout, non-200, SSRF-blocked,
unreachable domain) return all-None fields without failing the
rank check itself.

Adapted from the standalone ``preview_check.py`` script into an async
module suitable for use inside the FastAPI rank-check service.

Extraction priority chains (ported verbatim from ``preview_check.py``):

- **favicon** → ``<link rel="icon">`` → ``<link rel="apple-touch-icon">`` → ``/favicon.ico``
- **title**   → ``og:title`` meta → ``<title>`` tag → ``twitter:title`` meta
- **description** → ``meta[name=description]`` → ``og:description`` → ``twitter:description``
- **site_name** → JSON-LD ``WebSite.name`` → ``og:site_name`` → ``<meta name=application-name>`` → registrable domain
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

# ── Constants (mirror preview_check.py) ──────────────────────
TIMEOUT = 10                      # seconds
MAX_BYTES = 2 * 1024 * 1024       # read at most 2 MB of HTML
MAX_REDIRECTS = 5
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LinkPreviewBot/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}


# ── URL + SSRF helpers ───────────────────────────────────────


def _normalize_url(raw: str) -> str:
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw


def _assert_public(url: str) -> None:
    """SSRF guard: refuse localhost / private / link-local addresses.

    Resolves the hostname and checks every returned IP with
    ``ipaddress.ip_address(...).is_global``.
    """
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("Invalid URL")
    port = p.port or (443 if p.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(p.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"Could not resolve {p.hostname}")
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError("URL points to a non-public address")


# ── Async HTML fetch (with per-hop SSRF) ─────────────────────


async def _fetch_html(url: str) -> tuple[str, bytes]:
    """Fetch the page, following redirects manually so every hop is SSRF-checked.

    Returns ``(final_url, html_bytes)``.
    """
    async with httpx.AsyncClient(
        headers=HEADERS, timeout=TIMEOUT, follow_redirects=False
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            # Blocking DNS-based SSRF check in a worker thread
            await asyncio.to_thread(_assert_public, url)
            response = await client.get(url, timeout=TIMEOUT)
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("Redirect without Location header")
                url = urljoin(url, location)
                continue
            response.raise_for_status()
            return str(response.url), response.content[:MAX_BYTES]
    raise ValueError("Too many redirects")


# ── Parsing helpers (ported verbatim from preview_check.py) ───


def _meta(soup: BeautifulSoup, key: str, value: str):
    tag = soup.find("meta", attrs={key: value})
    if tag and tag.get("content"):
        return tag["content"].strip() or None
    return None


def _site_name_from_jsonld(soup: BeautifulSoup):
    """Look for a WebSite object in any <script type='application/ld+json'>."""

    def walk(node):
        if isinstance(node, list):
            for item in node:
                found = walk(item)
                if found:
                    return found
        elif isinstance(node, dict):
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if "WebSite" in types:
                name = node.get("name") or node.get("alternateName")
                if isinstance(name, list):
                    name = name[0] if name else None
                if name:
                    return str(name).strip()
            for key in ("@graph", "mainEntity", "isPartOf", "publisher"):
                if key in node:
                    found = walk(node[key])
                    if found:
                        return found
        return None

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        found = walk(data)
        if found:
            return found
    return None


def _get_site_name(soup: BeautifulSoup, domain: str) -> str:
    return (
        _site_name_from_jsonld(soup)
        or _meta(soup, "property", "og:site_name")
        or _meta(soup, "name", "application-name")
        or domain
    )


def _get_favicon(soup: BeautifulSoup, base_url: str) -> str:
    candidates: dict[str, str | None] = {"icon": None, "apple": None}
    for link in soup.find_all("link", href=True):
        rel = " ".join(link.get("rel", [])).lower()
        if "apple-touch-icon" in rel:
            candidates["apple"] = candidates["apple"] or link["href"]
        elif "icon" in rel:  # "icon" and "shortcut icon"
            candidates["icon"] = candidates["icon"] or link["href"]
    href = candidates["icon"] or candidates["apple"]
    if href:
        return urljoin(base_url, href.strip())
    return urljoin(base_url, "/favicon.ico")  # last-resort fallback


def _get_title(soup: BeautifulSoup):
    if _meta(soup, "property", "og:title"):
        return _meta(soup, "property", "og:title")
    if soup.title and soup.title.string and soup.title.string.strip():
        return soup.title.string.strip()
    return _meta(soup, "name", "twitter:title")


def _get_description(soup: BeautifulSoup):
    return (
        _meta(soup, "name", "description")
        or _meta(soup, "property", "og:description")
        or _meta(soup, "name", "twitter:description")
    )


def _parse_html(html: bytes, final_url: str) -> dict[str, Any]:
    """Extract preview metadata from raw HTML bytes."""
    soup = BeautifulSoup(html, "html.parser")
    domain = urlparse(final_url).hostname or ""
    preview: dict[str, Any] = {
        "site_name": _get_site_name(soup, domain),
        "domain": domain,
        "favicon": _get_favicon(soup, final_url),
        "title": _get_title(soup),
        "description": _get_description(soup),
    }
    if not preview["title"] and not preview["description"]:
        preview["warning"] = (
            "No title/description found. The site may be JS-rendered "
            "(empty <head> in raw HTML); try a headless browser fallback."
        )
    return preview


# ── Public entry point ────────────────────────────────────────


async def fetch_domain_preview(domain: str) -> dict[str, Any]:
    """Fetch **one** target domain's page and extract preview metadata.

    Called with the single ``normalized_domain`` from the rank-check
    request — NOT iterated over every SERP result.

    Args:
        domain: A bare registrable domain (e.g. ``"tesla.com"``) or
            a full URL.  If no scheme is present, ``https://`` is
            prepended.

    Returns:
        A dict with ``site_name``, ``domain``, ``favicon``,
        ``title``, ``description`` (and optionally ``warning``).
        On any fetch or parse error, a dict with all string fields
        set to ``None`` is returned — the rank check itself is
        never failed by a preview error.
    """
    url = _normalize_url(domain)
    try:
        final_url, html = await _fetch_html(url)
    except (ValueError, httpx.HTTPError):
        return {
            "site_name": None,
            "domain": domain,
            "favicon": None,
            "title": None,
            "description": None,
        }
    return _parse_html(html, final_url)
