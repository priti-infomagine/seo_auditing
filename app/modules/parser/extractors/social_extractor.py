from __future__ import annotations

import re
from typing import List

from bs4 import BeautifulSoup

from app.modules.parser.models.social_data import (
    SocialData,
    OpenGraphData,
    TwitterCardData,
)
from app.modules.parser.services.document_parser_service import DocumentContext


class SocialExtractor:
    """
    Extracts OpenGraph and Twitter Card metadata.

    Keeps the extraction extensible for additional social platforms.
    """

    SOCIAL_DOMAINS = {
        "facebook": ["facebook.com", "fb.com"],
        "twitter": ["twitter.com", "x.com"],
        "linkedin": ["linkedin.com"],
        "instagram": ["instagram.com"],
        "youtube": ["youtube.com", "youtu.be"],
        "pinterest": ["pinterest.com", "pin.it"],
        "tiktok": ["tiktok.com"],
        "github": ["github.com"],
    }

    def extract(self, context: DocumentContext) -> SocialData:
        soup = context.soup
        return SocialData(
            open_graph=OpenGraphData(tags=self._open_graph(soup)),
            twitter=TwitterCardData(tags=self._twitter(soup)),
        )

    @staticmethod
    def _open_graph(soup: BeautifulSoup) -> dict[str, list[str]]:
        result = {}
        for tag in soup.find_all("meta", attrs={"property": re.compile("^og:", re.IGNORECASE)}):
            key = str(tag.get("property", "")).strip()
            value = str(tag.get("content", "")).strip()
            if key and value:
                result.setdefault(key.lower(), []).append(value)
        return result

    @staticmethod
    def _twitter(soup: BeautifulSoup) -> dict[str, list[str]]:
        result = {}
        for tag in soup.find_all("meta", attrs={"name": re.compile("^twitter:", re.IGNORECASE)}):
            key = str(tag.get("name", "")).strip()
            value = str(tag.get("content", "")).strip()
            if key and value:
                result.setdefault(key.lower(), []).append(value)
        return result
