from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from app.modules.parser.models.technical_data import TechnicalData, IframeData
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

        # Extract iframe details
        iframes = self._extract_iframes(soup)
        iframe_count = len(iframes)

        script_count = len(soup.find_all("script"))
        style_count = len(soup.find_all("style"))
        inline_scripts = len(soup.find_all("script", src=False))
        inline_styles = len(soup.find_all("style"))

        external_resource_count = (
            len(soup.find_all("link", rel="stylesheet"))
            + len(soup.find_all("script", src=True))
            + len(soup.find_all("img", src=True))
        )

        # DOM element count for DOM size rule
        dom_elements = len(soup.find_all())

        # Viewport zoom analysis
        viewport_zoom_allows = self._check_viewport_zoom(soup)

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
            dom_elements=dom_elements,
            iframes=iframes,
            viewport_zoom_allows=viewport_zoom_allows,
        )

    def _extract_iframes(self, soup: BeautifulSoup) -> list[IframeData]:
        """Extract iframe elements with accessibility-relevant attributes."""
        iframes = []
        for iframe in soup.find_all("iframe"):
            title = iframe.get("title", "").strip()
            # Handle attributes that may be AttributeValueList (multiple values)
            sandbox = iframe.get("sandbox", "")
            if isinstance(sandbox, list):
                sandbox = " ".join(sandbox)
            sandbox = sandbox.strip()
            
            allow = iframe.get("allow", "")
            if isinstance(allow, list):
                allow = " ".join(allow)
            allow = allow.strip()
            
            iframes.append(IframeData(
                src=iframe.get("src", "").strip(),
                title=title,
                name=iframe.get("name", "").strip(),
                id=iframe.get("id", "").strip(),
                sandbox=sandbox,
                allow=allow,
                has_title=bool(title),
            ))
        return iframes

    def _check_viewport_zoom(self, soup: BeautifulSoup) -> bool:
        """Check if viewport meta tag allows zoom."""
        tag = soup.find("meta", attrs={"name": "viewport"})
        if not tag:
            return True  # No viewport tag means zoom is allowed by default

        content = tag.get("content", "").strip().lower()
        if not content:
            return True

        # Check for zoom-blocking directives
        # user-scalable=no, user-scalable=0
        if re.search(r"user-scalable\s*=\s*(no|0)", content):
            return False

        # maximum-scale=1 or less (blocks zoom in)
        max_scale_match = re.search(r"maximum-scale\s*=\s*([\d.]+)", content)
        if max_scale_match:
            try:
                if float(max_scale_match.group(1)) <= 1.0:
                    return False
            except ValueError:
                pass

        # minimum-scale=1 or more (blocks zoom out)
        min_scale_match = re.search(r"minimum-scale\s*=\s*([\d.]+)", content)
        if min_scale_match:
            try:
                if float(min_scale_match.group(1)) >= 1.0:
                    return False
            except ValueError:
                pass

        return True

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