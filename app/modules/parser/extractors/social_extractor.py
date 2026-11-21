from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.modules.parser.models.social_data import (
    SocialData,
    OpenGraphData,
    TwitterCardData,
    SocialLink,
    SharingButton,
)
from app.modules.parser.services.document_parser_service import DocumentContext


class SocialExtractor:
    """
    Extracts OpenGraph and Twitter Card metadata, social profile links,
    and social sharing buttons.

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

    # Common social sharing URL patterns
    SHARING_PATTERNS = {
        "facebook": [
            r"facebook\.com/sharer",
            r"facebook\.com/dialog/share",
        ],
        "twitter": [
            r"twitter\.com/intent/tweet",
            r"x\.com/intent/tweet",
        ],
        "linkedin": [
            r"linkedin\.com/sharing/share-offsite",
            r"linkedin\.com/shareArticle",
        ],
        "pinterest": [
            r"pinterest\.com/pin/create",
        ],
        "reddit": [
            r"reddit\.com/submit",
        ],
        "whatsapp": [
            r"whatsapp\.com/send",
            r"api\.whatsapp\.com/send",
        ],
        "telegram": [
            r"t\.me/share",
        ],
        "email": [
            r"mailto:\?",
        ],
    }

    # Common class/id patterns for sharing buttons
    SHARING_SELECTORS = [
        "[class*='share']",
        "[class*='social-share']",
        "[class*='social-share-button']",
        "[class*='share-button']",
        "[id*='share']",
        "[data-share]",
        "[data-social-share]",
        ".addthis_button",
        ".sharethis-button",
        "[class*='tweet-button']",
        "[class*='fb-share']",
        "[class*='linkedin-share']",
    ]

    def extract(self, context: DocumentContext) -> SocialData:
        soup = context.soup
        return SocialData(
            open_graph=OpenGraphData(tags=self._open_graph(soup)),
            twitter=TwitterCardData(tags=self._twitter(soup)),
            social_links=self._social_links(soup),
            sharing_buttons=self._sharing_buttons(soup),
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

    def _social_links(self, soup: BeautifulSoup) -> List[SocialLink]:
        """Extract links to social media profiles."""
        links: List[SocialLink] = []
        seen_urls = set()

        for link in soup.find_all("a", href=True):
            href = str(link.get("href", "")).strip()
            if not href:
                continue

            # Normalize URL for deduplication
            normalized = self._normalize_url(href)
            if normalized in seen_urls:
                continue

            platform = self._identify_platform(href)
            if platform:
                text = link.get_text(strip=True) if link.get_text() else None
                links.append(SocialLink(platform=platform, url=href, text=text))
                seen_urls.add(normalized)

        return links

    def _sharing_buttons(self, soup: BeautifulSoup) -> List[SharingButton]:
        """Extract social sharing buttons."""
        buttons: List[SharingButton] = []
        seen = set()

        # Check for sharing links by URL pattern
        for link in soup.find_all("a", href=True):
            href = str(link.get("href", "")).strip()
            if not href:
                continue

            platform = self._identify_sharing_platform(href)
            if platform:
                key = f"{platform}:{href}"
                if key in seen:
                    continue
                text = link.get_text(strip=True) if link.get_text() else None
                buttons.append(SharingButton(
                    platform=platform,
                    selector=f"a[href='{href}']",
                    url=href,
                    text=text,
                ))
                seen.add(key)

        # Check for buttons by CSS selectors
        for selector in self.SHARING_SELECTORS:
            try:
                elements = soup.select(selector)
                for el in elements:
                    # Try to identify platform from class/id/data attributes
                    platform = self._identify_platform_from_element(el)
                    if not platform:
                        continue

                    href = el.get("href") or el.get("data-url") or el.get("data-href")
                    if href:
                        href = str(href).strip()
                        key = f"{platform}:{href}"
                    else:
                        # Use element identifier as key
                        key = f"{platform}:{selector}:{id(el)}"

                    if key in seen:
                        continue

                    text = el.get_text(strip=True) if el.get_text() else None
                    buttons.append(SharingButton(
                        platform=platform,
                        selector=selector,
                        url=href if href else None,
                        text=text,
                    ))
                    seen.add(key)
            except Exception:
                # Invalid selector, skip
                continue

        return buttons

    def _identify_platform(self, url: str) -> Optional[str]:
        """Identify social platform from profile URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            for platform, domains in self.SOCIAL_DOMAINS.items():
                if any(d in domain for d in domains):
                    return platform
        except Exception:
            pass
        return None

    def _identify_sharing_platform(self, url: str) -> Optional[str]:
        """Identify social platform from sharing URL."""
        url_lower = url.lower()
        for platform, patterns in self.SHARING_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url_lower):
                    return platform
        return None

    def _identify_platform_from_element(self, element) -> Optional[str]:
        """Identify platform from element attributes."""
        # Check class names
        classes = element.get("class", [])
        if isinstance(classes, str):
            classes = [classes]
        class_str = " ".join(classes).lower()

        # Check id
        el_id = element.get("id", "").lower()

        # Check data attributes
        data_attrs = {k: v for k, v in element.attrs.items() if k.startswith("data-")}
        data_str = " ".join(str(v).lower() for v in data_attrs.values())

        combined = f"{class_str} {el_id} {data_str}"

        platform_keywords = {
            "facebook": ["facebook", "fb-", "fb_"],
            "twitter": ["twitter", "tweet", "x-", "x_"],
            "linkedin": ["linkedin", "li-", "in-"],
            "pinterest": ["pinterest", "pin-"],
            "reddit": ["reddit"],
            "whatsapp": ["whatsapp", "wa-"],
            "telegram": ["telegram", "tg-"],
            "email": ["email", "mail-", "mailto"],
        }

        for platform, keywords in platform_keywords.items():
            if any(kw in combined for kw in keywords):
                return platform

        return None

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication."""
        try:
            parsed = urlparse(url)
            # Remove fragment, normalize scheme/host
            normalized = f"{parsed.scheme}://{parsed.netloc.lower()}{parsed.path}"
            # Remove trailing slash
            if normalized.endswith("/") and len(normalized) > len(f"{parsed.scheme}://{parsed.netloc.lower()}"):
                normalized = normalized[:-1]
            return normalized
        except Exception:
            return url