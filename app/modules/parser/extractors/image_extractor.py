from __future__ import annotations

from bs4 import BeautifulSoup

from app.modules.parser.models.image_data import ImageData
from app.modules.parser.services.document_parser_service import DocumentContext


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
            results.append(
                ImageData(
                    resource_type="image",
                    url=str(tag.get("src", "")).strip(),
                    tag="img",
                    alt=str(tag.get("alt", "")).strip(),
                    title=str(tag.get("title", "")).strip(),
                    width=str(tag.get("width", "")).strip(),
                    height=str(tag.get("height", "")).strip(),
                    loading=str(tag.get("loading", "")).strip(),
                    decoding=str(tag.get("decoding", "")).strip(),
                    srcset=str(tag.get("srcset", "")).strip(),
                    sizes=str(tag.get("sizes", "")).strip(),
                    attributes={str(k): str(v) for k, v in tag.attrs.items()},
                )
            )

        for picture in soup.find_all("picture"):
            for source in picture.find_all("source"):
                results.append(
                    ImageData(
                        resource_type="image",
                        url=str(source.get("srcset", "")).strip().split(",")[0].split()[0],
                        tag="source",
                        alt=str(source.get("alt", "")).strip(),
                        srcset=str(source.get("srcset", "")).strip(),
                        sizes=str(source.get("sizes", "")).strip(),
                        attributes={str(k): str(v) for k, v in source.attrs.items()},
                    )
                )

        return results
