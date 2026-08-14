from __future__ import annotations

from bs4 import BeautifulSoup

from app.modules.parser.models.content_data import HeadingData
from app.modules.parser.services.document_parser_service import DocumentContext


class HeadingExtractor:
    """
    Extracts heading tags (H1-H6) preserving source order.
    """

    def extract(self, context: DocumentContext) -> list[HeadingData]:
        soup = context.soup
        results = []
        position = 0

        for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            text = tag.get_text(" ", strip=True)
            if not text:
                continue
            results.append(
                HeadingData(
                    level=int(tag.name[1]),
                    text=text,
                    position=position,
                )
            )
            position += 1

        return results
