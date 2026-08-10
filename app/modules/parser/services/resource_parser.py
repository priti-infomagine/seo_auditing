from bs4 import BeautifulSoup

from ..schemas.resource_schema import ResourceData
from .html_parser import ParserContext


class ResourceParser:

    def parse(self, context: ParserContext):
        soup: BeautifulSoup = context.soup

        resources = []

        resources.extend(
            self._images(soup)
        )

        resources.extend(
            self._scripts(soup)
        )

        resources.extend(
            self._stylesheets(soup)
        )

        resources.extend(
            self._iframes(soup)
        )

        resources.extend(
            self._media(soup)
        )

        return resources

    @staticmethod
    def _images(soup):
        results = []

        for tag in soup.find_all("img"):
            results.append(
                ResourceData(
                    resource_type="image",
                    tag="img",
                    url=str(
                        tag.get("src", "")
                    ).strip(),
                    alt=str(
                        tag.get("alt", "")
                    ).strip(),
                    title=str(
                        tag.get("title", "")
                    ).strip(),
                    width=str(
                        tag.get("width", "")
                    ).strip(),
                    height=str(
                        tag.get("height", "")
                    ).strip(),
                    loading=str(
                        tag.get("loading", "")
                    ).strip(),
                    decoding=str(
                        tag.get("decoding", "")
                    ).strip(),
                    srcset=str(
                        tag.get("srcset", "")
                    ).strip(),
                    sizes=str(
                        tag.get("sizes", "")
                    ).strip(),
                    attributes={
                        key: str(value)
                        for key, value in tag.attrs.items()
                    },
                )
            )

        return results

    @staticmethod
    def _scripts(soup):
        return [
            ResourceData(
                resource_type="script",
                tag="script",
                url=str(
                    tag.get("src", "")
                ).strip(),
                attributes={
                    key: str(value)
                    for key, value in tag.attrs.items()
                },
            )
            for tag in soup.find_all("script")
            if tag.get("src")
        ]

    @staticmethod
    def _stylesheets(soup):
        results = []

        for tag in soup.find_all("link"):
            rel = tag.get("rel", [])

            if isinstance(rel, str):
                rel = rel.split()

            rel = [
                str(value).lower()
                for value in rel
            ]

            if "stylesheet" not in rel:
                continue

            results.append(
                ResourceData(
                    resource_type="stylesheet",
                    tag="link",
                    url=str(
                        tag.get("href", "")
                    ).strip(),
                    rel=rel,
                    attributes={
                        key: str(value)
                        for key, value in tag.attrs.items()
                    },
                )
            )

        return results

    @staticmethod
    def _iframes(soup):
        return [
            ResourceData(
                resource_type="iframe",
                tag="iframe",
                url=str(
                    tag.get("src", "")
                ).strip(),
                attributes={
                    key: str(value)
                    for key, value in tag.attrs.items()
                },
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
                        url=str(
                            tag.get("src", "")
                        ).strip(),
                        attributes={
                            key: str(value)
                            for key, value in tag.attrs.items()
                        },
                    )
                )

        return results