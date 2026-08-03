"""
URL Validator
=============
URL validation and normalization utilities.
"""

import hashlib
from urllib.parse import urlparse


class URLValidator:
    """Validates and normalizes URLs."""

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Check if URL is valid."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc]) and result.scheme in ['http', 'https']
        except Exception:
            return False

    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize URL by adding https:// if missing."""
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url

    @staticmethod
    def get_domain(url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc.replace(':', '_')

    @staticmethod
    def get_url_hash(url: str) -> str:
        """Generate MD5 hash for URL."""
        return hashlib.md5(url.encode()).hexdigest()