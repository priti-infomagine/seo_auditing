"""
URL utility functions for normalization and validation.
"""
from typing import Optional
from urllib.parse import urlparse


def normalize_url(url: str) -> str:
    """
    Normalize a URL by removing fragments and standardizing format.
    
    Args:
        url: The URL to normalize
        
    Returns:
        Normalized URL string
    """
    parsed = urlparse(url)
    # Remove fragment
    normalized = parsed._replace(fragment="").geturl()
    return normalized


def is_valid_url(url: str) -> bool:
    """
    Check if a URL is valid.
    
    Args:
        url: The URL to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def get_domain(url: str) -> Optional[str]:
    """
    Extract domain from URL.
    
    Args:
        url: The URL to extract domain from
        
    Returns:
        Domain string or None if invalid
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return None


def is_internal_link(base_url: str, target_url: str) -> bool:
    """
    Check if target_url is internal to base_url.
    
    Args:
        base_url: The base URL
        target_url: The target URL to check
        
    Returns:
        True if internal, False otherwise
    """
    base_domain = get_domain(base_url)
    target_domain = get_domain(target_url)
    return base_domain == target_domain