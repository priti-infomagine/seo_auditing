"""
URL Normalization and SSRF Protection Utilities.
"""
import ipaddress
import socket
from typing import List, Optional, Set
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.modules.crawler.exceptions import InvalidURLError, SSRFError

DEFAULT_TRACKING_PARAMS: Set[str] = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "msclkid",
    "mc_eid",
    "ref",
}

BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_ip_private(ip_str: str) -> bool:
    """Check if an IP address belongs to a private/loopback/reserved network."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in network for network in BLOCKED_IP_NETWORKS)
    except ValueError:
        return False


def validate_url_ssrf(url: str, allow_private: bool = False) -> None:
    """
    Validate that the target host does not resolve to a private or loopback IP range (SSRF Protection).
    """
    if allow_private:
        return

    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise InvalidURLError(f"URL hostname is missing: {url}", url=url)

    # Check if host is direct IP literal
    if is_ip_private(hostname):
        raise SSRFError(f"SSRF Protection: Direct IP {hostname} is forbidden", url=url)

    if hostname.lower() in ("localhost", "localhost.localdomain", "127.0.0.1"):
        raise SSRFError(f"SSRF Protection: Hostname {hostname} is forbidden", url=url)

    # Attempt DNS resolution
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            if is_ip_private(ip_str):
                raise SSRFError(
                    f"SSRF Protection: Hostname {hostname} resolved to forbidden IP {ip_str}",
                    url=url,
                )
    except socket.gaierror:
        # DNS resolution error handled during fetch stage
        pass


def normalize_url_canonical(
    url: str,
    strip_params: Optional[Set[str]] = None,
    trailing_slash_policy: str = "preserve",
) -> str:
    """
    Canonical URL Normalization:
    - Normalizes scheme (http/https) to lowercase
    - Normalizes host to lowercase
    - Removes default ports (:80, :443)
    - Strips URL fragments (#...)
    - Sorts query parameters deterministically
    - Removes tracking parameters (utm_*, gclid, etc.)
    - Removes trailing slash if path == ""
    """
    if not url:
        raise InvalidURLError("URL string is empty", url=url)

    url_str = url.strip()
    if not url_str.lower().startswith(("http://", "https://")):
        if "://" in url_str:
            scheme = url_str.split("://", 1)[0]
            raise InvalidURLError(f"Unsupported scheme: {scheme}", url=url)
        if ":" in url_str.split("/", 1)[0]:
            scheme = url_str.split(":", 1)[0]
            raise InvalidURLError(f"Unsupported scheme: {scheme}", url=url)
        url_str = "https://" + url_str

    parsed = urlparse(url_str)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port

    if not host:
        raise InvalidURLError(f"Could not extract valid hostname from {url}", url=url)

    # Reconstruct netloc without default ports
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443) or port is None:
        netloc = host
    else:
        netloc = f"{host}:{port}"

    path = parsed.path or "/"
    if path != "/" and path.endswith("/") and trailing_slash_policy == "remove":
        path = path.rstrip("/")

    # Query string normalization & tracking param removal
    params_to_strip = strip_params if strip_params is not None else DEFAULT_TRACKING_PARAMS
    query_tuples = parse_qsl(parsed.query, keep_blank_values=True)
    filtered_tuples = [
        (k, v) for k, v in query_tuples if k.lower() not in params_to_strip
    ]

    filtered_tuples.sort(key=lambda item: (item[0], item[1]))
    clean_query = urlencode(filtered_tuples) if filtered_tuples else ""

    return urlunparse((scheme, netloc, path, parsed.params, clean_query, ""))
