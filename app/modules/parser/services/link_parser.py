from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..schemas.link_schema import LinkData
from .helpers.html_parser import ParserContext


class LinkParser:

    def parse(self, context: ParserContext):
        soup: BeautifulSoup = context.soup

        results = []

        for tag in soup.find_all("a"):
            href = str(tag.get("href", "")).strip()

            if not href:
                continue

            rel = tag.get("rel", [])

            if isinstance(rel, str):
                rel = rel.split()

            rel = [
                str(value).strip().lower()
                for value in rel
            ]

            attributes = {}

            for key, value in tag.attrs.items():
                if isinstance(value, list):
                    attributes[key] = " ".join(
                        str(item) for item in value
                    )
                else:
                    attributes[key] = str(value)

            results.append(
                LinkData(
                    href=href,
                    text=tag.get_text(" ", strip=True),
                    rel=rel,
                    target=str(
                        tag.get("target", "")
                    ).strip(),
                    title=str(
                        tag.get("title", "")
                    ).strip(),
                    download=str(
                        tag.get("download", "")
                    ).strip(),
                    absolute_url=urljoin(
                        context.url,
                        href,
                    ),
                    attributes=attributes,
                )
            )

        return results