from __future__ import annotations

from urllib.parse import urlparse

from app.shared.utils.url_utils import is_same_site


def analyze_links(links: list, base_url: str = "") -> dict:
    internal_count = 0
    external_count = 0
    base_domain = urlparse(base_url).netloc if base_url else ""

    for link in links:
        target = link.absolute_url or link.href or ""
        if not target:
            continue
        target_domain = urlparse(target).netloc
        if target_domain and base_domain and is_same_site(target_domain, base_domain):
            internal_count += 1
        else:
            external_count += 1

    total = internal_count + external_count
    return {
        "total_links": total,
        "internal_count": internal_count,
        "external_count": external_count,
        "internal_ratio": round(internal_count / total, 3) if total > 0 else 0.0,
        "external_ratio": round(external_count / total, 3) if total > 0 else 0.0,
    }
