"""
Async DNS cache for SSRF validation.

Replaces the synchronous ``socket.getaddrinfo()`` call in
``validate_url_ssrf`` with a native-async ``aiodns`` resolver backed by
an in-memory TTL cache.  This eliminates the biggest source of event-loop
blocking during crawling — every URL fetch and every broken-link check
no longer freezes all concurrent workers for 50ms–2s on a blocking DNS
lookup.

Key design decisions:
  - TTL cache (default 60 s) so repeated lookups for the same hostname
    are served from memory in microseconds.
  - Negative results (DNS failure) are cached briefly (10 s) to avoid
    hammering a non-existent domain.
  - The resolver is created lazily and reused (aiodns manages its own
    socket pool).
  - No external configuration required — works out of the box.
"""
import asyncio
import socket
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from app.core.logger import logger

if TYPE_CHECKING:
    import aiodns

try:
    import aiodns  # noqa: F811 — runtime import (TYPE_CHECKING above is for stubs)
    AIO_DNS_AVAILABLE = True
except ImportError:  # pragma: no cover
    AIO_DNS_AVAILABLE = False

# hostname -> ([ip_addresses], expiry_monotonic_time)
_dns_cache: Dict[str, Tuple[List[str], float]] = {}

# Default cache TTL in seconds — matches typical DNS TTL for static hosts.
_DEFAULT_TTL = 60.0
# Short TTL for negative (failed) lookups to retry sooner.
_NEGATIVE_TTL = 10.0

_resolver: Optional[Any] = None


def _get_resolver() -> Any:
    """Return the aiodns resolver for the active event loop, creating it lazily."""
    global _resolver
    loop = asyncio.get_running_loop()
    if _resolver is None or getattr(_resolver, "_loop", None) != loop:
        _resolver = aiodns.DNSResolver(
            timeout=2.0,
            tries=1,
            # lifetime=5.0,
            loop=loop,
        )
    return _resolver



async def resolve_host(hostname: str, ttl: float = _DEFAULT_TTL) -> List[str]:
    """
    Resolve *hostname* to a list of IP address strings using aiodns.

    Results are cached for *ttl* seconds.  Failed lookups are cached for
    ``_NEGATIVE_TTL`` seconds with an empty list so the caller can skip
    the DNS stage and let the HTTP fetch handle the network error.

    Returns:
        A list of IP strings (may be empty if resolution failed).
    """
    now = time.monotonic()
    cached = _dns_cache.get(hostname)
    if cached and cached[1] > now:
        return cached[0]

    if not AIO_DNS_AVAILABLE:
        # Fallback: run blocking getaddrinfo in a thread so we never
        # block the event loop even without aiodns installed.
        loop = asyncio.get_running_loop()
        try:
            addr_info = await loop.run_in_executor(
                None, socket.getaddrinfo, hostname, None
            )
            ip_list = [sockaddr[0] for _, _, _, _, sockaddr in addr_info]
        except socket.gaierror:
            ip_list = []
        _dns_cache[hostname] = (ip_list, now + _NEGATIVE_TTL)
        return ip_list

    resolver = _get_resolver()
    try:
        # Try IPv4 first
        result = await resolver.gethostbyname(hostname, socket.AF_INET)
        ip_list = list(getattr(result, "addresses", []) or [])
    except Exception:
        # Try IPv6 fallback
        try:
            result6 = await resolver.gethostbyname(hostname, socket.AF_INET6)
            ip_list = list(getattr(result6, "addresses", []) or [])
        except Exception as exc:
            logger.debug("DNS resolution failed for %s: %s", hostname, exc)
            ip_list = []
            # Cache the negative result briefly
            _dns_cache[hostname] = (ip_list, now + _NEGATIVE_TTL)
            return ip_list

    _dns_cache[hostname] = (ip_list, now + ttl)
    return ip_list


def clear_dns_cache() -> None:
    """Clear the DNS cache (useful for tests or cache invalidation)."""
    _dns_cache.clear()
