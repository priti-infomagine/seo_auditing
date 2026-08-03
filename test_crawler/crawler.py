"""
Crawler Service
===============
Main service orchestrating crawler and parser components.
"""

import asyncio
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from crawler import WebCrawler, CrawlerResponse, URLValidator
from parser import CrawlDataParser


class DataStorage:
    """Handles data storage and file management."""

    def __init__(self, base_dir: str = "crawl_data"):
        """
        Initialize storage.

        Args:
            base_dir: Base directory for storing crawl data
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)

    def save_crawl_data(self, url: str, crawler_response: CrawlerResponse) -> Path:
        """
        Save crawl data to file.

        Args:
            url: Original URL
            crawler_response: CrawlerResponse object from crawler

        Returns:
            Path to saved file
        """
        domain = URLValidator.get_domain(url)
        url_hash = URLValidator.get_url_hash(url)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create domain-specific directory
        domain_dir = self.base_dir / domain
        domain_dir.mkdir(exist_ok=True)

        # Create filename with URL hash and timestamp
        filename = f"{domain}_crawl_{timestamp}.json"
        filepath = domain_dir / filename

        # Convert CrawlerResponse to dictionary
        crawl_data = crawler_response.to_dict()

        # Prepare complete data structure
        complete_data = {
            "url": url,
            "crawled_at": datetime.now().isoformat(),
            "url_hash": url_hash,
            "domain": domain,
            "data": crawl_data
        }

        # Save to file with custom encoder to handle non-serializable objects
        class CustomJSONEncoder(json.JSONEncoder):
            def default(self, obj):
                # Skip method objects and other non-serializable types
                if callable(obj) and not isinstance(obj, (str, int, float, bool, list, dict)):
                    return None
                # Let the base class handle other types
                return super().default(obj)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(complete_data, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)

        return filepath

    def get_latest_crawl(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent crawl data for a URL.

        Args:
            url: URL to search for

        Returns:
            Latest crawl data or None
        """
        domain = URLValidator.get_domain(url)
        url_hash = URLValidator.get_url_hash(url)
        domain_dir = self.base_dir / domain

        if not domain_dir.exists():
            return None

        # Find files matching URL hash
        pattern = f"{domain}_*.json"
        files = sorted(domain_dir.glob(pattern), reverse=True)

        if not files:
            return None

        with open(files[0], 'r', encoding='utf-8') as f:
            return json.load(f)


class CrawlerService:
    """Main crawler service orchestrating all components."""

    def __init__(self, headless: bool = True):
        """
        Initialize crawler service.

        Args:
            headless: Run browser in headless mode
        """
        self.crawler = WebCrawler(headless=headless)
        self.parser = CrawlDataParser()
        self.storage = DataStorage()

    async def crawl(self, url: str) -> Dict[str, Any]:
        """
        Crawl a URL and store results.

        Args:
            url: URL to crawl

        Returns:
            Crawl results dictionary

        Raises:
            ValueError: If URL is invalid
            RuntimeError: If crawl fails
        """
        # Validate URL
        if not URLValidator.is_valid_url(url):
            raise ValueError(f"Invalid URL: {url}")

        normalized_url = URLValidator.normalize_url(url)
        print(f"Crawling: {normalized_url}")

        # Crawl URL (returns CrawlerResponse)
        async with self.crawler as browser:
            crawler_response = await browser.crawl(normalized_url)

        # Store crawler_response
        filepath = self.storage.save_crawl_data(normalized_url, crawler_response)
        
        # Note: CrawlDataParser is designed to analyze stored crawl data files
        # The actual HTML parsing will be done when user runs parser.py on the stored data
        # For now, we'll create a minimal parsed structure from crawler_response
        parsed_data = {
            "url": normalized_url,
            "domain": crawler_response.domain,
            "crawled_at": crawler_response.crawled_at,
            "note": "Raw crawl data stored. Run parser.py to analyze SEO."
        }

        # Return results
        result = {
            "url": normalized_url,
            "status": "success",
            "filepath": str(filepath),
            "data": parsed_data,
            "crawler_response": crawler_response.to_dict()
        }

        print(f"Crawl completed. Data saved to: {filepath}")
        return result

    def crawl_sync(self, url: str) -> Dict[str, Any]:
        """
        Synchronous wrapper for crawl method.

        Args:
            url: URL to crawl

        Returns:
            Crawl results dictionary
        """
        return asyncio.run(self.crawl(url))


def main():
    """Main entry point for CLI usage."""
    import sys

    print("="*50)
    print("WEB CRAWLER")
    print("="*50)
    
    # Check if URL provided as argument
    if len(sys.argv) >= 2:
        url = sys.argv[1]
    else:
        # Interactive mode
        url = input("\nEnter URL to crawl: ").strip()
        
        if not url:
            print("Error: No URL provided")
            sys.exit(1)

    try:
        service = CrawlerService(headless=True)
        result = service.crawl_sync(url)

        print("\n" + "="*50)
        print("CRAWL RESULTS")
        print("="*50)
        print(f"URL: {result['url']}")
        print(f"Status: {result['status']}")
        print(f"Saved to: {result['filepath']}")
        print("\nPage Info:")
        print(f"  Domain: {result['data']['domain']}")
        print(f"  Crawled at: {result['data']['crawled_at']}")
        print(f"  Note: {result['data']['note']}")
        print("\nTo analyze SEO data, run: python parser.py")
        print("="*50)

    except ValueError as e:
        print(f"Validation Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()