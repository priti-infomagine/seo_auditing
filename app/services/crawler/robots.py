"""
Robots and Sitemap Collector
=============================
Collects robots.txt and sitemap.xml data.
"""

from typing import Dict, Any, List
from urllib.parse import urljoin


class RobotsCollector:
    """Collects robots.txt and sitemap information."""
    
    def __init__(self, base_url: str):
        """
        Initialize collector.
        
        Args:
            base_url: Base URL of the website
        """
        self.base_url = base_url.rstrip('/')
    
    def collect_robots(self, page) -> Dict[str, Any]:
        """
        Collect robots.txt data.
        
        Args:
            page: Playwright page object
            
        Returns:
            Dictionary containing robots.txt information
        """
        robots_url = urljoin(self.base_url, '/robots.txt')
        
        try:
            response = page.request.get(robots_url)
            content = response.text() if response.status == 200 else ""
            
            # Extract sitemap URLs from robots.txt
            sitemap_urls = []
            if content:
                for line in content.split('\n'):
                    line = line.strip().lower()
                    if line.startswith('sitemap:'):
                        sitemap_url = line.split(':', 1)[1].strip()
                        sitemap_urls.append(sitemap_url)
            
            return {
                "exists": response.status == 200,
                "content": content,
                "sitemap_urls": sitemap_urls
            }
            
        except Exception:
            return {
                "exists": False,
                "content": "",
                "sitemap_urls": []
            }
    
    def collect_sitemap(self, page, sitemap_urls: List[str] = None) -> Dict[str, Any]:
        """
        Collect sitemap.xml data.
        
        Args:
            page: Playwright page object
            sitemap_urls: List of sitemap URLs to check (from robots.txt)
            
        Returns:
            Dictionary containing sitemap information
        """
        if not sitemap_urls:
            sitemap_urls = [urljoin(self.base_url, '/sitemap.xml')]
        
        all_urls = []
        sitemap_exists = False
        
        for sitemap_url in sitemap_urls:
            try:
                response = page.request.get(sitemap_url)
                
                if response.status == 200:
                    sitemap_exists = True
                    content = response.text()
                    
                    # Simple URL extraction (basic XML parsing)
                    # For production, use proper XML parser
                    import re
                    urls = re.findall(r'<loc>(.*?)</loc>', content)
                    all_urls.extend(urls)
                    
            except Exception:
                continue
        
        return {
            "exists": sitemap_exists,
            "urls": all_urls[:100]  # Limit to 100 URLs
        }
    
    def collect_all(self, page) -> Dict[str, Any]:
        """
        Collect both robots.txt and sitemap data.
        
        Args:
            page: Playwright page object
            
        Returns:
            Dictionary containing robots and sitemap information
        """
        robots_data = self.collect_robots(page)
        sitemap_data = self.collect_sitemap(page, robots_data.get('sitemap_urls', []))
        
        return {
            "robots": robots_data,
            "sitemap": sitemap_data
        }