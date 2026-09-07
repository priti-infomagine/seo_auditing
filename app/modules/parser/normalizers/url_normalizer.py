from urllib.parse import urljoin, urlparse

from app.shared.utils.url_utils import normalize_url


def resolve_url(base_url: str, href: str) -> str:
    if not href:
        return ""
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("#"):
        return ""
    if href.startswith(("mailto:", "tel:", "javascript:")):
        return ""
    return urljoin(base_url, href)


def is_internal(base_url: str, target_url: str) -> bool:
    base_domain = urlparse(base_url).netloc
    target_domain = urlparse(target_url).netloc
    return base_domain == target_domain


def normalize_rel(rel: str | list | None) -> list[str]:
    if rel is None:
        return []
    if isinstance(rel, str):
        rel = rel.split()
    return [str(value).strip().lower() for value in rel if str(value).strip()]
