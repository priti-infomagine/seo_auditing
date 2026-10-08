from __future__ import annotations

import asyncio
import gzip
import io
import ipaddress
import socket
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from http import HTTPStatus
from typing import Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx

from app.core.logger import logger
from app.shared.utils.url_utils import is_same_site, normalize_url

from .schema import RedirectHop, RedirectUrlResult

USER_AGENT = "SEOAuditBot/1.0"
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECT_HOPS = 10
MAX_HTML_BYTES = 2_000_000
MAX_SITEMAP_BYTES = 5_000_000
MAX_SITEMAP_EXPANDED_BYTES = 10_000_000
MAX_SITEMAP_FILES = 40
MAX_SITEMAP_DEPTH = 3
MAX_CRAWL_DEPTH = 5
MAX_LINKS_PER_PAGE = 200
MAX_TRANSIENT_RETRIES = 2
TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}


class CrawlError(Exception):
    """Raised when a requested crawl target is invalid or unsafe."""

    def __init__(self, message: str, error_type: str = "crawl_error") -> None:
        super().__init__(message)
        self.error_type = error_type


class HostGuard(Protocol):
    async def validate(self, url: str) -> None: ...


def canonicalize_url(value: str) -> str | None:
    try:
        parts = urlsplit(value.strip())
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return None
        if parts.username or parts.password:
            return None
        host = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        port = parts.port
    except (AttributeError, UnicodeError, ValueError):
        return None
    if port not in {None, 80, 443}:
        return None

    formatted_host = f"[{host}]" if ":" in host else host
    netloc = f"{formatted_host}:{port}" if port is not None else formatted_host
    candidate = urlunsplit(
        (parts.scheme.lower(), netloc, parts.path or "/", parts.query, "")
    )
    try:
        return normalize_url(candidate)
    except ValueError:
        return None


def _hostname(url: str) -> str:
    return urlsplit(url).hostname.lower().rstrip(".")


