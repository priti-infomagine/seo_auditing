from __future__ import annotations

from bs4 import BeautifulSoup

from app.modules.crawler.utils import url
from app.modules.parser.models.image_data import ImageData
from app.modules.parser.services.document_parser_service import DocumentContext


def get_first_srcset_url(srcset) -> str:
    if not srcset:
        return ""

    srcset = str(srcset).strip()

    if not srcset:
        return ""

    first_candidate = srcset.split(",")[0].strip()

    if not first_candidate:
        return ""

    parts = first_candidate.split()

    if not parts:
        return ""

    return parts[0]


class ImageExtractor:
    """
    Extracts image elements.

    Supports img, picture, and source tags.
    Does not decide whether an image is SEO-compliant.
    """

    def extract(self, context: DocumentContext) -> list[ImageData]:
        soup = context.soup
        results = []

        for tag in soup.find_all("img"):
            url_str = str(tag.get("src", "")).strip()
            results.append(
                ImageData(
                    resource_type="image",
                    url=url_str,
                    tag="img",
                    alt=str(tag.get("alt", "")).strip(),
                    title=str(tag.get("title", "")).strip(),
                    width=str(tag.get("width", "")).strip(),
                    height=str(tag.get("height", "")).strip(),
                    loading=str(tag.get("loading", "")).strip(),
                    decoding=str(tag.get("decoding", "")).strip(),
                    srcset=str(tag.get("srcset", "")).strip(),
                    sizes=str(tag.get("sizes", "")).strip(),
                    fetchpriority=str(tag.get("fetchpriority", "")).strip(),
                    is_gif=url_str.lower().endswith(".gif"),
                    attributes={str(k): str(v) for k, v in tag.attrs.items()},
                )
            )

        for picture in soup.find_all("picture"):
            for source in picture.find_all("source"):
                srcset_url = get_first_srcset_url(source.get("srcset"))
                results.append(
                    ImageData(
                        resource_type="image",
                        url=srcset_url,
                        tag="source",
                        alt=str(source.get("alt", "")).strip(),
                        srcset=str(source.get("srcset", "")).strip(),
                        sizes=str(source.get("sizes", "")).strip(),
                        fetchpriority=str(source.get("fetchpriority", "")).strip(),
                        is_gif=srcset_url.lower().endswith(".gif"),
                        attributes={str(k): str(v) for k, v in source.attrs.items()},
                    )
                )

        return results
