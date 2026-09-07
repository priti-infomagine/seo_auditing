from .url_normalizer import normalize_rel
from .text_normalizer import normalize_text


def normalize_rel_attribute(rel: str | list | None) -> list[str]:
    return normalize_rel(rel)


def normalize_lang(lang: str | None) -> str:
    if not lang:
        return ""
    return str(lang).strip().lower()


def normalize_boolean_attribute(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def normalize_loading(loading: str | None) -> str:
    if not loading:
        return ""
    return str(loading).strip().lower()


def normalize_charset(charset: str | None) -> str:
    if not charset:
        return ""
    return str(charset).strip().lower()


def normalize_attributes(attrs: dict) -> dict[str, str]:
    return {str(k): str(v) for k, v in attrs.items()}


def normalize_link_data(href: str, text: str, rel: str | list | None, base_url: str = "") -> dict:
    from .url_normalizer import resolve_url
    return {
        "href": href.strip() if href else "",
        "text": normalize_text(text) if text else "",
        "rel": normalize_rel_attribute(rel),
        "absolute_url": resolve_url(base_url, href),
    }
