from __future__ import annotations

from typing import List

from bs4 import BeautifulSoup

from app.modules.parser.models.page_metadata import (
    PageMetadata,
    MetaTag,
    HreflangLink,
)
from app.modules.parser.services.document_parser_service import DocumentContext


class MetadataExtractor:
    """
    Extracts page metadata.

    Produces raw facts only — no SEO pass/fail evaluation.
    """

    def extract(self, context: DocumentContext) -> PageMetadata:
        soup = context.soup

        title = self._title(soup)
        meta_description = self._description(soup)

        return PageMetadata(
            title=title,
            title_length=len(title),
            meta_description=meta_description,
            meta_description_length=len(meta_description),
            robots=self._robots(soup),
            googlebot=self._googlebot(soup),
            viewport=self._viewport(soup),
            charset=context.charset,
            language=context.language,
            canonical=self._canonical(soup),
            hreflang=self._hreflang(soup),
            open_graph=self._open_graph(soup),
            twitter=self._twitter(soup),
            meta_tags=self._meta_tags(soup),
            favicon_urls=self._favicons(soup),
        )

    @staticmethod
    def _title(soup: BeautifulSoup) -> str:
        tag = soup.find("title")
        if not tag:
            return ""
        return tag.get_text(" ", strip=True)

    @staticmethod
    def _description(soup: BeautifulSoup) -> str:
        tag = soup.find(
            "meta",
            attrs={"name": lambda value: isinstance(value, str) and value.lower() == "description"},
        )
        if not tag:
            return ""
        return str(tag.get("content", "")).strip()

    @staticmethod
    def _robots(soup: BeautifulSoup) -> List[MetaTag]:
        results = []
        for tag in soup.find_all("meta"):
            name = str(tag.get("name", "")).strip().lower()
            if name in {"robots", "googlebot", "bingbot"}:
                results.append(
                    MetaTag(
                        name=name,
                        content=str(tag.get("content", "")).strip(),
                    )
                )
        return results

    @staticmethod
    def _viewport(soup: BeautifulSoup) -> str:
        tag = soup.find("meta", attrs={"name": "viewport"})
        if not tag:
            return ""
        return str(tag.get("content", "")).strip()

    @staticmethod
    def _canonical(soup: BeautifulSoup) -> str:
        for tag in soup.find_all("link"):
            rel = tag.get("rel", [])
            if isinstance(rel, str):
                rel = rel.split()
            rel = [str(value).lower() for value in rel]
            if "canonical" in rel:
                return str(tag.get("href", "")).strip()
        return ""

    @staticmethod
    def _googlebot(soup: BeautifulSoup) -> str:
        tag = soup.find("meta", attrs={"name": "googlebot"})
        if tag:
            return str(tag.get("content", "")).strip()
        return ""

    @staticmethod
    def _hreflang(soup: BeautifulSoup) -> List[HreflangLink]:
        results = []
        for tag in soup.find_all("link"):
            rel = tag.get("rel", [])
            if isinstance(rel, str):
                rel = rel.split()
            rel = [str(value).lower() for value in rel]
            if "alternate" not in rel:
                continue
            hreflang = str(tag.get("hreflang", "")).strip()
            if not hreflang:
                continue
            results.append(
                HreflangLink(
                    href=str(tag.get("href", "")).strip(),
                    hreflang=hreflang,
                    rel=rel,
                    is_x_default=(hreflang == "x-default"),
                )
            )
        return results

    @staticmethod
    def _open_graph(soup: BeautifulSoup):
        result = {}
        for tag in soup.find_all("meta"):
            key = str(tag.get("property", "")).strip()
            if not key.lower().startswith("og:"):
                continue
            value = str(tag.get("content", "")).strip()
            result.setdefault(key.lower(), []).append(value)
        return result

    @staticmethod
    def _twitter(soup: BeautifulSoup):
        result = {}
        for tag in soup.find_all("meta"):
            key = str(tag.get("name", "")).strip()
            if not key.lower().startswith("twitter:"):
                continue
            value = str(tag.get("content", "")).strip()
            result.setdefault(key.lower(), []).append(value)
        return result

    @staticmethod
    def _meta_tags(soup: BeautifulSoup) -> List[MetaTag]:
        results = []
        for tag in soup.find_all("meta"):
            results.append(
                MetaTag(
                    name=str(tag.get("name", "")).strip(),
                    property=str(tag.get("property", "")).strip(),
                    content=str(tag.get("content", "")).strip(),
                    http_equiv=str(tag.get("http-equiv", "")).strip(),
                )
            )
        return results

    @staticmethod
    def _favicons(soup: BeautifulSoup) -> List[str]:
        results = []
        for tag in soup.find_all("link"):
            rel = tag.get("rel", [])
            if isinstance(rel, str):
                rel = rel.split()
            rel = [str(x).lower() for x in rel]
            if "icon" in rel or "shortcut" in rel:
                href = str(tag.get("href", "")).strip()
                if href:
                    results.append(href)
        return results
