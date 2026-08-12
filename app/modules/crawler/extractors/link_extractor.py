"""
Link extractor - extracts links from HTML content.

Extracts ``<a>`` anchors (including non-HTTP protocols such as ``mailto:``,
``tel:``, ``javascript:`` and ``#`` fragment links) plus canonical and
hreflang ``<link>`` elements.

**Backwards compatibility:** the original ``LinkFacts.links`` list keeps its
identical semantics (HTTP-only anchors; ``mailto:``/``tel:``/``javascript:``
and ``#`` fragment links are excluded). The full, deep-analysis surface is
additionally exposed on ``LinkFacts.deep_links`` with rich per-link metadata
(protocol, target, title, download, anchor-text quality, new-tab behaviour)
so downstream consumers keep working unchanged while gaining deeper signal.
"""
from dataclasses import dataclass, field
from urllib.parse import urljoin
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Deep-link-analysis constants
# ---------------------------------------------------------------------------

# Words that carry little SEO signal when used verbatim as link text.
_GENERIC_ANCHOR_WORDS = {
    "click", "clickhere", "here", "readmore", "read", "more", "link",
    "this", "page", "website", "go", "next", "previous", "download",
    "view", "details", "continue", "button", "submit", "info", "access",
    "start", "home", "getstarted", "learn", "learnmore", "see", "seeall",
    "fullstory", "readarticle", "about", "login", "signup", "register",
    "logout", "visit", "open", "explore", "knowmore", "know", "findout",
}

# Protocols that resolve to a real HTTP(S) document (as opposed to
# mailto:/tel:/javascript:/fragment-only hrefs). Relative paths are HTTP too.
_NON_HTTP_PROTOCOLS = frozenset({"fragment", "mailto", "tel", "javascript"})


@dataclass
class LinkFacts:
    links: list = field(default_factory=list)
    internal_count: int = 0
    external_count: int = 0
    # Deep-analysis surface (additive - does not change ``links`` behaviour).
    deep_links: list = field(default_factory=list)
    total_link_count: int = 0
    fragment_count: int = 0
    mailto_count: int = 0
    tel_count: int = 0
    javascript_count: int = 0
    non_http_count: int = 0


def _normalize_anchor_text(anchor_text: str) -> str:
    """Collapse whitespace inside anchor text for quality + length checks."""
    return " ".join(anchor_text.split()) if anchor_text else ""


def _classify_protocol(href: str) -> str:
    """Classify a raw href into a protocol bucket for deep analysis."""
    lower = href.strip().lower()
    if lower.startswith("javascript:"):
        return "javascript"
    if lower.startswith("mailto:"):
        return "mailto"
    if lower.startswith("tel:"):
        return "tel"
    if lower.startswith("#"):
        return "fragment"
    if lower.startswith("http://"):
        return "http"
    if lower.startswith("https://"):
        return "https"
    if lower.startswith(("//", "/", "./", "../")):
        return "relative"
    # Any scheme-less path (e.g. ``industry.html``) is a relative URL.
    if ":" not in lower:
        return "relative"
    return "other"


def _classify_anchor_text(anchor_text: str) -> str:
    """
    Classify anchor text quality for SEO deep-analysis.

    Returns one of: ``empty``, ``generic``, ``url_like`` or ``descriptive``.
    """
    text = _normalize_anchor_text(anchor_text).lower()
    if not text:
        return "empty"
    if text.startswith(("http://", "https://", "www.", "//")):
        return "url_like"
    if "." in text and " " not in text and "/" in text:
        return "url_like"
    words = text.split()
    if len(words) <= 2 and all(w in _GENERIC_ANCHOR_WORDS for w in words):
        return "generic"
    return "descriptive"


def _make_link(
    tag,
    href: str,
    base_url: str,
    anchor_text: str,
    rel: str,
    link_type: str,
    is_internal: bool,
) -> dict:
    """Build a deep-analysis-enriched link dict (additive over old fields)."""
    rel_lower = rel.lower()
    protocol = _classify_protocol(href)
    normalized_text = _normalize_anchor_text(anchor_text)
    target = str(tag.get("target", "")).strip()

    return {
        # --- Original fields (unchanged names/semantics) ---
        "url": urljoin(base_url, href),
        "anchor_text": anchor_text,
        "rel": rel,
        "link_type": link_type,
        "is_internal": is_internal,
        "is_external": (
            (not is_internal) and protocol not in _NON_HTTP_PROTOCOLS
        ),
        "nofollow": "nofollow" in rel_lower,
        "ugc": "ugc" in rel_lower,
        "sponsored": "sponsored" in rel_lower,
        # --- Deep-analysis fields (additive, non-breaking) ---
        "raw_href": href,
        "protocol": protocol,
        "is_fragment": protocol == "fragment",
        "is_mailto": protocol == "mailto",
        "is_tel": protocol == "tel",
        "is_javascript": protocol == "javascript",
        "is_http": protocol not in _NON_HTTP_PROTOCOLS,
        "target": target,
        "title": str(tag.get("title", "")).strip(),
        "download": str(tag.get("download", "")).strip(),
        "opens_new_tab": target == "_blank",
        "has_link_text": bool(normalized_text),
        "link_text_length": len(normalized_text),
        "anchor_text_classification": _classify_anchor_text(anchor_text),
    }



