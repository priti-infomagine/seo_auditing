"""
Crawler Response Model
=====================
Structured response object for crawler data.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List


@dataclass
class CrawlerResponse:
    """
    Structured response from web crawler containing all collected data.
    
    Attributes:
        requested_url: Original URL requested
        final_url: Final URL after redirects
        domain: Extracted domain name
        html: Raw HTML content
        crawled_at: ISO timestamp of crawl
        
        http: HTTP response data (status, headers, etc.)
        redirects: Complete redirect chain
        
        performance: Browser performance metrics
        resources: Tracked resources (JS, CSS, images, etc.)
        javascript: JavaScript console logs and errors
        
        security_headers: Security-related HTTP headers
        ssl: SSL/TLS certificate information
        
        robots: robots.txt data
        sitemap: sitemap.xml data
        
        cookies: Captured cookies
    """
    
    # Core data
    requested_url: str
    final_url: str
    domain: str
    html: str
    crawled_at: str
    
    # HTTP response data
    http: Dict[str, Any] = field(default_factory=dict)
    redirects: List[Dict[str, Any]] = field(default_factory=list)
    
    # Performance metrics
    performance: Dict[str, Any] = field(default_factory=dict)
    
    # Resource tracking
    resources: Dict[str, List[Dict[str, Any]]] = field(default_factory=lambda: {
        "javascript": [],
        "css": [],
        "images": [],
        "fonts": [],
        "documents": [],
        "other": []
    })
    
    # JavaScript monitoring
    javascript: Dict[str, List] = field(default_factory=lambda: {
        "console_errors": [],
        "console_warnings": [],
        "failed_requests": []
    })
    
    # Security headers
    security_headers: Dict[str, str] = field(default_factory=dict)
    
    # SSL information
    ssl: Dict[str, Any] = field(default_factory=dict)
    
    # Robots and sitemap
    robots: Dict[str, Any] = field(default_factory=dict)
    sitemap: Dict[str, Any] = field(default_factory=dict)
    
    # Cookies
    cookies: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary for serialization."""
        return {
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "domain": self.domain,
            "html": self.html,
            "crawled_at": self.crawled_at,
            "http": self.http,
            "redirects": self.redirects,
            "performance": self.performance,
            "resources": self.resources,
            "javascript": self.javascript,
            "security_headers": self.security_headers,
            "ssl": self.ssl,
            "robots": self.robots,
            "sitemap": self.sitemap,
            "cookies": self.cookies
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CrawlerResponse':
        """Create CrawlerResponse from dictionary."""
        return cls(
            requested_url=data["requested_url"],
            final_url=data["final_url"],
            domain=data["domain"],
            html=data["html"],
            crawled_at=data["crawled_at"],
            http=data.get("http", {}),
            redirects=data.get("redirects", []),
            performance=data.get("performance", {}),
            resources=data.get("resources", {
                "javascript": [], "css": [], "images": [],
                "fonts": [], "documents": [], "other": []
            }),
            javascript=data.get("javascript", {
                "console_errors": [], "console_warnings": [], "failed_requests": []
            }),
            security_headers=data.get("security_headers", {}),
            ssl=data.get("ssl", {}),
            robots=data.get("robots", {}),
            sitemap=data.get("sitemap", {}),
            cookies=data.get("cookies", [])
        )