"""
WebCrawler - pure crawler that fetches a single URL and extracts
crawl-level data (HTTP info, SSL, security headers, resources,
robots.txt, sitemap).  No SEO parsing or scoring logic.
"""
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup

from app.utils.crawler_utils.url_utils import get_domain, is_internal_link, normalize_url

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

SECURITY_HEADER_NAMES = {
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
    "content-security-policy",
    "x-xss-protection",
    "referrer-policy",
    "permissions-policy",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
}


@dataclass
class CrawlResult:
    """Structured result of crawling a single URL."""

    requested_url: str
    final_url: str
    html: str
    http: dict = field(default_factory=dict)
    ssl: dict = field(default_factory=dict)
    security_headers: dict = field(default_factory=dict)
    performance: dict = field(default_factory=dict)
    resources: dict = field(default_factory=dict)
    javascript: dict = field(default_factory=dict)
    robots: dict = field(default_factory=dict)
    sitemap: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON dumping."""
        return {
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "html": self.html,
            "http": self.http,
            "ssl": self.ssl,
            "security_headers": self.security_headers,
            "performance": self.performance,
            "resources": self.resources,
            "javascript": self.javascript,
            "robots": self.robots,
            "sitemap": self.sitemap,
        }


class WebCrawler:
    """Crawls a single URL and returns structured crawl data."""

    def __init__(
        self,
        timeout: int = 30,
        follow_redirects: bool = True,
        user_agent: Optional[str] = None,
    ):
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self.user_agent = user_agent or DEFAULT_USER_AGENT

    async def crawl(self, url: str) -> CrawlResult:
        """
        Crawl a URL and return structured results.

        Args:
            url: URL to crawl (must include http:// or https://)

        Returns:
            CrawlResult with HTTP, SSL, security, resource, robots,
            and sitemap data.

        Raises:
            ValueError: if the URL is invalid.
            RuntimeError: if the crawl fails (network error, etc.).
        """
        # -- validate -----------------------------------------------------
        if not url or not url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL: {url}")

        normalized = normalize_url(url)
        domain = get_domain(normalized)
        if not domain:
            raise ValueError(f"Invalid URL: {url} - could not extract domain")

        # -- fetch --------------------------------------------------------
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=self.follow_redirects,
            headers={"User-Agent": self.user_agent},
        ) as client:
            start = time.time()
            try:
                response = await client.get(normalized)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                raise RuntimeError(f"Could not connect to {normalized}: {exc}") from exc
            except httpx.HTTPError as exc:
                raise RuntimeError(f"Crawl failed for {normalized}: {exc}") from exc

            elapsed_ms = int((time.time() - start) * 1000)
            content_bytes = response.content
            content_type = (
                response.headers.get("content-type", "")
                .split(";")[0]
                .strip()
                .lower()
            )

            # -- HTTP info ------------------------------------------------
            http_info = {
                "status_code": response.status_code,
                "response_time": round(elapsed_ms / 1000.0, 3),
                "response_time_ms": elapsed_ms,
                "content_type": content_type,
                "content_size": len(content_bytes),
                "headers": dict(response.headers),
            }

            # -- SSL / security --------------------------------------------
            ssl_info = self._extract_ssl_info(normalized, response)
            security_headers = self._extract_security_headers(response.headers)

            # -- performance -----------------------------------------------
            performance = {
                "response_time_ms": elapsed_ms,
                "download_size_bytes": len(content_bytes),
                "content_type": content_type,
                "status_code": response.status_code,
            }

            # -- resources & javascript (HTML only) ----------------------
            html = response.text
            resources: dict = {}
            javascript: dict = {}
            if "text/html" in content_type:
                soup = BeautifulSoup(html, "html.parser")
                resources, javascript = self._extract_resources(soup, normalized, domain)
            else:
                resources = {
                    "total_links": 0,
                    "internal_links": 0,
                    "external_links": 0,
                    "images": 0,
                    "scripts": 0,
                    "stylesheets": 0,
                    "total_assets": 0,
                }
                javascript = {
                    "total_scripts": 0,
                    "external_scripts": 0,
                    "inline_scripts": 0,
                    "has_inline_js": False,
                }

            # -- robots.txt -----------------------------------------------
            robots_info = await self._check_robots(client, normalized, domain)

            # -- sitemap --------------------------------------------------
            sitemap_info = await self._check_sitemap(client, normalized, domain)

        return CrawlResult(
            requested_url=str(normalized),
            final_url=str(response.url),
            html=html,
            http=http_info,
            ssl=ssl_info,
            security_headers=security_headers,
            performance=performance,
            resources=resources,
            javascript=javascript,
            robots=robots_info,
            sitemap=sitemap_info,
        )

    # -- private helpers ------------------------------------------------

    @staticmethod
    def _extract_ssl_info(url: str, response: httpx.Response) -> dict:
        """Extract SSL/TLS information from the response."""
        parsed = urlparse(url)
        is_https = parsed.scheme == "https"

        info: dict = {
            "is_https": is_https,
            "protocol": None,
            "cert_issuer": None,
            "cert_valid_to": None,
            "cert_valid_from": None,
            "hsts": response.headers.get("strict-transport-security"),
        }

        if is_https:
            # Try to reach the TLS object through the network stream
            try:
                stream = (
                    response.http_response.extensions.get("network_stream")
                    if hasattr(response, "http_response")
                    else None
                )
                if stream is not None and hasattr(stream, "ssl_object") and stream.ssl_object:
                    cert = stream.ssl_object.getpeercert()
                    if cert:
                        info["cert_issuer"] = dict(
                            x for x in cert.get("issuer", ())
                        )
                        not_after = cert.get("not_after")
                        not_before = cert.get("not_before")
                        if not_after:
                            info["cert_valid_to"] = not_after
                        if not_before:
                            info["cert_valid_from"] = not_before
            except Exception:
                pass

        return info

    @staticmethod
    def _extract_security_headers(headers: httpx.Headers) -> dict:
        """Extract common security-related response headers."""
        result: dict = {}
        for name in SECURITY_HEADER_NAMES:
            value = headers.get(name)
            if value is not None:
                result[name] = value
        result["has_security_headers"] = len(result) > 0
        return result

    def _extract_resources(
        self,
        soup: BeautifulSoup,
        base_url: str,
        domain: str,
    ) -> tuple[dict, dict]:
        """Extract page resources and JavaScript info from parsed HTML."""
        # Links
        all_links = soup.find_all("a", href=True)
        internal = sum(
            1 for a in all_links
            if is_internal_link(base_url, urljoin(base_url, a.get("href", "")))
        )
        external = len(all_links) - internal

        images = len(soup.find_all("img", src=True))
        scripts_with_src = soup.find_all("script", src=True)
        scripts_total = soup.find_all("script")
        stylesheets = len(soup.find_all("link", rel="stylesheet"))

        resources = {
            "total_links": len(all_links),
            "internal_links": internal,
            "external_links": external,
            "images": images,
            "scripts": len(scripts_with_src),
            "stylesheets": stylesheets,
            "total_assets": images + len(scripts_with_src) + stylesheets,
        }

        javascript = {
            "total_scripts": len(scripts_total),
            "external_scripts": len(scripts_with_src),
            "inline_scripts": len(scripts_total) - len(scripts_with_src),
            "has_inline_js": len(scripts_total) > len(scripts_with_src),
        }

        return resources, javascript

    async def _check_robots(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        domain: str,
    ) -> dict:
        """Fetch and inspect robots.txt."""
        robots_url = f"{urlparse(base_url).scheme}://{domain}/robots.txt"
        info = {
            "url": robots_url,
            "exists": False,
            "status_code": None,
            "content": None,
            "rules_count": 0,
            "allows_crawling": True,
        }
        try:
            resp = await client.get(robots_url, follow_redirects=True)
            if resp.status_code == 200:
                info["exists"] = True
                info["status_code"] = resp.status_code
                content = resp.text
                info["content"] = content
                # Count non-empty, non-comment lines as rules
                lines = [
                    ln.strip()
                    for ln in content.splitlines()
                    if ln.strip() and not ln.strip().startswith("#")
                ]
                info["rules_count"] = len(lines)
                # Check for Disallow: / which blocks all
                info["allows_crawling"] = not bool(
                    re.search(r"disallow:\s*/\s*$", content, re.IGNORECASE | re.MULTILINE)
                )
            else:
                info["status_code"] = resp.status_code
        except Exception:
            pass
        return info

    async def _check_sitemap(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        domain: str,
    ) -> dict:
        """Probe common sitemap locations."""
        scheme = urlparse(base_url).scheme
        sitemap_paths = [
            "/sitemap.xml",
            "/sitemap_index.xml",
            "/sitemap/",
            "/sitemap",
        ]
        for path in sitemap_paths:
            sitemap_url = f"{scheme}://{domain}{path}"
            try:
                resp = await client.get(sitemap_url, follow_redirects=True)
                if resp.status_code == 200 and resp.content:
                    return {
                        "url": sitemap_url,
                        "exists": True,
                        "status_code": resp.status_code,
                        "content_type": resp.headers.get("content-type", ""),
                        "content_length": len(resp.content),
                    }
            except Exception:
                continue
        return {
            "url": f"{scheme}://{domain}/sitemap.xml",
            "exists": False,
            "status_code": None,
            "content_type": None,
            "content_length": 0,
        }
