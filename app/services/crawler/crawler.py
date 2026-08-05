"""
Web Crawler
===========
Main crawler implementation using Playwright sync API.
The entire browser lifecycle (start → crawl → close) runs in a single thread
to avoid greenlet thread-switching errors on Windows.
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, Page, Browser

from .response import CrawlerResponse
from .validator import URLValidator
from .http_collector import HTTPCollector
from .performance import PerformanceCollector
from .resources import ResourceTracker
from .security import SecurityCollector
from .robots import RobotsCollector


class WebCrawler:
    """Handles web page retrieval using Playwright sync API."""
    
    def __init__(self, headless: bool = True, timeout: int = 30000):
        """
        Initialize crawler.
        
        Args:
            headless: Run browser in headless mode
            timeout: Page load timeout in milliseconds
        """
        self.headless = headless
        self.timeout = timeout
    
    async def crawl(self, url: str) -> CrawlerResponse:
        """
        Crawl a URL and return structured response.
        
        The entire browser lifecycle runs in a single thread to avoid
        greenlet thread-switching errors.
        
        Args:
            url: URL to crawl
            
        Returns:
            CrawlerResponse object containing all collected data
            
        Raises:
            RuntimeError: If crawl fails
        """
        # Run the entire crawl lifecycle in a single thread
        return await asyncio.to_thread(self._crawl_sync, url)
    
    def _crawl_sync(self, url: str) -> CrawlerResponse:
        """
        Synchronous crawl implementation (runs entirely in one thread).
        
        Args:
            url: URL to crawl
            
        Returns:
            CrawlerResponse object containing all collected data
        """
        playwright = None
        browser = None
        
        try:
            # Start Playwright and browser in this thread
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=self.headless)
            
            # Initialize collectors
            resource_tracker = ResourceTracker()
            redirect_chain = []
            
            # Track start time
            start_time = datetime.now()
            requested_url = url
            normalized_url = URLValidator.normalize_url(url)
            domain = URLValidator.get_domain(normalized_url)
            
            # Create page
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            
            page.set_extra_http_headers({
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
            
            # Track resources
            def handle_response(response):
                try:
                    # Track redirects
                    if response.status in [301, 302, 303, 307, 308]:
                        redirect_chain.append({
                            "from": response.request.url,
                            "to": response.url,
                            "status_code": response.status
                        })
                    
                    # Track resources
                    resource_type = ResourceTracker.categorize_url(response.url)
                    resource_tracker.track_resource(
                        url=response.url,
                        resource_type=resource_type
                    )
                except Exception:
                    pass
            
            # Track console messages
            console_errors = []
            console_warnings = []
            
            def handle_console(msg):
                try:
                    if msg.type == 'error':
                        console_errors.append({
                            "text": msg.text,
                            "timestamp": datetime.now().isoformat()
                        })
                    elif msg.type == 'warning':
                        console_warnings.append({
                            "text": msg.text,
                            "timestamp": datetime.now().isoformat()
                        })
                except Exception:
                    pass
            
            # Track failed requests
            failed_requests = []
            
            def handle_request_failure(request):
                try:
                    failure = request.failure() if callable(request.failure) else request.failure
                    failed_requests.append({
                        "url": request.url,
                        "failure": failure if failure else "unknown"
                    })
                except Exception:
                    pass
            
            page.on('response', handle_response)
            page.on('console', handle_console)
            page.on('requestfailed', handle_request_failure)
            
            # Initialize response data
            http_data = {
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
            security_headers = {}
            
            try:
                # Navigate to page
                response = page.goto(normalized_url, wait_until="domcontentloaded", timeout=self.timeout)
                
                if response:
                    http_data = HTTPCollector.collect_from_response(response)
                    security_headers = SecurityCollector.collect_security_headers_from_response(response)
                
                # Wait for network idle
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                
                # Collect performance metrics
                performance_metrics = PerformanceCollector.collect_from_page(page)
                
                # Collect SSL info
                ssl_info = SecurityCollector.collect_ssl_info(page)
                
                # Collect robots and sitemap
                robots_collector = RobotsCollector(normalized_url)
                robots_sitemap_data = robots_collector.collect_all(page)
                
                # Get final URL and HTML
                final_url = page.url
                html = page.content()
                
                # Calculate response time
                end_time = datetime.now()
                response_time = (end_time - start_time).total_seconds()
                
                # Build HTTP data with timing
                http_data["response_time"] = response_time
                
                # Build robots/sitemap data
                robots_data = robots_sitemap_data.get("robots", {})
                sitemap_data = robots_sitemap_data.get("sitemap", {})
                
                # Create CrawlerResponse
                crawler_response = CrawlerResponse(
                    requested_url=requested_url,
                    final_url=final_url,
                    domain=domain,
                    html=html,
                    crawled_at=datetime.now().isoformat(),
                    
                    # HTTP data
                    http=http_data,
                    redirects=redirect_chain,
                    
                    # Performance
                    performance=performance_metrics,
                    
                    # Resources
                    resources=resource_tracker.get_resources(),
                    
                    # JavaScript
                    javascript={
                        "console_errors": console_errors,
                        "console_warnings": console_warnings,
                        "failed_requests": failed_requests
                    },
                    
                    # Security
                    security_headers=security_headers,
                    ssl=ssl_info,
                    
                    # Robots and sitemap
                    robots=robots_data,
                    sitemap=sitemap_data,
                    
                    # Cookies (empty for now, can be enhanced)
                    cookies=[]
                )
                
                return crawler_response
                
            except Exception as e:
                raise RuntimeError(f"Failed to crawl {normalized_url}: {str(e)}")
            
            finally:
                page.close()
        
        finally:
            # Close browser and stop Playwright in the SAME thread
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright:
                try:
                    playwright.stop()
                except Exception:
                    pass
    
    async def crawl_multiple(self, urls: List[str]) -> List[CrawlerResponse]:
        """
        Crawl multiple URLs.
        
        Args:
            urls: List of URLs to crawl
            
        Returns:
            List of CrawlerResponse objects
        """
        results = []
        
        for url in urls:
            try:
                result = await self.crawl(url)
                results.append(result)
            except Exception as e:
                # Log error and continue with next URL
                print(f"Error crawling {url}: {str(e)}")
                continue
        
        return results