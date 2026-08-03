"""
Security Collector
==================
Collects security headers and SSL/TLS information.
"""

from typing import Dict, Any, List


class SecurityCollector:
    """Collects security-related information from responses."""
    
    @staticmethod
    def collect_ssl_info(page) -> Dict[str, Any]:
        """
        Collect SSL/TLS certificate information.
        
        Args:
            page: Playwright page object
            
        Returns:
            Dictionary containing SSL information
        """
        try:
            # Get security details from page
            security_details = page.evaluate("""
                () => {
                    return {
                        isSecure: window.isSecureContext,
                        protocol: location.protocol
                    };
                }
            """)
            
            # Try to get certificate information via response
            ssl_info = {
                "enabled": security_details.get('isSecureContext', False) and security_details.get('protocol') == 'https:',
                "certificate_issuer": "",
                "certificate_expiry": "",
                "tls_version": ""
            }
            
            return ssl_info
            
        except Exception:
            return {
                "enabled": False,
                "certificate_issuer": "",
                "certificate_expiry": "",
                "tls_version": ""
            }
    
    @staticmethod
    def collect_security_headers_from_response(response) -> Dict[str, str]:
        """
        Collect security headers from response.
        
        Args:
            response: Playwright response object
            
        Returns:
            Dictionary containing security headers
        """
        try:
            # In sync API, headers is a method; call it if callable
            headers_dict = response.headers() if callable(response.headers) else response.headers
            headers = dict(headers_dict)
            
            return {
                "strict_transport_security": headers.get("strict-transport-security", ""),
                "content_security_policy": headers.get("content-security-policy", ""),
                "x_frame_options": headers.get("x-frame-options", ""),
                "x_content_type_options": headers.get("x-content-type-options", ""),
                "referrer_policy": headers.get("referrer-policy", "")
            }
        except Exception:
            return {
                "strict_transport_security": "",
                "content_security_policy": "",
                "x_frame_options": "",
                "x_content_type_options": "",
                "referrer_policy": ""
            }
    
    @staticmethod
    def analyze_security_posture(security_headers: Dict[str, str], ssl_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze overall security posture (raw data only, no scoring).
        
        Args:
            security_headers: Security headers dictionary
            ssl_info: SSL information dictionary
            
        Returns:
            Dictionary with security posture information
        """
        return {
            "has_hsts": bool(security_headers.get("strict_transport_security")),
            "has_csp": bool(security_headers.get("content_security_policy")),
            "has_x_frame_options": bool(security_headers.get("x_frame_options")),
            "has_x_content_type_options": bool(security_headers.get("x_content_type_options")),
            "has_referrer_policy": bool(security_headers.get("referrer_policy")),
            "ssl_enabled": ssl_info.get("enabled", False),
            "security_headers_count": sum([
                bool(security_headers.get("strict_transport_security")),
                bool(security_headers.get("content_security_policy")),
                bool(security_headers.get("x_frame_options")),
                bool(security_headers.get("x_content_type_options")),
                bool(security_headers.get("referrer_policy"))
            ])
        }