class PublicHostGuard:
    """Reject non-public targets before any crawler request is sent."""

    async def validate(self, url: str) -> None:
        try:
            parsed = urlsplit(url)
            host = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise CrawlError("Malformed target URL", "invalid_target") from exc
        if parsed.scheme not in {"http", "https"} or not host:
            raise CrawlError("Only HTTP and HTTPS URLs are allowed", "invalid_target")
        if parsed.username or parsed.password:
            raise CrawlError("Credentials are not allowed in target URLs", "invalid_target")

        normalized_host = host.lower().rstrip(".")
        try:
            address = ipaddress.ip_address(normalized_host)
            addresses = [address]
        except ValueError:
            try:
                records = await asyncio.to_thread(
                    socket.getaddrinfo,
                    normalized_host,
                    port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            except OSError as exc:
                raise CrawlError(
                    f"Unable to resolve host: {normalized_host}", "dns_error"
                ) from exc
            try:
                addresses = [
                    ipaddress.ip_address(record[4][0]) for record in records
                ]
            except ValueError as exc:
                raise CrawlError(
                    f"Host resolved to an invalid address: {normalized_host}",
                    "dns_error",
                ) from exc

        if not addresses or any(not address.is_global for address in addresses):
            raise CrawlError(
                f"Target host is not publicly routable: {normalized_host}",
                "ssrf_blocked",
            )


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.base_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag.lower() == "base" and values.get("href") and self.base_href is None:
            self.base_href = values["href"]
        if tag.lower() not in {"a", "area", "link"}:
            return
        href = values.get("href")
        if href:
            self.links.append(href)


def _response_url(response: httpx.Response, fallback: str) -> str:
    return canonicalize_url(str(response.url)) or fallback


async def _read_limited(response: httpx.Response, max_bytes: int) -> bytes:
    body = bytearray()
    async for chunk in response.aiter_bytes():
        remaining = max_bytes - len(body)
        body.extend(chunk[:remaining])
        if len(body) >= max_bytes:
            break
    return bytes(body)


async def _fetch_text(
    client: httpx.AsyncClient,
    guard: HostGuard,
    url: str,
    max_bytes: int,
) -> tuple[int, str, str | None]:
    await guard.validate(url)
    try:
        async with client.stream("GET", url, headers={"User-Agent": USER_AGENT}) as response:
            content_type = response.headers.get("content-type", "").lower()
            if response.status_code >= 400:
                return response.status_code, "", content_type
            body = await _read_limited(response, max_bytes)
            if urlsplit(url).path.lower().endswith(".gz"):
                try:
                    with gzip.GzipFile(fileobj=io.BytesIO(body)) as compressed:
                        body = compressed.read(MAX_SITEMAP_EXPANDED_BYTES + 1)
                except (EOFError, OSError) as exc:
                    raise CrawlError(f"Invalid gzip sitemap: {url}") from exc
                if len(body) > MAX_SITEMAP_EXPANDED_BYTES:
                    raise CrawlError(f"Expanded sitemap exceeds size limit: {url}")
            encoding = response.encoding or "utf-8"
            return response.status_code, body.decode(encoding, errors="replace"), content_type
    except (httpx.HTTPError, OSError) as exc:
        raise CrawlError(f"Request failed for {url}: {type(exc).__name__}") from exc


def _parse_sitemap_xml(content: str) -> tuple[list[str], list[str]]:
    root = ElementTree.fromstring(content)

    page_urls: list[str] = []
    child_sitemaps: list[str] = []
    root_name = root.tag.rsplit("}", 1)[-1].lower()
    target = child_sitemaps if root_name == "sitemapindex" else page_urls
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() == "loc" and element.text:
            target.append(element.text.strip())
    return page_urls, child_sitemaps


def _same_host(url: str, host: str) -> bool:
    try:
        return is_same_site(_hostname(url), host)
    except ValueError:
        return False


async def _discover_sitemaps(
    origin: str,
    host: str,
    robots_text: str,
    client: httpx.AsyncClient,
    guard: HostGuard,
    max_urls: int,
    errors: list[str],
) -> list[str]:
    sitemap_candidates: deque[tuple[str, int]] = deque()

    for line in robots_text.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() == "sitemap":
            candidate = canonicalize_url(value.strip())
            if candidate and _same_host(candidate, host):
                sitemap_candidates.append((candidate, 0))

    for path in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml"):
        sitemap_candidates.append((urljoin(origin, path), 0))

    seen_sitemaps: set[str] = set()
    urls: list[str] = []
    seen_urls: set[str] = set()

    while (
        sitemap_candidates
        and len(seen_sitemaps) < MAX_SITEMAP_FILES
        and len(urls) < max_urls
    ):
        batch: list[str] = []
        sitemap_depths: dict[str, int] = {}
        while sitemap_candidates and len(batch) < 10:
            sitemap_url, depth = sitemap_candidates.popleft()
            normalized = canonicalize_url(sitemap_url)
            if (
                normalized
                and normalized not in seen_sitemaps
                and _same_host(normalized, host)
            ):
                seen_sitemaps.add(normalized)
                batch.append(normalized)
                sitemap_depths[normalized] = depth
                if len(seen_sitemaps) >= MAX_SITEMAP_FILES:
                    break

        async def fetch_sitemap(url: str) -> tuple[str, int | None, str | None]:
            try:
                status_code, content, _ = await _fetch_text(
                    client, guard, url, max_bytes=MAX_SITEMAP_BYTES
                )
                return url, status_code, content
            except CrawlError as exc:
                logger.debug("redirect_urls: sitemap fetch failed for %s: %s", url, exc)
                return url, None, str(exc)

        responses = await asyncio.gather(
            *(fetch_sitemap(url) for url in batch)
        )
        for response_url, status_code, content in responses:
            depth = sitemap_depths[response_url]
            if status_code is None:
                errors.append(f"Sitemap could not be fetched: {response_url}: {content}")
                continue
            if status_code == 404:
                continue
            if status_code < 200 or status_code >= 300:
                errors.append(f"Sitemap returned HTTP {status_code}: {response_url}")
                continue
            try:
                page_urls, child_sitemaps = _parse_sitemap_xml(content or "")
            except ElementTree.ParseError:
                errors.append(f"Sitemap contains invalid XML: {response_url}")
                continue
            if depth >= MAX_SITEMAP_DEPTH and child_sitemaps:
                errors.append(f"Sitemap nesting limit reached at {response_url}")
            for child in child_sitemaps:
                normalized_child = canonicalize_url(urljoin(response_url, child))
                if (
                    depth < MAX_SITEMAP_DEPTH
                    and normalized_child
                    and _same_host(normalized_child, host)
                ):
                    sitemap_candidates.append((normalized_child, depth + 1))
            for candidate in page_urls:
                normalized = canonicalize_url(urljoin(response_url, candidate))
                if (
                    normalized
                    and _same_host(normalized, host)
                    and normalized not in seen_urls
                ):
                    seen_urls.add(normalized)
                    urls.append(normalized)
                    if len(urls) >= max_urls:
                        break

    return urls[:max_urls]


@dataclass
class SiteDiscovery:
    host: str
    urls: list[str]
    sitemap_urls: list[str]
    page_edges: list[tuple[str, str]]
    errors: list[str]
    robots_reachable: bool
    depths: dict[str, int] = field(default_factory=dict)


async def discover_site_urls(
    domain: str,
    max_urls: int,
    client: httpx.AsyncClient,
    guard: HostGuard,
    progress: Callable[[int, int], Awaitable[None]] | None = None,
    *,
    max_depth: int = MAX_CRAWL_DEPTH,
) -> SiteDiscovery:
    if max_depth < 0 or max_depth > 8:
        raise ValueError("max_depth must be between 0 and 8")
    origin = canonicalize_url(domain)
    if not origin:
        raise CrawlError("Provide a valid HTTP or HTTPS website URL")
    parsed_origin = urlsplit(origin)
    if parsed_origin.path not in {"", "/"} or parsed_origin.query:
        origin = urlunsplit((parsed_origin.scheme, parsed_origin.netloc, "/", "", ""))
    host = _hostname(origin)

    robots = RobotFileParser()
    robots_url = urljoin(origin, "/robots.txt")
    robots.set_url(robots_url)
    robots_text = ""
    discovery_errors: list[str] = []
    try:
        status_code, robots_text, _ = await _fetch_text(
            client, guard, robots_url, max_bytes=512_000
        )
        if 400 <= status_code < 500:
            robots_text = ""
        elif status_code < 200 or status_code >= 300:
            error = f"robots.txt was unreachable (HTTP {status_code})"
            logger.warning("redirect_urls: %s for %s", error, host)
            return SiteDiscovery(host, [], [], [], [error], False)
    except CrawlError as exc:
        robots_text = ""
        error = f"robots.txt could not be fetched: {exc}"
        logger.warning("redirect_urls: %s for %s", error, host)
        return SiteDiscovery(host, [], [], [], [error], False)
    robots.parse(robots_text.splitlines())

    sitemap_urls = await _discover_sitemaps(
        origin,
        host,
        robots_text,
        client,
        guard,
        max_urls,
        discovery_errors,
    )
    seed_urls = list(dict.fromkeys([origin, *sitemap_urls]))
    queue = deque([(origin, 0)])
    queued = {origin}
    if max_depth > 0:
        for sitemap_url in seed_urls[1:]:
            if len(queued) >= max_urls:
                break
            if sitemap_url not in queued:
                queue.append((sitemap_url, 1))
                queued.add(sitemap_url)
    visited: set[str] = set()
    depths: dict[str, int] = {}
    ordered_urls: list[str] = []
    ordered_depths: dict[str, int] = {}
    page_edges: list[tuple[str, str]] = []
    page_edge_set: set[tuple[str, str]] = set()

    while queue and len(visited) < max_urls:
        batch: list[str] = []
        while queue and len(batch) < 10 and len(visited) < max_urls:
            page_url, depth = queue.popleft()
            if page_url in visited or not robots.can_fetch(USER_AGENT, page_url):
                continue
            visited.add(page_url)
            depths[page_url] = depth
            batch.append(page_url)

        if not batch:
            continue

        async def crawl_page(page_url: str) -> tuple[str, list[str]]:
            try:
                await guard.validate(page_url)
                async with client.stream(
                    "GET", page_url, headers={"User-Agent": USER_AGENT}
                ) as response:
                    if response.status_code < 200 or response.status_code >= 300:
                        return page_url, []
                    if "text/html" not in response.headers.get("content-type", "").lower():
                        return page_url, []
                    body = await _read_limited(response, MAX_HTML_BYTES)
                    parser = _LinkParser()
                    parser.feed(body.decode(response.encoding or "utf-8", errors="replace"))
                    base = urljoin(page_url, parser.base_href) if parser.base_href else page_url
                    links = []
                    for href in parser.links:
                        normalized = canonicalize_url(urljoin(base, href))
                        if normalized and _same_host(normalized, host):
                            links.append(normalized)
                    return page_url, links
            except (CrawlError, httpx.HTTPError, OSError) as exc:
                logger.warning("redirect_urls: page crawl failed for %s: %s", page_url, exc)
                if len(discovery_errors) < 100:
                    discovery_errors.append(
                        f"Page could not be crawled: {page_url}: {type(exc).__name__}"
                    )
                return page_url, []

        pages = await asyncio.gather(*(crawl_page(url) for url in batch))
        for source, links in pages:
            ordered_urls.append(source)
            ordered_depths[source] = depths[source]
            for target in links:
                edge = (source, target)
                if edge not in page_edge_set:
                    page_edges.append(edge)
                    page_edge_set.add(edge)
                if (
                    depths[source] < max_depth
                    and target not in queued
                    and len(queued) < max_urls
                ):
                    queued.add(target)
                    queue.append((target, depths[source] + 1))

        if progress:
            await progress(len(visited), len(queue))

    return SiteDiscovery(
        host=host,
        urls=ordered_urls[:max_urls],
        sitemap_urls=sitemap_urls,
        page_edges=page_edges,
        errors=discovery_errors,
        robots_reachable=True,
        depths=ordered_depths,
    )


async def check_redirect_chain(
    url: str,
    audited_host: str,
    client: httpx.AsyncClient,
    guard: HostGuard,
    *,
    max_hops: int = MAX_REDIRECT_HOPS,
) -> RedirectUrlResult:
    if max_hops < 0 or max_hops > 20:
        raise ValueError("max_hops must be between 0 and 20")
    result = RedirectUrlResult(url=url, chain=[{"url": url, "status": None}])
    current_url = url
    seen = {url}

    for _ in range(max_hops + 1):
        try:
            response_url = current_url
            status_code = 0
            location: str | None = None
            latency_ms = 0
            for attempt in range(MAX_TRANSIENT_RETRIES + 1):
                await guard.validate(current_url)
                started = time.perf_counter()
                async with client.stream(
                    "GET",
                    current_url,
                    headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"},
                ) as response:
                    latency_ms = round((time.perf_counter() - started) * 1000)
                    status_code = response.status_code
                    location = response.headers.get("location")
                    response_url = _response_url(response, current_url)
                if (
                    status_code not in TRANSIENT_HTTP_STATUSES
                    or attempt >= MAX_TRANSIENT_RETRIES
                ):
                    break
                await asyncio.sleep(0.1 * (2**attempt))

            result.latency_ms = (result.latency_ms or 0) + latency_ms
            if status_code not in REDIRECT_STATUSES:
                result.final_url = response_url
                result.final_status = status_code
                result.is_broken = status_code >= 400
                break

            target = (
                canonicalize_url(urljoin(current_url, location))
                if location
                else None
            )
            result.hops.append(
                RedirectHop(
                    url=current_url,
                    status=status_code,
                    status_text=_status_text(status_code),
                    location=location,
                    resolved=target,
                    latency_ms=latency_ms,
                )
            )
            result.redirect_count += 1
            result.redirects = result.redirect_count
            result.is_redirect = True
            if not location:
                result.error = "Redirect response is missing the Location header"
                result.error_type = "malformed_location"
                result.final_url = response_url
                result.final_status = status_code
                break
            if target is None:
                result.error = "Redirect location is not a valid HTTP(S) URL"
                result.error_type = "malformed_location"
                result.final_url = response_url
                result.final_status = status_code
                break
            result.chain.append({"url": target, "status": status_code})
            is_internal = _same_host(target, audited_host)
            result.is_internal_redirect |= is_internal
            result.is_external_redirect |= not is_internal
            if target in seen:
                result.error = "Redirect loop detected"
                result.error_type = "redirect_loop"
                result.final_url = response_url
                result.final_status = status_code
                break
            if result.redirect_count > max_hops:
                result.error = f"Redirect limit exceeded ({max_hops})"
                result.error_type = "max_hops_exceeded"
                result.final_url = response_url
                result.final_status = status_code
                break
            seen.add(target)
            current_url = target
            if result.redirect_count == max_hops:
                # One more response is required to tell whether the final URL
                # redirects again, so the next iteration remains intentional.
                continue
        except CrawlError as exc:
            result.error = str(exc)
            result.error_type = exc.error_type
            result.final_url = current_url
            break
        except httpx.TimeoutException as exc:
            result.error = f"Request timed out: {type(exc).__name__}"
            result.error_type = "timeout"
            break
        except httpx.ConnectError as exc:
            cause_text = str(exc).lower()
            result.error = f"Connection failed: {type(exc).__name__}"
            result.error_type = (
                "tls_error" if "ssl" in cause_text or "certificate" in cause_text
                else "connection_error"
            )
            break
        except (httpx.HTTPError, OSError) as exc:
            result.error = f"Request failed: {type(exc).__name__}"
            result.error_type = "request_error"
            break

    if not result.final_url:
        result.final_url = current_url
    if result.error:
        result.is_broken = True
    return result


def _status_text(status_code: int) -> str | None:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return None