def _link_tag_entry(href: str, base_url: str, link_type: str, rel: str) -> dict:
    """Build a deep-analysis link dict for a ``<link>`` element."""
    protocol = _classify_protocol(href)
    return {
        "url": urljoin(base_url, href),
        "anchor_text": "",
        "rel": rel,
        "link_type": link_type,
        "is_internal": True,
        "is_external": False,
        "nofollow": False,
        "ugc": False,
        "sponsored": False,
        "raw_href": href,
        "protocol": protocol,
        "is_fragment": False,
        "is_mailto": False,
        "is_tel": False,
        "is_javascript": False,
        "is_http": protocol not in _NON_HTTP_PROTOCOLS,
        "target": "",
        "title": "",
        "download": "",
        "opens_new_tab": False,
        "has_link_text": False,
        "link_text_length": 0,
        "anchor_text_classification": "empty",
    }


def extract_links(soup: BeautifulSoup, base_url: str) -> LinkFacts:
    """
    Extract all links from HTML content.

    Builds the full deep-analysis surface (``deep_links``) containing every
    anchor - including non-HTTP protocols (``mailto:``, ``tel:``,
    ``javascript:``, ``#`` fragments) - plus canonical and hreflang links.
    The original ``links`` list is then derived by filtering to HTTP(S)
    targets so its behaviour, internal/external counts and downstream
    consumers stay unchanged.

    Args:
        soup: BeautifulSoup object
        base_url: Base URL for resolving relative links

    Returns:
        LinkFacts with the original ``links`` and the deep ``deep_links``
    """
    from app.shared.utils.url_utils import is_internal_link

    deep_links = []
    fragment_count = 0
    mailto_count = 0
    tel_count = 0
    javascript_count = 0
    non_http_count = 0

    # Extract <a> tags (all anchors, including non-HTTP protocols)
    for tag in soup.find_all("a", href=True):
        href = str(tag.get("href", "")).strip()
        if not href:
            continue

        protocol = _classify_protocol(href)
        absolute_url = urljoin(base_url, href)
        anchor_text = tag.get_text(strip=True) or ""
        rel = tag.get("rel")
        if isinstance(rel, list):
            rel = " ".join(rel)
        elif rel is None:
            rel = ""

        link_type = "anchor"
        if tag.find_parent("nav"):
            link_type = "navigation"
        elif tag.find_parent("footer"):
            link_type = "footer"

        is_internal = is_internal_link(base_url, absolute_url)

        deep_links.append(_make_link(
            tag,
            href,
            base_url,
            anchor_text,
            rel,
            link_type,
            is_internal,
        ))

        if protocol == "fragment":
            fragment_count += 1
            non_http_count += 1
        elif protocol == "mailto":
            mailto_count += 1
            non_http_count += 1
        elif protocol == "tel":
            tel_count += 1
            non_http_count += 1
        elif protocol == "javascript":
            javascript_count += 1
            non_http_count += 1

    # Extract canonical links
    for tag in soup.find_all("link", rel="canonical", href=True):
        href = tag.get("href", "").strip()
        if href:
            deep_links.append(_link_tag_entry(href, base_url, "canonical", "canonical"))

    # Extract hreflang links
    for tag in soup.find_all("link", rel="alternate", hreflang=True, href=True):
        href = tag.get("href", "").strip()
        if href:
            deep_links.append(_link_tag_entry(
                href, base_url, "hreflang", tag.get("hreflang", "")
            ))

    # Original list keeps only HTTP(S)-resolving targets, preserving the
    # pre-existing behaviour and internal/external counts.
    links = [d for d in deep_links if d["is_http"]]
    internal_count = sum(1 for d in links if d["is_internal"])
    external_count = len(links) - internal_count

    return LinkFacts(
        links=links,
        internal_count=internal_count,
        external_count=external_count,
        deep_links=deep_links,
        total_link_count=len(deep_links),
        fragment_count=fragment_count,
        mailto_count=mailto_count,
        tel_count=tel_count,
        javascript_count=javascript_count,
        non_http_count=non_http_count,
    )
