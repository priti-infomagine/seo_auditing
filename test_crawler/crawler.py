"""
Modular Web Crawler Module
==========================
A production-ready web crawler using Playwright and BeautifulSoup.
"""

import re
import json
import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page, Browser
from bs4 import BeautifulSoup


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


class WebCrawler:
    """Handles web page retrieval using Playwright."""

    def __init__(self, headless: bool = True, timeout: int = 30000):
        """
        Initialize crawler.

        Args:
            headless: Run browser in headless mode
            timeout: Page load timeout in milliseconds
        """
        self.headless = headless
        self.timeout = timeout
        self.browser: Optional[Browser] = None
        self.playwright = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch page content.

        Args:
            url: URL to fetch

        Returns:
            HTML content or None if failed
        """
        try:
            if not self.browser:
                raise RuntimeError("Browser not initialized. Use async context manager.")

            page = await self.browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )

            await page.set_extra_http_headers({
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })

            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
            await page.wait_for_load_state("networkidle", timeout=10000)

            content = await page.content()
            await page.close()

            return content

        except Exception as e:
            print(f"Error fetching {url}: {str(e)}")
            return None


class DataParser:
    """Parses HTML content using BeautifulSoup."""

    @staticmethod
    def parse(html: str) -> Dict[str, Any]:
        """
        Parse HTML and extract SEO-relevant data.

        Args:
            html: Raw HTML content

        Returns:
            Dictionary containing parsed data
        """
        soup = BeautifulSoup(html, 'html.parser')

        data = {
            # Basic
            "title": DataParser._get_title(soup),
            "title_length": DataParser._get_title_length(soup),

            "meta_description": DataParser._get_meta_description(soup),
            "meta_description_length": DataParser._get_meta_description_length(soup),

            "meta_keywords": DataParser._get_meta_keywords(soup),
            "author": DataParser._get_author(soup),
            "language": DataParser._get_language(soup),
            "charset": DataParser._get_charset(soup),
            "viewport": DataParser._get_viewport(soup),

            # SEO
            "canonical_url": DataParser._get_canonical(soup),
            "has_canonical": DataParser._has_canonical(soup),
            "robots_meta": DataParser._get_robots_meta(soup),

            # Headings
            "headings": DataParser._get_headings(soup),
            "heading_stats": DataParser._get_heading_stats(soup),

            # Content
            "word_count": DataParser._get_word_count(soup),
            "reading_time_minutes": DataParser._get_reading_time(soup),
            "paragraph_count": DataParser._get_paragraph_count(soup),
            "lists": DataParser._get_lists(soup),
            "table_count": DataParser._get_table_count(soup),
            "form_count": DataParser._get_form_count(soup),
            "button_count": DataParser._get_button_count(soup),
            "iframe_count": DataParser._get_iframe_count(soup),
            "video_count": DataParser._get_video_count(soup),

            # Media
            "images": DataParser._get_images(soup),
            "favicon": DataParser._get_favicon(soup),

            # Links
            "links": DataParser._get_links(soup),
            "hreflang": DataParser._get_hreflang(soup),

            # Social
            "open_graph": DataParser._get_open_graph(soup),
            "twitter_cards": DataParser._get_twitter_cards(soup),

            # Structured Data
            "schema_markup": DataParser._get_schema_markup(soup),

            # Quality Metrics
            "doctype": DataParser._get_doctype(html),
            "html_size": len(html),
            "text_html_ratio": DataParser._get_text_html_ratio(html, soup),
            "content_hash": DataParser._get_content_hash(soup),
        }

        return data
    
        # ==========================
    # TITLE
    # ==========================

    @staticmethod
    def _get_title_length(soup):
        title = DataParser._get_title(soup)
        return len(title) if title else 0


    # ==========================
    # META DESCRIPTION
    # ==========================

    @staticmethod
    def _get_meta_description_length(soup):
        desc = DataParser._get_meta_description(soup)
        return len(desc) if desc else 0


    # ==========================
    # CANONICAL
    # ==========================

    @staticmethod
    def _has_canonical(soup):
        return DataParser._get_canonical(soup) is not None


    # ==========================
    # HEADING STATS
    # ==========================

    @staticmethod
    def _get_heading_stats(soup):
        return {
            f"h{i}": len(soup.find_all(f"h{i}"))
            for i in range(1, 7)
        }


    # ==========================
    # READING TIME
    # ==========================

    @staticmethod
    def _get_reading_time(soup):
        words = DataParser._get_word_count(soup)
        return max(1, round(words / 200))


    # ==========================
    # PARAGRAPHS
    # ==========================

    @staticmethod
    def _get_paragraph_count(soup):
        return len(soup.find_all("p"))


    # ==========================
    # LISTS
    # ==========================

    @staticmethod
    def _get_lists(soup):
        return {
            "unordered": len(soup.find_all("ul")),
            "ordered": len(soup.find_all("ol"))
        }


    # ==========================
    # TABLES
    # ==========================

    @staticmethod
    def _get_table_count(soup):
        return len(soup.find_all("table"))


    # ==========================
    # FORMS
    # ==========================

    @staticmethod
    def _get_form_count(soup):
        return len(soup.find_all("form"))


    # ==========================
    # BUTTONS
    # ==========================

    @staticmethod
    def _get_button_count(soup):
        return len(soup.find_all("button"))


    # ==========================
    # IFRAMES
    # ==========================

    @staticmethod
    def _get_iframe_count(soup):
        return len(soup.find_all("iframe"))


    # ==========================
    # VIDEOS
    # ==========================

    @staticmethod
    def _get_video_count(soup):
        return (
            len(soup.find_all("video"))
            + len(
                soup.find_all(
                    "iframe",
                    src=re.compile(r"(youtube|youtu\.be|vimeo)", re.I)
                )
            )
        )


    # ==========================
    # FAVICON
    # ==========================

    @staticmethod
    def _get_favicon(soup):
        icon = soup.find("link", rel=lambda x: x and "icon" in x.lower())
        return icon.get("href") if icon else None


    # ==========================
    # HREFLANG
    # ==========================

    @staticmethod
    def _get_hreflang(soup):
        hreflangs = []

        for tag in soup.find_all("link", rel="alternate"):
            lang = tag.get("hreflang")
            href = tag.get("href")

            if lang and href:
                hreflangs.append({
                    "lang": lang,
                    "url": href
                })

        return hreflangs


    # ==========================
    # DOCTYPE
    # ==========================

    @staticmethod
    def _get_doctype(html):
        match = re.search(r'<!DOCTYPE\s+([^>]*)>', html, re.I)
        return match.group(1).strip() if match else None


    # ==========================
    # HTML SIZE
    # ==========================

    @staticmethod
    def _get_html_size(html):
        return len(html.encode("utf-8"))


    # ==========================
    # TEXT / HTML RATIO
    # ==========================

    @staticmethod
    def _get_text_html_ratio(html, soup):
        text = soup.get_text(" ", strip=True)

        if not html:
            return 0

        return round(len(text) / len(html), 3)


    # ==========================
    # CONTENT HASH
    # ==========================

    @staticmethod
    def _get_content_hash(soup):
        text = soup.get_text(" ", strip=True)
        return hashlib.sha256(text.encode()).hexdigest()
        
    @staticmethod
    def _get_author(soup):
        meta = soup.find("meta", attrs={"name": "author"})
        return meta.get("content") if meta else None
    @staticmethod
    def _get_charset(soup):
        meta = soup.find("meta", attrs={"charset": True})
        if meta:
            return meta.get("charset")

        meta = soup.find("meta", attrs={"http-equiv": "Content-Type"})
        if meta:
            return meta.get("content")
        return None
  
    @staticmethod
    def _get_viewport(soup):
        meta = soup.find("meta", attrs={"name": "viewport"})
        return meta.get("content") if meta else None

    @staticmethod
    def _get_title(soup: BeautifulSoup) -> Optional[str]:
        """Extract page title."""
        title_tag = soup.find('title')
        return title_tag.get_text(strip=True) if title_tag else None

    @staticmethod
    def _get_meta_description(soup: BeautifulSoup) -> Optional[str]:
        """Extract meta description."""
        meta = soup.find('meta', attrs={'name': 'description'})
        return meta.get('content', '').strip() if meta else None

    @staticmethod
    def _get_meta_keywords(soup: BeautifulSoup) -> List[str]:
        """Extract meta keywords."""
        meta = soup.find('meta', attrs={'name': 'keywords'})
        if not meta:
            return []
        keywords = meta.get('content', '')
        return [k.strip() for k in keywords.split(',') if k.strip()]

    @staticmethod
    def _get_headings(soup: BeautifulSoup) -> Dict[str, List[str]]:
        """Extract all headings (h1-h6)."""
        headings = {}
        for level in range(1, 7):
            tag = f'h{level}'
            elements = soup.find_all(tag)
            headings[tag] = [e.get_text(strip=True) for e in elements]
        return headings

    @staticmethod
    def _get_links(soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract all links."""
        links = soup.find_all('a', href=True)
        internal = []
        external = []

        for link in links:
            href = link['href'].strip()
            text = link.get_text(strip=True)
            if href and not href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                if href.startswith('http'):
                    external.append({"url": href, "text": text[:100]})
                else:
                    internal.append({"url": href, "text": text[:100]})

        return {
            "internal_count": len(internal),
            "external_count": len(external),
            "internal_links": internal[:20],  # Limit to 20
            "external_links": external[:20]
        }

    @staticmethod
    def _get_images(soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract image information."""
        images = soup.find_all('img')
        without_alt = sum(1 for img in images if not img.get('alt'))

        return {
            "total_count": len(images),
            "without_alt": without_alt,
            "sample": [
                {
                    "src": img.get('src', ''),
                    "alt": img.get('alt', '')[:100]
                }
                for img in images[:10]
            ]
        }

    @staticmethod
    def _get_word_count(soup: BeautifulSoup) -> int:
        """Estimate word count."""
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        text = soup.get_text()
        words = text.split()
        return len(words)

    @staticmethod
    def _get_language(soup: BeautifulSoup) -> Optional[str]:
        """Extract page language."""
        html_tag = soup.find('html')
        if html_tag and html_tag.get('lang'):
            return html_tag.get('lang')

        meta = soup.find('meta', attrs={'http-equiv': 'content-language'})
        if meta:
            return meta.get('content')

        return None

    @staticmethod
    def _get_canonical(soup: BeautifulSoup) -> Optional[str]:
        """Extract canonical URL."""
        link = soup.find('link', rel='canonical')
        return link.get('href') if link else None

    @staticmethod
    def _get_robots_meta(soup: BeautifulSoup) -> Optional[str]:
        """Extract robots meta tag."""
        meta = soup.find('meta', attrs={'name': 'robots'})
        return meta.get('content') if meta else None

    @staticmethod
    def _get_open_graph(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract Open Graph tags."""
        og_data = {}
        for tag in soup.find_all('meta', property=re.compile(r'^og:')):
            property_name = tag.get('property', '')
            content = tag.get('content', '')
            if property_name and content:
                og_data[property_name] = content
        return og_data

    @staticmethod
    def _get_twitter_cards(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract Twitter Card tags."""
        twitter_data = {}
        for tag in soup.find_all('meta', attrs={'name': re.compile(r'^twitter:')}):
            name = tag.get('name', '')
            content = tag.get('content', '')
            if name and content:
                twitter_data[name] = content
        return twitter_data

    @staticmethod
    def _get_schema_markup(soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract structured data (JSON-LD)."""
        schemas = []
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                schemas.append(data)
            except (json.JSONDecodeError, AttributeError):
                continue
        return schemas


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

    def save_crawl_data(self, url: str, crawl_data: Dict[str, Any]) -> Path:
        """
        Save crawl data to file.

        Args:
            url: Original URL
            crawl_data: Crawled data dictionary

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
        filename = f"{url_hash}_{timestamp}.json"
        filepath = domain_dir / filename

        # Prepare complete data structure
        complete_data = {
            "url": url,
            "crawled_at": datetime.now().isoformat(),
            "url_hash": url_hash,
            "domain": domain,
            "data": crawl_data
        }

        # Save to file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(complete_data, f, indent=2, ensure_ascii=False)

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
        pattern = f"{url_hash}_*.json"
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
        self.validator = URLValidator()
        self.crawler = WebCrawler(headless=headless)
        self.parser = DataParser()
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
        if not self.validator.is_valid_url(url):
            raise ValueError(f"Invalid URL: {url}")

        normalized_url = self.validator.normalize_url(url)
        print(f"Crawling: {normalized_url}")

        # Fetch page
        async with self.crawler as browser:
            html = await browser.fetch_page(normalized_url)

        if not html:
            raise RuntimeError(f"Failed to fetch content from {normalized_url}")

        # Parse data
        parsed_data = self.parser.parse(html)

        # Store data
        filepath = self.storage.save_crawl_data(normalized_url, parsed_data)

        # Return results
        result = {
            "url": normalized_url,
            "status": "success",
            "filepath": str(filepath),
            "data": parsed_data
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
        print(f"  Title: {result['data']['title']}")
        print(f"  Word Count: {result['data']['word_count']}")
        print(f"  Language: {result['data']['language']}")
        print(f"  Total Links: {result['data']['links']['internal_count'] + result['data']['links']['external_count']}")
        print(f"  Total Images: {result['data']['images']['total_count']}")
        print(f"  Images without alt: {result['data']['images']['without_alt']}")
        print(f"  H1 tags: {len(result['data']['headings']['h1'])}")
        print(f"  Open Graph tags: {len(result['data']['open_graph'])}")
        print("="*50)

    except ValueError as e:
        print(f"Validation Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()