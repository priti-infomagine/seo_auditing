from app.modules.parser.normalizers.url_normalizer import (
    resolve_url,
    is_internal,
    normalize_rel,
)
from app.modules.parser.normalizers.text_normalizer import normalize_text


def normalize_link(href: str, text: str, rel, base_url: str = "") -> dict:
    return {
        "href": href.strip() if href else "",
        "text": normalize_text(text) if text else "",
        "rel": normalize_rel(rel),
        "absolute_url": resolve_url(base_url, href),
    }


def normalize_link_list(links: list[dict], base_url: str = "") -> list[dict]:
    return [normalize_link(l.get("href", ""), l.get("text", ""), l.get("rel"), base_url) for l in links]
