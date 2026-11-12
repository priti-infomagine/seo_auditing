from __future__ import annotations

from bs4 import BeautifulSoup

from app.modules.parser.models.resource_data import ResourceData
from app.modules.parser.services.document_parser_service import DocumentContext


class ResourceExtractor:
    """
    Extracts references to external resources.

    Does not decide whether resources are SEO-compliant.
    """

    def extract(self, context: DocumentContext) -> list[ResourceData]:
        soup = context.soup
        results = []
        results.extend(self._images(soup))
        results.extend(self._scripts(soup))
        results.extend(self._stylesheets(soup))
        results.extend(self._iframes(soup))
        results.extend(self._media(soup))
        return results

    @staticmethod
    def _images(soup):
        results = []
        for tag in soup.find_all("img"):
            results.append(
                ResourceData(
                    resource_type="image",
                    tag="img",
                    url=str(tag.get("src", "")).strip(),
                    alt=str(tag.get("alt", "")).strip(),
                    title=str(tag.get("title", "")).strip(),
                    width=str(tag.get("width", "")).strip(),
                    height=str(tag.get("height", "")).strip(),
                    loading=str(tag.get("loading", "")).strip(),
                    decoding=str(tag.get("decoding", "")).strip(),
                    srcset=str(tag.get("srcset", "")).strip(),
                    sizes=str(tag.get("sizes", "")).strip(),
                    fetchpriority=str(tag.get("fetchpriority", "")).strip(),
                    attributes={str(k): str(v) for k, v in tag.attrs.items()},
                )
            )
        return results

    @staticmethod
    def _scripts(soup):
        results = []
        for tag in soup.find_all("script"):
            if not tag.get("src"):
                continue
            attrs = {str(k): str(v) for k, v in tag.attrs.items()}
            async_attr = tag.get("async") is not None
            defer_attr = tag.get("defer") is not None
            module_attr = tag.get("type") == "module"
            fetchpriority = str(tag.get("fetchpriority", "")).strip()
            results.append(
                ResourceData(
                    resource_type="script",
                    tag="script",
                    url=str(tag.get("src", "")).strip(),
                    async_attr=async_attr,
                    defer_attr=defer_attr,
                    module_attr=module_attr,
                    fetchpriority=fetchpriority,
                    attributes=attrs,
                )
            )
        return results

    @staticmethod
    def _stylesheets(soup):
        results = []
        for tag in soup.find_all("link"):
            rel = tag.get("rel", [])
            if isinstance(rel, str):
                rel = rel.split()
            rel = [str(value).lower() for value in rel]
            if "stylesheet" not in rel:
                continue
            attrs = {str(k): str(v) for k, v in tag.attrs.items()}
            media = str(tag.get("media", "")).strip()
            fetchpriority = str(tag.get("fetchpriority", "")).strip()
            results.append(
                ResourceData(
                    resource_type="stylesheet",
                    tag="link",
                    url=str(tag.get("href", "")).strip(),
                    rel=rel,
                    media=media,
                    fetchpriority=fetchpriority,
                    attributes=attrs,
                )
            )
        return results

    @staticmethod
    def _iframes(soup):
        return [
            ResourceData(
                resource_type="iframe",
                tag="iframe",
                url=str(tag.get("src", "")).strip(),
                attributes={str(k): str(v) for k, v in tag.attrs.items()},
            )
            for tag in soup.find_all("iframe")
        ]

    @staticmethod
    def _media(soup):
        results = []
        for tag_name in ["video", "audio"]:
            for tag in soup.find_all(tag_name):
                results.append(
                    ResourceData(
                        resource_type=tag_name,
                        tag=tag_name,
                        url=str(tag.get("src", "")).strip(),
                        attributes={str(k): str(v) for k, v in tag.attrs.items()},
                    )
                )
        return results
