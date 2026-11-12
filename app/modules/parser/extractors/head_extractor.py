from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from app.modules.parser.models.head_data import HeadData
from app.modules.parser.services.document_parser_service import DocumentContext


class HeadExtractor:
    """Extracts resource hints and metadata from <head> element."""

    def extract(self, context: DocumentContext) -> HeadData:
        soup = context.soup
        head = soup.find("head")
        if not head:
            return HeadData()

        preconnect_hints = []
        dns_prefetch_hints = []
        preload_hints = []
        google_fonts_urls = []
        meta_http_equiv = {}

        for link in head.find_all("link", href=True):
            rel = " ".join(link.get("rel", [])).lower()
            href = link["href"].strip()
            attrs = {str(k): str(v) for k, v in link.attrs.items()}

            if "preconnect" in rel:
                preconnect_hints.append({
                    "href": href,
                    "crossorigin": link.get("crossorigin"),
                    "attributes": attrs,
                })
            if "dns-prefetch" in rel:
                dns_prefetch_hints.append({
                    "href": href,
                    "attributes": attrs,
                })
            if "preload" in rel:
                preload_hints.append({
                    "href": href,
                    "as": link.get("as"),
                    "crossorigin": link.get("crossorigin"),
                    "fetchpriority": link.get("fetchpriority"),
                    "attributes": attrs,
                })

            # Google Fonts detection
            if "fonts.googleapis.com" in href or "fonts.gstatic.com" in href:
                google_fonts_urls.append({
                    "href": href,
                    "rel": rel,
                    "attributes": attrs,
                })

        # Meta http-equiv headers
        for meta in head.find_all("meta", attrs={"http-equiv": True}):
            meta_http_equiv[meta["http-equiv"].lower()] = meta.get("content", "").strip()

        return HeadData(
            preconnect_hints=preconnect_hints,
            dns_prefetch_hints=dns_prefetch_hints,
            preload_hints=preload_hints,
            google_fonts_urls=google_fonts_urls,
            meta_http_equiv=meta_http_equiv,
        )