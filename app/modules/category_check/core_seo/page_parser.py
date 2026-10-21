"""
PageParser — HTML → ParsedPage using BeautifulSoup.

Extracts title, meta tags, headings, links, images, content text,
structured data (JSON-LD), Open Graph / Twitter card tags, and more.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .models import ImageInfo, LinkInfo, ParsedPage
from .url_normalizer import URLNormalizer, resolve_relative

try:
    from bs4 import BeautifulSoup, NavigableString, Tag

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    BeautifulSoup = None  # type: ignore[assignment]
    Tag = object  # type: ignore[assignment]
    NavigableString = object  # type: ignore[assignment]


class PageParser:
    """Parse raw HTML into a structured ParsedPage."""

    def __init__(self, base_url: str = ""):
        self.base_url = base_url

    def parse(self, html: str, url: str) -> ParsedPage:
        """Parse HTML into a ParsedPage.

        Args:
            html: Raw HTML string.
            url: The canonical URL of the page (used for base resolution).

        Returns:
            ParsedPage with all extracted data.
        """
        if not BS4_AVAILABLE:
            return ParsedPage(url=url)

        if not html:
            return ParsedPage(url=url)

        soup = BeautifulSoup(html, "html.parser")
        page = ParsedPage(url=url)

        page.doctype = self._extract_doctype(soup)
        page.language = self._extract_language(soup)
        page.charset = self._extract_charset(soup)
        page.viewport = self._extract_viewport(soup)
        page.title = self._extract_title(soup)
        page.description = self._extract_meta(soup, "description")
        page.keywords = self._extract_meta_keywords(soup)
        page.robots_meta = self._extract_meta(soup, "robots")
        page.canonical = self._extract_canonical(soup, url)
        page.canonical_source_count = self._count_canonical_sources(soup)
        page.viewport = self._extract_viewport(soup)
        page.open_graph = self._extract_open_graph(soup)
        page.social = self._extract_social(soup)
        page.structured_data = self._extract_structured_data(soup)
        page.headings, page.heading_counts = self._extract_headings(soup)
        page.heading_hierarchy = self._extract_heading_hierarchy(soup)
        page.links = self._extract_links(soup, url)
        page.internal_links, page.external_links = self._classify_links(soup, url, page.links)
        page.images = self._extract_images(soup, url)
        page.favicon_urls = self._extract_favicon_urls(soup, url)
        page.content_text, page.word_count, page.char_count, page.paragraph_count = (
            self._extract_content(soup)
        )
        page.content_hash = hashlib.sha256(
            page.content_text.encode("utf-8", errors="replace")
        ).hexdigest()[:16]
        page.has_h1 = page.heading_counts.get("h1", 0) > 0
        page.has_h2 = page.heading_counts.get("h2", 0) > 0
        page.final_url = url

        return page

    # ── Field extraction helpers ────────────────────────────────────

    def _extract_doctype(self, soup: Any) -> str:
        doctype = soup.find("!doctype")
        if doctype:
            return str(doctype).strip()
        for item in soup.contents:
            if isinstance(item, type(soup.original_doctype)) if hasattr(soup, "original_doctype") and soup.original_doctype else False:
                pass
        if hasattr(soup, "original_doctype") and soup.original_doctype:
            return f"<!DOCTYPE {soup.original_doctype.strip()}>"
        return ""

    def _extract_language(self, soup: Any) -> str:
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            return str(html_tag.get("lang")).strip()
        return ""

    def _extract_charset(self, soup: Any) -> str:
        meta = soup.find("meta", attrs={"charset": True})
        if meta:
            return str(meta.get("charset")).strip()
        meta = soup.find("meta", attrs={"http-equiv": re.compile(r"^content-type$", re.IGNORECASE)})
        if meta:
            content = meta.get("content", "")
            match = re.search(r"charset\s*=\s*([^\s;]+)", str(content), re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_viewport(self, soup: Any) -> str:
        meta = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.IGNORECASE)})
        if meta:
            return str(meta.get("content", "")).strip()
        return ""

    def _extract_title(self, soup: Any) -> str:
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text().strip()
        return ""

    def _extract_meta(self, soup: Any, name: str) -> str:
        for attr in ("name", "property"):
            meta = soup.find("meta", attrs={attr: re.compile(rf"^{re.escape(name)}$", re.IGNORECASE)})
            if meta:
                content = meta.get("content", "")
                if content:
                    return str(content).strip()
        return ""

    def _extract_meta_keywords(self, soup: Any) -> list[str]:
        meta = soup.find("meta", attrs={"name": re.compile(r"^keywords$", re.IGNORECASE)})
        if meta:
            content = meta.get("content", "")
            if content:
                return [kw.strip() for kw in str(content).split(",") if kw.strip()]
        return []

    def _extract_canonical(self, soup: Any, page_url: str) -> str:
        link = soup.find("link", attrs={"rel": re.compile(r"canonical", re.IGNORECASE)})
        if link and link.get("href"):
            href = str(link.get("href"))
            return resolve_relative(page_url, href)

        og_url = self._extract_open_graph(soup).get("og:url", "")
        if og_url:
            return resolve_relative(page_url, og_url)

        return page_url

    def _count_canonical_sources(self, soup: Any) -> int:
        """Count canonical sources: <link rel=canonical> + HTTP Link header references."""
        count = 0
        canonical_links = soup.find_all("link", rel=re.compile(r"canonical", re.IGNORECASE))
        count += len(canonical_links)
        for meta in soup.find_all("meta", property=re.compile(r"^og:url$", re.IGNORECASE)):
            count += 1
        return max(0, count)

    def _extract_open_graph(self, soup: Any) -> dict[str, str]:
        og: dict[str, str] = {}
        for meta in soup.find_all("meta", property=re.compile(r"^og:", re.IGNORECASE)):
            prop = meta.get("property", "").lower()
            content = meta.get("content", "")
            if prop and content:
                og[prop] = str(content).strip()
        return og

    def _extract_social(self, soup: Any) -> dict[str, Any]:
        social: dict[str, Any] = {
            "twitter_cards": {},
            "open_graph": self._extract_open_graph(soup),
        }
        for meta in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:", re.IGNORECASE)}):
            name = meta.get("name", "").lower()
            content = meta.get("content", "")
            if name and content:
                social["twitter_cards"][name] = str(content).strip()
        return social

    def _extract_structured_data(self, soup: Any) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        for script in soup.find_all("script", attrs={"type": re.compile(r"^application/ld\+json$", re.IGNORECASE)}):
            content = script.get_text().strip()
            if not content:
                continue
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    schemas.append(data)
                elif isinstance(data, list):
                    schemas.extend(item for item in data if isinstance(item, dict))
            except (json.JSONDecodeError, ValueError):
                continue
        for link in soup.find_all("link", rel=re.compile(r"^(https?://)?schema\.org", re.IGNORECASE)):
            href = link.get("href")
            if href:
                schemas.append({"@type": "schema.org", "href": str(href)})
        return schemas

    def _extract_headings(self, soup: Any) -> tuple[dict[str, list[str]], dict[str, int]]:
        headings: dict[str, list[str]] = {}
        counts: dict[str, int] = {}
        for level in range(1, 7):
            key = f"h{level}"
            tags = soup.find_all(key)
            texts = [t.get_text().strip() for t in tags if t.get_text().strip()]
            headings[key] = texts
            counts[key] = len(texts)
        return headings, counts

    def _extract_heading_hierarchy(self, soup: Any) -> list[int]:
        hierarchy: list[int] = []
        for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            level = int(heading.name[1])
            hierarchy.append(level)
        return hierarchy

    def _extract_links(self, soup: Any, page_url: str) -> list[LinkInfo]:
        links: list[LinkInfo] = []
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href", "")).strip()
            if not href:
                continue
            if href.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
                continue
            text = anchor.get_text().strip()
            resolved = resolve_relative(page_url, href)
            try:
                normalized = URLNormalizer.normalize_url(resolved)
            except (ValueError, Exception):
                normalized = resolved

            internal = self._is_internal(normalized, page_url)
            links.append(
                LinkInfo(
                    href=href,
                    text=text[:200],
                    internal=internal,
                )
            )
        return links

    def _classify_links(
        self, soup: Any, page_url: str, links: list[LinkInfo]
    ) -> tuple[list[LinkInfo], list[LinkInfo]]:
        internal, external = [], []
        for link in links:
            if link.internal:
                internal.append(link)
            else:
                external.append(link)
        return internal, external

    def _is_internal(self, url: str, base_url: str) -> bool:
        try:
            from urllib.parse import urlsplit
            url_host = urlsplit(url).hostname or ""
            base_host = urlsplit(base_url).hostname or ""
            return URLNormalizer.is_same_site(url_host, base_host)
        except Exception:
            return False

    def _extract_images(self, soup: Any, page_url: str) -> list[ImageInfo]:
        images: list[ImageInfo] = []
        for img in soup.find_all("img", src=True):
            src = str(img.get("src", "")).strip()
            if not src or src.startswith("data:"):
                continue
            alt = str(img.get("alt", "") or "")
            has_alt = img.has_attr("alt")
            try:
                width = int(img.get("width")) if img.get("width") else None
            except (ValueError, TypeError):
                width = None
            try:
                height = int(img.get("height")) if img.get("height") else None
            except (ValueError, TypeError):
                height = None

            resolved = resolve_relative(page_url, src)
            images.append(
                ImageInfo(
                    src=resolved,
                    alt=alt,
                    has_alt=has_alt,
                    width=width,
                    height=height,
                )
            )
        return images

    def _extract_favicon_urls(self, soup: Any, page_url: str) -> list[str]:
        """Extract favicon URLs from <link rel=icon> and <meta> tags."""
        favicons: list[str] = []
        for link in soup.find_all(
            "link", rel=re.compile(r"(icon|shortcut\s+icon|apple-touch-icon)", re.IGNORECASE)
        ):
            href = link.get("href")
            if href:
                resolved = resolve_relative(page_url, str(href))
                favicons.append(resolved)
        meta_icon = soup.find("meta", attrs={"name": re.compile(r"^msapplication-TileImage$", re.IGNORECASE)})
        if meta_icon:
            content = meta_icon.get("content", "")
            if content:
                favicons.append(str(content))
        return favicons

    def _extract_content(self, soup: Any) -> tuple[str, int, int, int]:
        for element in soup(["script", "style", "noscript", "nav", "svg", "iframe"]):
            element.decompose()

        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        char_count = len(text)
        words = text.split() if text else []
        word_count = len(words)

        paragraphs = soup.find_all("p")
        paragraph_count = len(paragraphs)

        return text, word_count, char_count, paragraph_count

    def build_rule_data(self, parsed: ParsedPage, crawl_result: Any = None) -> dict[str, Any]:
        """Build the data dict consumed by the rule engine.

        Combines parsed page data with crawl result metadata.
        """
        return {
            "url": parsed.url,
            "final_url": crawl_result.final_url if crawl_result else parsed.final_url,
            "status_code": crawl_result.status_code if crawl_result else parsed.http_status,
            "headers": crawl_result.headers if crawl_result else {},
            "title": parsed.title,
            "description": parsed.description,
            "keywords": parsed.keywords,
            "headings": parsed.headings,
            "heading_counts": parsed.heading_counts,
            "heading_hierarchy": parsed.heading_hierarchy,
            "links": [
                {
                    "href": l.href,
                    "text": l.text,
                    "internal": l.internal,
                }
                for l in parsed.links
            ],
            "internal_links_count": len(parsed.internal_links),
            "external_links_count": len(parsed.external_links),
            "internal_links": [
                {"href": l.href, "text": l.text} for l in parsed.internal_links
            ],
            "external_links": [
                {"href": l.href, "text": l.text} for l in parsed.external_links
            ],
            "images": [
                {
                    "src": img.src,
                    "alt": img.alt,
                    "has_alt": img.has_alt,
                    "width": img.width,
                    "height": img.height,
                }
                for img in parsed.images
            ],
            "images_without_alt": sum(1 for img in parsed.images if not img.has_alt),
            "word_count": parsed.word_count,
            "char_count": parsed.char_count,
            "content_text": parsed.content_text,
            "canonical": parsed.canonical,
            "canonical_source_count": parsed.canonical_source_count,
            "robots_meta": parsed.robots_meta,
            "viewport": parsed.viewport,
            "favicon_urls": parsed.favicon_urls,
            "charset": parsed.charset,
            "language": parsed.language,
            "doctype": parsed.doctype,
            "structured_data": parsed.structured_data,
            "open_graph": parsed.open_graph,
            "social": parsed.social,
        }


__all__ = ["PageParser"]
