"""
Redirect extractor - extracts redirect chain from HTTP response.
Returns structured redirect data only, no persistence logic.
"""
from typing import List, Optional


class ExtractedRedirect:
    """Structured redirect data."""
    def __init__(
        self,
        url: str,
        status_code: int,
    ):
        self.url = url
        self.status_code = status_code


def extract_redirect_chain(response) -> List[ExtractedRedirect]:
    """
    Extract redirect chain from HTTP response.
    
    Args:
        response: httpx.Response object
        
    Returns:
        List of ExtractedRedirect objects
    """
    redirects = []
    
    # httpx follows redirects by default, so we need to check history
    if hasattr(response, 'history'):
        for hist_response in response.history:
            redirects.append(ExtractedRedirect(
                url=str(hist_response.url),
                status_code=hist_response.status_code,
            ))
    
    # Add final response
    redirects.append(ExtractedRedirect(
        url=str(response.url),
        status_code=response.status_code,
    ))
    
    return redirects