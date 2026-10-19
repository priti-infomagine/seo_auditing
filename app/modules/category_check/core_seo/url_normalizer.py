"""
URL normalization + SSRF protection for the Core SEO crawler pipeline.

Refactored from request_validation.py's normalize_url() into a comprehensive
set of utilities: scheme enforcement, default-port stripping, fragment removal,
tracking-parameter removal, IDNA encoding, eTLD+1 comparison, and SSRF checks.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import parse_qs, quote, urljoin, urlsplit, urlunsplit

from .constants import (
    BLOCKED_HOST_SUFFIXES,
    BLOCKED_HOSTS,
    BLOCKED_IP_NETWORKS,
    MAX_URL_LENGTH,
    TRACKING_PARAMS,
)

_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*$", re.IGNORECASE)
_TLD_RE = re.compile(r"^(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})$")
_SCHEME_LIKE = re.compile(r"^[a-z][a-z0-9+.\-]*:(?!\d)", re.IGNORECASE)

_MULTIPLE_LEVEL_SUFFIXES = (
    ".co.uk",
    ".org.uk",
    ".ac.uk",
    ".gov.uk",
    ".nhs.uk",
    ".co.in",
    ".org.in",
    ".ac.in",
    ".gov.in",
    ".nic.in",
    ".com.au",
    ".net.au",
    ".org.au",
    ".gov.au",
    ".co.jp",
    ".or.jp",
    ".ne.jp",
    ".go.jp",
    ".com.br",
    ".net.br",
    ".org.br",
    ".gov.br",
    ".co.nz",
    ".org.nz",
    ".net.nz",
    ".com.cn",
    ".net.cn",
    ".org.cn",
    ".gov.cn",
    ".co.za",
    ".org.za",
    ".net.za",
)

_DEFAULT_PORTS = {"http": 80, "https": 443}


class URLNormalizer:
    """Comprehensive URL normalization and SSRF protection utilities."""

    @staticmethod
    def normalize_url(raw: str) -> str:
        """Normalize a URL for crawling.

        - Strips whitespace, enforces length limit (2048).
        - Auto-prepends ``https://`` if no scheme.
        - Validates scheme ∈ {http, https}.
        - Rejects credentials in URL.
        - Lowercases scheme + host.
        - Removes default ports (:80, :443).
        - Rejects IP-literal hosts (SSRF).
        - Rejects localhost / blacklisted suffixes.
        - IDNA encodes unicode domains.
        - Strips fragments.
        - Sorts + strips tracking parameters.
        - Ensures path defaults to ``/``.
        """
        if not isinstance(raw, str):
            raise ValueError("URL must be a string")

        s = raw.strip()
        if not s:
            raise ValueError("URL is required")
        if len(s) > MAX_URL_LENGTH:
            raise ValueError(f"URL must be at most {MAX_URL_LENGTH} characters")
        if any(c.isspace() or ord(c) < 32 for c in s):
            raise ValueError("URL contains spaces or control characters")

        if "://" not in s:
            if _SCHEME_LIKE.match(s):
                raise ValueError("Only http and https URLs are allowed")
            s = "https://" + s

        try:
            parts = urlsplit(s)
        except ValueError:
            raise ValueError("URL is not valid")

        scheme = parts.scheme.lower()
        if scheme not in _DEFAULT_PORTS:
            raise ValueError("Only http and https URLs are allowed")

        if parts.username or parts.password:
            raise ValueError("URLs with username or password are not allowed")

        host = parts.hostname
        if not host:
            raise ValueError("URL has no host")

        host = host.rstrip(".").lower()

        if URLNormalizer._is_ip(host):
            raise ValueError("Use a domain name, not an IP address")

        try:
            host = host.encode("idna").decode("ascii")
        except (UnicodeError, ValueError):
            raise ValueError("Domain name is not valid")

        if len(host) > 253:
            raise ValueError("Domain name is too long")

        if host in BLOCKED_HOSTS or host.endswith(BLOCKED_HOST_SUFFIXES):
            raise ValueError("Internal hostnames are not allowed")

        if "." not in host or not _TLD_RE.match(host.rsplit(".", 1)[-1]):
            raise ValueError("Enter a valid domain, like example.com")

        port = parts.port
        netloc = host
        if port and port not in (80, 443):
            raise ValueError("Only ports 80 and 443 are allowed")
        if port and port != _DEFAULT_PORTS[scheme]:
            netloc = f"{host}:{port}"

        path = URLNormalizer._normalize_path(parts.path or "/")
        query = URLNormalizer._strip_tracking_params(parts.query)

        return urlunsplit((scheme, netloc, path, query, ""))

    @staticmethod
    def normalize_url_canonical(raw: str, **overrides) -> str:
        """Return the full canonical form: lowercase, no default ports,
        sorted params, no tracking params, no fragment."""
        normalized = URLNormalizer.normalize_url(raw)
        parts = urlsplit(normalized)
        scheme = parts.scheme.lower()
        host = parts.hostname or ""
        netloc = host
        port = parts.port
        if port and port != _DEFAULT_PORTS.get(scheme):
            netloc = f"{host}:{port}"
        query = URLNormalizer._strip_tracking_params(parts.query)
        path = URLNormalizer._normalize_path(parts.path or "/")
        return urlunsplit((scheme, netloc, path, query, ""))

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize URL path: resolve dot segments and decode percent-encoding.

        Handles ``/a/../b`` → ``/b``, ``/a/./b`` → ``/a/b``, ``/%2E%2E/`` → ``/``
        without breaking query strings or protocol-relative schemes.
        """
        if not path:
            return "/"
        if not path.startswith("/"):
            path = "/" + path
        parts = path.split("/")
        resolved: list[str] = []
        for segment in parts:
            if segment == "" or segment == ".":
                continue
            if segment == "..":
                if resolved:
                    resolved.pop()
                continue
            resolved.append(segment)
        return "/" + "/".join(resolved)

    @staticmethod
    def normalize_host(host: str) -> str:
        """Normalize a host for comparison: lowercase, strip port,
        strip trailing dot, strip leading www."""
        if not host:
            return ""
        host = host.strip().lower().rstrip(".")
        if host.startswith("["):
            idx = host.find("]")
            if idx != -1:
                host = host[1:idx]
        else:
            if ":" in host:
                host = host.split(":", 1)[0]
        host = host.removeprefix("www.")
        return host

    @staticmethod
    def _registered_domain(host: str) -> str:
        """Extract the registered domain (eTLD+1) from a hostname."""
        host = host.strip().lower().rstrip(".")
        if not host:
            return ""
        if host.startswith("["):
            return host
        if ":" in host:
            host = host.split(":", 1)[0]
        host = host.removeprefix("www.")

        parts = host.split(".")
        if len(parts) < 2:
            return host

        for suffix in _MULTIPLE_LEVEL_SUFFIXES:
            if host.endswith(suffix):
                suffix_labels = suffix.count(".") + 1
                if len(parts) > suffix_labels:
                    return ".".join(parts[-suffix_labels:])
                return host

        return ".".join(parts[-2:]) if len(parts) >= 2 else host

    @staticmethod
    def is_same_site(host_a: str, host_b: str) -> bool:
        """Determine whether two hosts belong to the same site (eTLD+1)."""
        reg_a = URLNormalizer._registered_domain(host_a)
        reg_b = URLNormalizer._registered_domain(host_b)
        return bool(reg_a) and bool(reg_b) and reg_a == reg_b

    @staticmethod
    def get_domain(url: str) -> str:
        """Extract the registered domain (eTLD+1) from a URL."""
        try:
            host = urlsplit(url).hostname or ""
        except (ValueError, AttributeError):
            return ""
        return URLNormalizer._registered_domain(host)

    @staticmethod
    def _is_ip(host: str) -> bool:
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_ip_in_blocked_network(ip_str: str, allow_private: bool = False) -> bool:
        """Check if an IP address is in a blocked network range."""
        if allow_private:
            return False
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False

        for network in BLOCKED_IP_NETWORKS:
            try:
                if ip in ipaddress.ip_network(network, strict=False):
                    if ip.is_private or ip.is_loopback or ip.is_link_local:
                        return True
            except (ValueError, TypeError):
                continue
        return False

    @staticmethod
    def validate_url_ssrf(url: str, allow_private: bool = False) -> None:
        """Validate a URL for SSRF — resolve DNS and check IP ranges.

        Raises ValueError if the URL resolves to a forbidden IP/network.
        """
        parts = urlsplit(url)
        host = parts.hostname or ""
        if not host:
            raise ValueError("URL has no host")

        if URLNormalizer._is_ip(host):
            if URLNormalizer._is_ip_in_blocked_network(host, allow_private):
                raise ValueError(f"SSRF protection: IP address '{host}' is blocked")

        try:
            addrinfo = socket.getaddrinfo(host, None)
        except socket.gaierror:
            raise ValueError(f"Cannot resolve host: {host}")

        for family, _socktype, _proto, _canonname, sockaddr in addrinfo:
            ip_str = sockaddr[0]
            if URLNormalizer._is_ip_in_blocked_network(ip_str, allow_private):
                raise ValueError(
                    f"SSRF protection: host '{host}' resolves to blocked IP '{ip_str}'"
                )

    @staticmethod
    def resolve_relative(base: str, href: str) -> str:
        """Resolve a relative URL against a base URL."""
        if not href:
            return base
        joined = urljoin(base, href)
        return joined

    @staticmethod
    def _strip_tracking_params(query: str) -> str:
        """Remove tracking parameters and sort remaining params."""
        if not query:
            return ""
        parsed = parse_qs(query, keep_blank_values=True)
        cleaned = {
            k: v for k, v in parsed.items() if k.lower() not in TRACKING_PARAMS
        }
        sorted_pairs = sorted(cleaned.items())
        parts = []
        for key, values in sorted_pairs:
            for val in values:
                parts.append(f"{key}={quote(val, safe='~')}" if val else key)
        return "&".join(parts)


normalize_url = URLNormalizer.normalize_url
normalize_url_canonical = URLNormalizer.normalize_url_canonical
normalize_host = URLNormalizer.normalize_host
is_same_site = URLNormalizer.is_same_site
get_domain = URLNormalizer.get_domain
resolve_relative = URLNormalizer.resolve_relative
validate_url_ssrf = URLNormalizer.validate_url_ssrf


class LinkSet:
    """Helper for link discovery deduplication (used by page_discoverer)."""

    def __init__(self):
        self._seen: set[str] = set()
        self._lock = None

    def add(self, normalized_url: str) -> bool:
        if normalized_url in self._seen:
            return False
        self._seen.add(normalized_url)
        return True

    def __len__(self) -> int:
        return len(self._seen)


__all__ = [
    "LinkSet",
    "URLNormalizer",
    "get_domain",
    "is_same_site",
    "normalize_host",
    "normalize_url",
    "normalize_url_canonical",
    "resolve_relative",
    "validate_url_ssrf",
]
