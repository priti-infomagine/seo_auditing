from __future__ import annotations

import re

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


# Regex to find background-image: url(...) in inline style attributes and <style> blocks
_BG_IMAGE_RE = re.compile(
    r'background-image\s*:\s*url\(["\']?([^"\')\s]+)["\']?\)',
    re.IGNORECASE,
)

# Generic alt text patterns (lowercase)
_GENERIC_ALT_PATTERNS = frozenset({
    "image", "photo", "picture", "banner", "hero", "logo",
    "click here", "here", "read more", "learn more", "more",
    "default", "untitled", "stock", "placeholder", "lorem", "ipsum",
    "image of", "picture of", "photo of",
})

# Generic filename patterns (regex)
_GENERIC_FILENAME_RE = re.compile(
    r'^(IMG_|DSC_|DSCF_|PANO_|PHT_|screenshot|screen_shot|screen-'
    r'|image[\d_]*\.|photo[\d_]*\.|untitled[\d_]*\.|blob[\d_]*\.|'
    r'[a-f0-9]{8,}\.[a-z]+)$',
    re.IGNORECASE,
)


class ImageExtractor:
    """
    Extracts image elements.

    Supports img, picture, source, and CSS background-image tags.
    Does not decide whether an image is SEO-compliant.
    """

    def extract(self, context: DocumentContext) -> list[ImageData]:
        soup = context.soup
        results: list[ImageData] = []

        # ── 1. <img> tags ──────────────────────────────────────────────
        for tag in soup.find_all("img"):
            url_str = str(tag.get("src", "")).strip()
            alt_val = str(tag.get("alt", "")).strip()
            srcset_val = str(tag.get("srcset", "")).strip()
            sizes_val = str(tag.get("sizes", "")).strip()
            width_val = str(tag.get("width", "")).strip()
            height_val = str(tag.get("height", "")).strip()
            loading_val = str(tag.get("loading", "")).strip()

            has_picture_parent = tag.parent is not None and tag.parent.name == "picture"

            results.append(
                ImageData(
                    resource_type="image",
                    url=url_str,
                    tag="img",
                    alt=alt_val,
                    title=str(tag.get("title", "")).strip(),
                    width=width_val,
                    height=height_val,
                    loading=loading_val,
                    decoding=str(tag.get("decoding", "")).strip(),
                    srcset=srcset_val,
                    sizes=sizes_val,
                    fetchpriority=str(tag.get("fetchpriority", "")).strip(),
                    is_gif=url_str.lower().endswith(".gif"),
                    is_decorative=(alt_val == "" and "alt" in tag.attrs),
                    has_srcset=bool(srcset_val),
                    has_sizes=bool(sizes_val),
                    has_picture_parent=has_picture_parent,
                    attributes={str(k): str(v) for k, v in tag.attrs.items()},
                )
            )

        # ── 2. <picture> > <source> tags ───────────────────────────────
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
                        has_srcset=bool(source.get("srcset", "").strip()),
                        has_picture_parent=True,
                        attributes={str(k): str(v) for k, v in source.attrs.items()},
                    )
                )

            # ── 3. Check for <img> fallback inside <picture> ─────────
            has_img_fallback = picture.find("img") is not None
            # Store as a synthetic record so rules can detect missing fallbacks
            if not has_img_fallback:
                results.append(
                    ImageData(
                        resource_type="image",
                        url="",
                        tag="picture_missing_fallback",
                        has_picture_parent=True,
                    )
                )

        # ── 4. CSS background-image (inline style attributes) ─────────
        for tag in soup.find_all(style=True):
            style_attr = str(tag.get("style", ""))
            for match in _BG_IMAGE_RE.finditer(style_attr):
                bg_url = match.group(1).strip()
                results.append(
                    ImageData(
                        resource_type="image",
                        url=bg_url,
                        tag="css_background",
                        is_background_image=True,
                        parent_tag=tag.name,
                        attributes={str(k): str(v) for k, v in tag.attrs.items()},
                    )
                )

        # ── 5. CSS background-image (<style> blocks) ──────────────────
        for style_tag in soup.find_all("style"):
            css_content = style_tag.string or ""
            for match in _BG_IMAGE_RE.finditer(css_content):
                bg_url = match.group(1).strip()
                results.append(
                    ImageData(
                        resource_type="image",
                        url=bg_url,
                        tag="css_background",
                        is_background_image=True,
                        parent_tag="style",
                        attributes={str(k): str(v) for k, v in style_tag.attrs.items()},
                    )
                )

        return results