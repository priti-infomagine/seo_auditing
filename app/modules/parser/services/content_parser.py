import copy
import re

from bs4 import BeautifulSoup

from ..schemas.content_schema import (
    ContentData,
    HeadingData,
    ListData,
    ParagraphData,
    SemanticElement,
    TableData,
)
from .html_parser import ParserContext


class ContentParser:

    def parse(self, context: ParserContext) -> ContentData:
        soup = context.soup

        text = self._get_visible_text(soup)
        normalized_text = self._normalize_text(text)

        return ContentData(
            text=text,
            normalized_text=normalized_text,
            word_count=self._word_count(normalized_text),
            character_count=len(normalized_text),
            paragraphs=self._paragraphs(soup),
            headings=self._headings(soup),
            lists=self._lists(soup),
            tables=self._tables(soup),
            semantic_elements=self._semantic_elements(soup),
            has_main=soup.find("main") is not None,
            has_article=soup.find("article") is not None,
            has_header=soup.find("header") is not None,
            has_footer=soup.find("footer") is not None,
            has_nav=soup.find("nav") is not None,
        )

    @staticmethod
    def _get_visible_text(soup: BeautifulSoup) -> str:
        working = copy.copy(soup)
        for tag in working(
            ["script", "style", "noscript", "template"]
        ):
            tag.decompose()
        return working.get_text(" ", strip=True)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _word_count(text: str) -> int:
        if not text:
            return 0
        return len(text.split())

    @staticmethod
    def _paragraphs(soup: BeautifulSoup):
        return [
            ParagraphData(
                text=tag.get_text(" ", strip=True)
            )
            for tag in soup.find_all("p")
            if tag.get_text(" ", strip=True)
        ]

    @staticmethod
    def _headings(soup: BeautifulSoup):
        results = []
        position = 0

        for tag in soup.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6"]
        ):
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

    @staticmethod
    def _lists(soup: BeautifulSoup):
        results = []

        for tag in soup.find_all(["ul", "ol"]):
            items = [
                item.get_text(" ", strip=True)
                for item in tag.find_all("li", recursive=False)
            ]

            results.append(
                ListData(
                    ordered=tag.name == "ol",
                    items=items,
                )
            )

        return results

    @staticmethod
    def _tables(soup: BeautifulSoup):
        results = []

        for table in soup.find_all("table"):
            headers = [
                cell.get_text(" ", strip=True)
                for cell in table.find_all("th")
            ]

            rows = []

            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])

                if not cells:
                    continue

                rows.append([
                    cell.get_text(" ", strip=True)
                    for cell in cells
                ])

            results.append(
                TableData(
                    headers=headers,
                    rows=rows,
                )
            )

        return results

    @staticmethod
    def _semantic_elements(soup: BeautifulSoup):
        tags = [
            "main",
            "article",
            "section",
            "nav",
            "header",
            "footer",
            "aside",
            "figure",
            "figcaption",
            "address",
            "time",
        ]

        return [
            SemanticElement(
                tag=tag.name,
                text=tag.get_text(" ", strip=True),
            )
            for tag in soup.find_all(tags)
        ]
