from urllib.parse import urlparse

from app.shared.utils.url_utils import normalize_host


def normalize_target_url(raw_url: str) -> tuple[str, str]:
    """Return a canonical crawl URL and normalized site domain."""
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise ValueError("url must be a non-empty string")

    cleaned = raw_url.strip()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"

    parsed = urlparse(cleaned)
    host = normalize_host(parsed.netloc or parsed.path)
    if not host:
        raise ValueError(f"Invalid URL: {raw_url}")

    scheme = parsed.scheme.lower() if parsed.scheme in {"http", "https"} else "https"
    canonical = f"{scheme}://{parsed.netloc or host}{parsed.path or '/'}"
    if parsed.query:
        canonical = f"{canonical}?{parsed.query}"
    return canonical, host