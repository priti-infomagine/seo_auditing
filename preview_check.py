"""
Enter a domain/URL and get: site name, domain, favicon, title, description.

Install:  pip install httpx beautifulsoup4  
          python preview_check.py example.com
          
"""

import ipaddress
import json
import socket
import sys
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

TIMEOUT = 10                    # seconds
MAX_BYTES = 2 * 1024 * 1024     # read at most 2 MB of HTML
MAX_REDIRECTS = 5
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LinkPreviewBot/1.0)",
    "Accept": "text/html,application/xhtml+xml",
}


# ---------------------------------------------------------------- fetching ---

def normalize_url(raw: str) -> str:
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw


def assert_public(url: str) -> None:
    """SSRF guard: refuse localhost / private / link-local addresses."""
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


def fetch_html(url: str):
    """Fetch the page, following redirects manually so every hop is checked.
    Returns (final_url, html_bytes)."""
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            assert_public(url)
            with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise ValueError("Redirect without Location header")
                    url = urljoin(url, location)
                    continue
                resp.raise_for_status()
                chunks, size = [], 0
                for chunk in resp.iter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_BYTES:
                        break
                return str(resp.url), b"".join(chunks)[:MAX_BYTES]
    raise ValueError("Too many redirects")


# ----------------------------------------------------------------- parsing ---

def meta(soup, key: str, value: str):
    tag = soup.find("meta", attrs={key: value})
    if tag and tag.get("content"):
        return tag["content"].strip() or None
    return None


def site_name_from_jsonld(soup):
    """Look for a WebSite object in any <script type="application/ld+json">."""

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


def get_site_name(soup, domain: str) -> str:
    return (
        site_name_from_jsonld(soup)
        or meta(soup, "property", "og:site_name")
        or meta(soup, "name", "application-name")
        or domain
    )


def get_favicon(soup, base_url: str) -> str:
    candidates = {"icon": None, "apple": None}
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


def get_title(soup):
    if meta(soup, "property", "og:title"):
        return meta(soup, "property", "og:title")
    if soup.title and soup.title.string and soup.title.string.strip():
        return soup.title.string.strip()
    return meta(soup, "name", "twitter:title")


def get_description(soup):
    return (
        meta(soup, "name", "description")
        or meta(soup, "property", "og:description")
        or meta(soup, "name", "twitter:description")
    )


def parse_html(html: bytes, final_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    domain = urlparse(final_url).hostname or ""
    return {
        "url": final_url,
        "domain": domain,
        "site_name": get_site_name(soup, domain),
        "favicon": get_favicon(soup, final_url),
        "title": get_title(soup),
        "description": get_description(soup),
    }


def get_preview(raw_url: str) -> dict:
    """Main function: use this inside your API endpoint."""
    final_url, html = fetch_html(normalize_url(raw_url))
    result = parse_html(html, final_url)
    if not result["title"] and not result["description"]:
        result["warning"] = (
            "No title/description found. The site may be JS-rendered "
            "(empty <head> in raw HTML); try a headless browser fallback."
        )
    return result


# --------------------------------------------------------------------- CLI ---

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else input("Enter domain or URL: ")
    try:
        print(json.dumps(get_preview(target), indent=2, ensure_ascii=False))
    except (ValueError, httpx.HTTPError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)