"""
HTTP Data Collector
===================
Collects HTTP response data and headers.
"""

from typing import Dict, Any, List


class HTTPCollector:
    """Collects HTTP response data from Playwright responses."""
    
    @staticmethod
    def collect_from_response(response) -> Dict[str, Any]:
        """
        Extract HTTP data from Playwright response object.
        
        Args:
            response: Playwright response object
            
        Returns:
            Dictionary containing HTTP response data
        """
        try:
            # In sync API, headers is a method; call it if callable
            headers_dict = response.headers() if callable(response.headers) else response.headers
            headers = dict(headers_dict)
            
            # http_version is a method in sync API; call it if callable
            http_version = response.http_version() if callable(response.http_version) else response.http_version
            
            return {
                "status_code": response.status,
                "http_version": http_version if http_version else "",
                "content_type": headers.get("content-type", ""),
                "content_length": headers.get("content-length", ""),
                "content_encoding": headers.get("content-encoding", ""),
                "server": headers.get("server", ""),
                "cache_control": headers.get("cache-control", ""),
                "etag": headers.get("etag", ""),
                "last_modified": headers.get("last-modified", ""),
                "vary": headers.get("vary", ""),
            }
        except Exception as e:
            return {
                "status_code": 0,
                "http_version": "",
                "content_type": "",
                "content_length": "",
                "content_encoding": "",
                "server": "",
                "cache_control": "",
                "etag": "",
                "last_modified": "",
                "vary": ""
            }
    
    @staticmethod
    def collect_security_headers(headers: Dict[str, str]) -> Dict[str, str]:
        """
        Extract security-related headers.
        
        Args:
            headers: Dictionary of response headers
            
        Returns:
            Dictionary of security headers
        """
        return {    
            "strict_transport_security": headers.get("strict-transport-security", ""),
            "content_security_policy": headers.get("content-security-policy", ""),
            "x_frame_options": headers.get("x-frame-options", ""),
            "x_content_type_options": headers.get("x-content-type-options", ""),
            "referrer_policy": headers.get("referrer-policy", "")
        }