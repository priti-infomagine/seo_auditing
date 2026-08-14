from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from app.modules.parser.models.technical_data import TechnicalData
from app.modules.parser.services.document_parser_service import DocumentContext


class TechnicalExtractor:
    """
    Extracts document-level technical facts.

    HTTP-level facts come from crawler/fetch results, not from HTML.
    """

    def extract(self, context: DocumentContext) -> TechnicalData:
        soup = context.soup

        doctype = context.doctype
        html_lang = context.language
        charset = context.charset
        viewport = self._get_viewport(soup)
        base_tag = self._get_base_tag(soup)
        meta_refresh = self._get_meta_refresh(soup)

        iframe_count = len(soup.find_all("iframe"))
        script_count = len(soup.find_all("script"))
        style_count = len(soup.find_all("style"))
        inline_scripts = len(soup.find_all(attrs={"src": False}))
        inline_styles = len(soup.find_all("style"))

        external_resource_count = (
            len(soup.find_all("link", rel="stylesheet"))
            + len(soup.find_all("script", src=True))
            + len(soup.find_all("img", src=True))
        )

        return TechnicalData(
            doctype=doctype,
            html_lang=html_lang,
            charset=charset,
            viewport=viewport,
            base_tag=base_tag,
            meta_refresh=meta_refresh,
            iframe_count=iframe_count,
            script_count=script_count,
            style_count=style_count,
            inline_scripts=inline_scripts,
            inline_styles=inline_styles,
            external_resource_count=external_resource_count,
        )

    @staticmethod
    def _get_viewport(soup: BeautifulSoup) -> str:
        tag = soup.find("meta", attrs={"name": "viewport"})
        return tag.get("content", "").strip() if tag else ""

    @staticmethod
    def _get_base_tag(soup: BeautifulSoup) -> str:
        tag = soup.find("base", href=True)
        return tag.get("href", "").strip() if tag else ""

    @staticmethod
    def _get_meta_refresh(soup: BeautifulSoup) -> str:
        tag = soup.find("meta", attrs={"http-equiv": "refresh"})
        return tag.get("content", "").strip() if tag else ""
