from __future__ import annotations

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.modules.parser.models.link_data import LinkData
from app.modules.parser.services.document_parser_service import DocumentContext
from app.modules.parser.normalizers.url_normalizer import normalize_rel, is_internal


class LinkExtractor:
    """
    Extracts all anchor elements.

    Does not evaluate SEO quality of links.
    """

    def extract(self, context: DocumentContext) -> list[LinkData]:
        soup = context.soup
        results = []

        for tag in soup.find_all("a"):
            href = str(tag.get("href", "")).strip()
            # Store raw href before normalization
            raw_href = str(tag.get("href", ""))

            if not href:
                continue

            rel = tag.get("rel", [])
            if isinstance(rel, str):
                rel = rel.split()
            rel = [str(value).strip().lower() for value in rel]

            # Extract accessible name components (WCAG 2.1)
            # Priority: aria-label > aria-labelledby > title > link text
            aria_label = str(tag.get("aria-label", "")).strip()
            aria_labelledby = str(tag.get("aria-labelledby", "")).strip()
            title_attr = str(tag.get("title", "")).strip()
            link_text = tag.get_text(" ", strip=True)

            # Compute accessible name per WCAG
            accessible_name = aria_label or aria_labelledby or title_attr or link_text or ""

            # Determine if link is internal or external
            absolute_url = urljoin(context.url, href)
            link_is_internal = is_internal(context.url, absolute_url)
            link_is_external = not link_is_internal

            attributes = {}
            raw_attributes = {}
            for key, value in tag.attrs.items():
                if isinstance(value, list):
                    attributes[key] = " ".join(str(item) for item in value)
                    raw_attributes[key] = " ".join(str(item) for item in value)
                else:
                    attributes[key] = str(value)
                    raw_attributes[key] = str(value)

            results.append(
                LinkData(
                    href=href,
                    text=link_text,
                    accessible_name=accessible_name,
                    aria_label=aria_label,
                    aria_labelledby=aria_labelledby,
                    is_internal=link_is_internal,
                    is_external=link_is_external,
                    rel=rel,
                    target=str(tag.get("target", "")).strip(),
                    title=title_attr,
                    download=str(tag.get("download", "")).strip(),
                    absolute_url=absolute_url,
                    attributes=attributes,
                    raw_href=raw_href,
                    raw_attributes=raw_attributes,
                )
            )

        return results
