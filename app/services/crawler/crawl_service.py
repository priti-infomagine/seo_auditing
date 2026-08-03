"""
Crawler Service
===============
Business logic for web crawling operations.
"""
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from .crawler import WebCrawler
from .response import CrawlerResponse
from app.core.logger import logger


class CrawlerService:
    """Service for managing web crawling operations."""
    
    def __init__(self, storage_dir: str = "app/storage/crawler"):
        """
        Initialize crawler service.
        
        Args:
            storage_dir: Directory to store crawled data
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    async def crawl_url(self, url: str) -> Dict[str, Any]:
        """
        Crawl a URL and save the data.
        
        Args:
            url: URL to crawl
            
        Returns:
            Dictionary with crawl results and metadata
            
        Raises:
            ValueError: If URL is invalid
            RuntimeError: If crawling fails
        """
        # Validate URL
        from .validator import URLValidator
        normalized_url = URLValidator.normalize_url(url)
        domain = URLValidator.get_domain(normalized_url)
        
        if not domain:
            raise ValueError(f"Invalid URL: {url}")
        
        logger.info(f"Starting crawl for URL: {normalized_url}")
        
        # Perform crawl
        crawler = WebCrawler()
        response: CrawlerResponse = await crawler.crawl(normalized_url)
        
        # Save crawl data
        filepath = self._save_crawl_data(response, domain)
        
        # Get test number
        test_number = self._get_next_test_number(domain)
        
        logger.info(f"Crawl completed successfully. Saved to: {filepath}")
        
        return {
            "success": True,
            "message": "Crawl completed successfully",
            "url": normalized_url,
            "domain": domain,
            "test_number": test_number,
            "file_path": str(filepath),
            "crawled_at": response.crawled_at,
            "data": {
                "status_code": response.http.get("status_code"),
                "response_time": response.http.get("response_time"),
                "html_size": len(response.html),
                "title": response.html[:100] if response.html else "",  # Preview
            }
        }
    
    def _save_crawl_data(self, response: CrawlerResponse, domain: str) -> Path:
        """
        Save crawl data to file with incremental test number.
        
        Args:
            response: CrawlerResponse object
            domain: Domain name
            
        Returns:
            Path to saved file
        """
        # Create domain directory
        domain_dir = self.storage_dir / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate URL hash
        url_hash = hashlib.md5(response.final_url.encode()).hexdigest()
        
        # Get next test number
        test_number = self._get_next_test_number(domain)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{domain}_test_{test_number}.json"
        filepath = domain_dir / filename
        
        # Convert response to dict and save
        response_dict = response.to_dict()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(response_dict, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def _get_next_test_number(self, domain: str) -> int:
        """
        Get the next test number for a domain.
        
        Args:
            domain: Domain name
            
        Returns:
            Next test number
        """
        domain_dir = self.storage_dir / domain
        
        if not domain_dir.exists():
            return 1
        
        # Find all test files
        test_files = list(domain_dir.glob("*_test_*.json"))
        
        if not test_files:
            return 1
        
        # Extract test numbers
        test_numbers = []
        for filepath in test_files:
            try:
                # Extract test number from filename
                # Format: {hash}_{timestamp}_test_{number}.json
                stem = filepath.stem
                test_part = stem.split('_test_')[-1]
                test_num = int(test_part.split('_')[0])
                test_numbers.append(test_num)
            except (IndexError, ValueError):
                continue
        
        return max(test_numbers, default=0) + 1
    
    def get_crawl_by_domain(self, domain: str, test_number: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Get crawl data by domain and optional test number.
        
        Args:
            domain: Domain name
            test_number: Specific test number (latest if None)
            
        Returns:
            Crawl data dictionary or None
        """
        domain_dir = self.storage_dir / domain
        
        if not domain_dir.exists():
            return None
        
        if test_number:
            # Find specific test file
            pattern = f"*_test_{test_number}.json"
            files = sorted(domain_dir.glob(pattern))
            if files:
                with open(files[0], 'r', encoding='utf-8') as f:
                    return json.load(f)
        else:
            # Get latest file
            files = sorted(domain_dir.glob("*.json"), reverse=True)
            if files:
                with open(files[0], 'r', encoding='utf-8') as f:
                    return json.load(f)
        
        return None
    
    def list_crawled_domains(self) -> List[str]:
        """
        List all crawled domains.
        
        Returns:
            List of domain names
        """
        if not self.storage_dir.exists():
            return []
        
        return [d.name for d in self.storage_dir.iterdir() if d.is_dir()]
    
    def list_tests_for_domain(self, domain: str) -> List[Dict[str, Any]]:
        """
        List all test files for a domain.
        
        Args:
            domain: Domain name
            
        Returns:
            List of test file metadata
        """
        domain_dir = self.storage_dir / domain
        
        if not domain_dir.exists():
            return []
        
        tests = []
        for filepath in sorted(domain_dir.glob("*.json")):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Extract test number from filename
                stem = filepath.stem
                test_part = stem.split('_test_')[-1]
                test_number = int(test_part.split('_')[0])
                
                tests.append({
                    "test_number": test_number,
                    "filename": filepath.name,
                    "path": str(filepath),
                    "crawled_at": data.get("crawled_at"),
                    "url": data.get("final_url") or data.get("requested_url")
                })
            except Exception:
                continue
        
        return sorted(tests, key=lambda x: x['test_number'])