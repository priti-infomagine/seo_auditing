from typing import Any


SUPPORT_MATRIX = {
    "title": (True, True),
    "description": (True, True),
    "keywords": (False, True),
    "author": (False, False),
    "viewport": (True, True),
    "robots": (True, True),
    "theme-color": (False, False),
    "twitter:card": (False, False),
    "twitter:title": (False, False),
    "twitter:description": (False, False),
    "twitter:image": (False, False),
}


def _first_tag_value(meta_tags: list[dict], tag_name: str) -> str:
    for tag in meta_tags:
        name = str(tag.get("name") or "").strip().lower()
        prop = str(tag.get("property") or "").strip().lower()
        if name == tag_name or prop == tag_name:
            return str(tag.get("content") or "").strip()
    return ""


def _social_value(social: dict[str, Any], tag_name: str) -> str:
    value = social.get(tag_name)
    if isinstance(value, list):
        return str(value[0]).strip() if value else ""
    return str(value or "").strip()


def build_metadata_rows(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the fixed metadata table shown by the metadata checker UI."""
    page_metadata = page.get("page_metadata") or {}
    meta_tags = page_metadata.get("meta_tags") or []
    twitter = page_metadata.get("twitter") or {}

    values = {
        "title": page.get("title") or "",
        "description": page.get("meta_description") or "",
        "keywords": page_metadata.get("keywords") or _first_tag_value(meta_tags, "keywords"),
        "author": page_metadata.get("author") or _first_tag_value(meta_tags, "author"),
        "viewport": page_metadata.get("viewport") or _first_tag_value(meta_tags, "viewport"),
        "robots": page_metadata.get("robots_meta") or _first_tag_value(meta_tags, "robots"),
        "theme-color": page_metadata.get("theme_color") or _first_tag_value(meta_tags, "theme-color"),
        "twitter:card": _social_value(twitter, "twitter:card") or _first_tag_value(meta_tags, "twitter:card"),
        "twitter:title": _social_value(twitter, "twitter:title") or _first_tag_value(meta_tags, "twitter:title"),
        "twitter:description": _social_value(twitter, "twitter:description") or _first_tag_value(meta_tags, "twitter:description"),
        "twitter:image": _social_value(twitter, "twitter:image") or _first_tag_value(meta_tags, "twitter:image"),
    }

    return [
        {
            "tag": tag,
            "content": values[tag],
            "google_supported": SUPPORT_MATRIX[tag][0],
            "bing_supported": SUPPORT_MATRIX[tag][1],
        }
        for tag in SUPPORT_MATRIX
    ]