"""Technical Parser - Extracts technical SEO and HTTP information."""
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup


class TechnicalParser:
    """Extracts technical SEO information."""
    
    @staticmethod
    def parse_http_headers(headers: Dict[str, str]) -> Dict[str, Any]:
        """
        Parse HTTP headers.
        
        Args:
            headers: Dictionary of HTTP headers
            
        Returns:
            Parsed header information
        """
        if not headers:
            return {}
        
        return {
            "content_type": headers.get("content-type", ""),
            "content_encoding": headers.get("content-encoding", ""),
            "cache_control": headers.get("cache-control", ""),
            "etag": headers.get("etag", ""),
            "last_modified": headers.get("last-modified", ""),
            "server": headers.get("server", ""),
            "x_robots_tag": headers.get("X-Robots-Tag", ""),
            "gzip_enabled": "gzip" in headers.get("content-encoding", "").lower(),
            "brotli_enabled": "br" in headers.get("content-encoding", "").lower()
        }
    
    @staticmethod
    def get_viewport(soup: BeautifulSoup) -> str:
        """
        Extract viewport meta tag.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Viewport content
        """
        viewport_meta = soup.find('meta', attrs={'name': 'viewport'})
        return viewport_meta.get('content', '').strip() if viewport_meta else ""
    
    @staticmethod
    def get_charset(soup: BeautifulSoup) -> str:
        """
        Extract charset information.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Character encoding
        """
        # Check for charset meta tag
        charset_meta = soup.find('meta', attrs={'charset': True})
        if charset_meta:
            return charset_meta.get('charset', '').strip()
        
        # Check for content-type meta tag
        content_type_meta = soup.find('meta', attrs={'http-equiv': 'Content-Type'})
        if content_type_meta:
            content = content_type_meta.get('content', '')
            if 'charset=' in content:
                return content.split('charset=')[-1].strip()
        
        return ""
    
    @staticmethod
    def get_doctype(html: str) -> str:
        """
        Extract DOCTYPE declaration.
        
        Args:
            html: Raw HTML string
            
        Returns:
            DOCTYPE declaration
        """
        if not html:
            return ""
        
        html_stripped = html.strip().upper()
        if html_stripped.startswith('<!DOCTYPE'):
            doctype_end = html.find('>', 10)
            if doctype_end != -1:
                return html[10:doctype_end].strip()
        
        return ""
    
    @staticmethod
    def check_mobile_friendly(soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Check mobile-friendliness indicators.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Mobile-friendliness analysis
        """
        viewport = TechnicalParser.get_viewport(soup)
        
        checks = {
            "has_viewport": bool(viewport),
            "viewport_content": viewport,
            "is_mobile_friendly": bool(viewport)
        }
        
        # Check for viewport width=device-width
        if viewport:
            if 'width=device-width' in viewport:
                checks["uses_device_width"] = True
            else:
                checks["uses_device_width"] = False
                checks["issues"] = ["Viewport missing width=device-width"]
        
        return checks
    
    @staticmethod
    def get_robots_meta(soup: BeautifulSoup) -> str:
        """
        Extract robots meta directive.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Robots meta content
        """
        robots_tag = soup.find('meta', attrs={'name': 'robots'})
        return robots_tag.get('content', '').strip() if robots_tag else ""
    
    @staticmethod
    def get_html_language(soup: BeautifulSoup) -> str:
        """
        Extract HTML language attribute.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Language code
        """
        html_tag = soup.find('html')
        if html_tag:
            return html_tag.get('lang', '').strip()
        return ""
    
    @staticmethod
    def analyze_performance_indicators(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
        """
        Analyze performance-related indicators.
        
        Args:
            soup: BeautifulSoup object
            html: Raw HTML string
            
        Returns:
            Performance analysis
        """
        indicators = {
            "html_size_bytes": len(html.encode('utf-8')) if html else 0,
            "script_count": len(soup.find_all('script')),
            "style_count": len(soup.find_all('style')),
            "link_count": len(soup.find_all('link')),
            "has_inline_styles": bool(soup.find_all(style=True)),
            "has_external_css": bool(soup.find_all('link', rel='stylesheet'))
        }
        
        # Estimate render-blocking resources
        render_blocking = []
        
        # Check for CSS in head
        head = soup.find('head')
        if head:
            styles = head.find_all('link', rel='stylesheet')
            render_blocking.extend([s.get('href', '') for s in styles])
        
        indicators["render_blocking_resources"] = render_blocking
        indicators["render_blocking_count"] = len(render_blocking)
        
        return indicators