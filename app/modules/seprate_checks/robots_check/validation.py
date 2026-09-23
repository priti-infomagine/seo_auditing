"""
Robots check input validation.

Centralizes domain validation so it is shared between the Pydantic schema
(parse-time) and the service layer (runtime / test-time validation without
an HTTP request).
"""
from app.shared.utils.url_utils import normalize_host

from .model import FetchStatus


class RobotsCheckValidationError(ValueError):
    """Raised when a robots check input fails validation."""


def validate_domain(domain: str) -> str:
    """Validate and normalize a bare domain string.

    Accepts forms like ``example.com``, ``www.example.com``,
    ``https://example.com/path``, ``Example.COM:8080``.
    Returns the lowercase registered domain
    (``normalize_host`` strips ``www.`` and the port).

    Raises:
        RobotsCheckValidationError: if *domain* is empty or invalid.
    """
    if not isinstance(domain, str) or not domain.strip():
        raise RobotsCheckValidationError("domain must be a non-empty string")

    cleaned = domain.strip().lower()

    # If the input contains a scheme (e.g. "https://example.com/path"),
    # extract just the host portion before normalize_host.
    # normalize_host only handles bare hostnames/netlocs, not full URLs —
    # passing "https://example.com" would incorrectly return "https".
    if "://" in cleaned:
        cleaned = cleaned.split("://", 1)[1]
    # Strip any path, query, or fragment that may follow the host
    cleaned = cleaned.split("/", 1)[0]

    host = normalize_host(cleaned)
    if not host:
        raise RobotsCheckValidationError(f"Invalid domain: {domain!r}")
    return host


def build_robots_url(domain: str, scheme: str = "https") -> str:
    """Build the canonical robots.txt URL for *domain*."""
    return f"{scheme}://{domain}/robots.txt"


FETCHSTATUSES = FetchStatus
