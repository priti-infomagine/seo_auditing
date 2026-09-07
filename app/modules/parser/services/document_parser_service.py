from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from bs4 import BeautifulSoup

from app.modules.parser.exceptions import HTMLParseError


@dataclass
class DocumentContext:
    html: str
    url: str
    soup: BeautifulSoup

    doctype: str = ""
    language: str = ""
    charset: str = ""

    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class DocumentParserService:
    """
    Centralized HTML DOM parsing.

    Parses HTML exactly once per page and produces a DocumentContext
    shared by all extractors. The DOM must never be reparsed inside
    individual extractors.
    """

    def parse(self, html: str, url: str = "") -> DocumentContext:
        if not html:
            return DocumentContext(
                html=html,
                url=url,
                soup=BeautifulSoup("", "html.parser"),
                errors=["HTML content is empty"],
            )

        try:
            soup = BeautifulSoup(html, "html.parser")
            doctype = self._extract_doctype(html)

            html_tag = soup.find("html")
            language = ""
            if html_tag:
                language = str(html_tag.get("lang", "")).strip()

            charset = ""
            charset_tag = soup.find("meta", attrs={"charset": True})
            if charset_tag:
                charset = str(charset_tag.get("charset", "")).strip()

            return DocumentContext(
                html=html,
                url=url,
                soup=soup,
                doctype=doctype,
                language=language,
                charset=charset,
            )
        except Exception as exc:
            raise HTMLParseError(
                f"Failed to parse HTML: {exc}"
            ) from exc

    @staticmethod
    def _extract_doctype(html: str) -> str:
        upper = html.lstrip().upper()
        if not upper.startswith("<!DOCTYPE"):
            return ""
        end = html.find(">")
        if end == -1:
            return ""
        return html[9:end].strip()
