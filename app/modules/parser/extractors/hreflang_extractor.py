from __future__ import annotations

from bs4 import BeautifulSoup

from app.modules.parser.models.hreflang_data import HreflangData
from app.modules.parser.services.document_parser_service import DocumentContext


class HreflangExtractor:
    """
    Extracts hreflang link elements.

    Produces raw facts — does not validate SEO correctness.
    """

    def extract(self, context: DocumentContext) -> list[HreflangData]:
        soup = context.soup
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
                HreflangData(
                    href=str(tag.get("href", "")).strip(),
                    hreflang=hreflang,
                    rel=rel,
                    is_x_default=(hreflang == "x-default"),
                )
            )

        return results
