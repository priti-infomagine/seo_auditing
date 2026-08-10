"""
Technical extractor - catch-all for technical evidence.

Absorbs HTTP response metadata, redirects, security headers,
JSON-LD, performance observations, accessibility facts.
"""
from dataclasses import dataclass, field
from typing import Any
from bs4 import BeautifulSoup


@dataclass
class TechnicalFacts:
    status_code: int = 0
    content_type: str = ""
    content_length: int = 0
    response_time_ms: int = 0
    headers: dict = field(default_factory=dict)
    redirects: list = field(default_factory=list)
    security: dict = field(default_factory=dict)
    performance: dict = field(default_factory=dict)
    accessibility: dict = field(default_factory=dict)
    json_ld: list = field(default_factory=list)


def extract_technical(
    status_code: int,
    headers: dict,
    content_length: int,
    response_time_ms: int,
    redirects: list = None,
    soup: BeautifulSoup = None,
    raw_html: str = "",
) -> TechnicalFacts:
    """
    Extract technical facts from HTTP response and HTML.

    Args:
        status_code: HTTP status code
        headers: Response headers dict
        content_length: Response content length in bytes
        response_time_ms: Response time in milliseconds
        redirects: List of redirect dicts [{url, status_code}]
        soup: BeautifulSoup object (optional, for JSON-LD extraction)
        raw_html: Raw HTML string (optional, for performance indicators)

    Returns:
        TechnicalFacts with all technical evidence
    """
    if redirects is None:
        redirects = []

    security = _extract_security(headers)
    performance = _extract_performance(soup, raw_html, response_time_ms)
    accessibility = _extract_accessibility(soup)
    json_ld = _extract_json_ld(soup) if soup else []

    return TechnicalFacts(
        status_code=status_code,
        content_type=headers.get("content-type", "").split(";")[0].strip().lower(),
        content_length=content_length,
        response_time_ms=response_time_ms,
        headers=dict(headers),
        redirects=redirects,
        security=security,
        performance=performance,
        accessibility=accessibility,
        json_ld=json_ld,
    )


def _extract_security(headers: dict) -> dict:
    security = {
        "https": False,
        "ssl": {},
        "headers": {},
        "mixed_content": [],
    }

    # HSTS
    hsts = headers.get("strict-transport-security", "")
    if hsts:
        security["headers"]["strict_transport_security"] = hsts

    # CSP
    csp = headers.get("content-security-policy", "")
    if csp:
        security["headers"]["content_security_policy"] = csp

    # X-Content-Type-Options
    xcto = headers.get("x-content-type-options", "")
    if xcto:
        security["headers"]["x_content_type_options"] = xcto

    # X-Frame-Options
    xfo = headers.get("x-frame-options", "")
    if xfo:
        security["headers"]["x_frame_options"] = xfo

    # Referrer-Policy
    rp = headers.get("referrer-policy", "")
    if rp:
        security["headers"]["referrer_policy"] = rp

    return security


def _extract_performance(soup: BeautifulSoup, raw_html: str, response_time_ms: int) -> dict:
    performance = {
        "load_time_ms": response_time_ms,
        "html_size_bytes": len(raw_html.encode("utf-8")) if raw_html else 0,
        "render_blocking_resources": [],
    }

    if soup:
        head = soup.find("head")
        if head:
            css_links = head.find_all("link", rel="stylesheet")
            performance["render_blocking_resources"] = [
                s.get("href", "") for s in css_links
            ]
            performance["render_blocking_count"] = len(css_links)

        scripts = soup.find_all("script")
        performance["script_count"] = len(scripts)

    return performance


def _extract_accessibility(soup: BeautifulSoup) -> dict:
    accessibility = {
        "images": {"total": 0, "with_alt": 0, "without_alt": 0},
        "forms": {"total": 0, "inputs": 0, "labeled_inputs": 0},
        "buttons": {"total": 0, "accessible": 0},
    }

    if not soup:
        return accessibility

    images = soup.find_all("img")
    accessibility["images"]["total"] = len(images)
    for img in images:
        alt = img.get("alt", "").strip()
        if alt:
            accessibility["images"]["with_alt"] += 1
        else:
            accessibility["images"]["without_alt"] += 1

    forms = soup.find_all("form")
    accessibility["forms"]["total"] = len(forms)
    for form in forms:
        inputs = form.find_all(["input", "textarea", "select"])
        accessibility["forms"]["inputs"] += len(inputs)
        for inp in inputs:
            if inp.get("id") or inp.get("aria-label") or inp.get("name"):
                accessibility["forms"]["labeled_inputs"] += 1

    buttons = soup.find_all("button")
    accessibility["buttons"]["total"] = len(buttons)

    return accessibility


def _extract_json_ld(soup: BeautifulSoup) -> list:
    import json
    schemas = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                schemas.append({
                    "type": data.get("@type", "Unknown"),
                    "context": data.get("@context", ""),
                    "raw": script.string,
                    "parsed": data,
                })
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        schemas.append({
                            "type": item.get("@type", "Unknown"),
                            "context": item.get("@context", ""),
                            "raw": script.string,
                            "parsed": item,
                        })
        except (json.JSONDecodeError, AttributeError):
            continue
    return schemas
