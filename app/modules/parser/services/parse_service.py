"""
Parse Service
=============
Business logic for parsing crawled website data.

This service:
1. Takes a website/domain name
2. Matches it with the latest crawled .json file in app/storage/crawler/{domain}/
3. Parses the crawled data using the ParserService
4. Stores the parsed output in app/storage/parsed/{domain}/ with incremental test number
"""
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from app.core.logger import logger
from .parser_service import ParserService


class ParseService:
    """Service for parsing crawled website data and storing results."""

    def __init__(
        self,
        crawl_dir: str = "app/storage/crawler",
        parsed_dir: str = "app/storage/parsed",
    ):
        """
        Initialize parse service.

        Args:
            crawl_dir: Directory containing crawled data
            parsed_dir: Directory to store parsed data
        """
        self.crawl_dir = Path(crawl_dir)
        self.parsed_dir = Path(parsed_dir)
        self.parser = ParserService(crawl_dir=str(self.crawl_dir))

    def parse_website(self, website: str) -> Dict[str, Any]:
        """
        Parse the latest crawled data for a website and save the result.

        Args:
            website: Website/domain name (e.g., 'cyfuture.com')

        Returns:
            Dictionary with parse results and metadata

        Raises:
            ValueError: If no crawl data found for the website
            RuntimeError: If parsing fails
        """
        # Normalize domain
        domain = self._normalize_domain(website)

        # Find the latest crawl file for this domain (checks exact and www. variants)
        crawl_file = self._get_latest_crawl_file(domain)
        if not crawl_file:
            raise ValueError(
                f"No crawled data found for website '{domain}'. "
                f"Please crawl the website first."
            )

        # Use the actual directory name where the crawl data was stored
        # (e.g., 'www.wikipedia.org' if that's how the crawler saved it)
        actual_domain = crawl_file.parent.name

        logger.info(f"Found latest crawl file: {crawl_file}")

        # Load crawl data
        crawl_data = self._load_json(crawl_file)

        # Parse the HTML from crawl data
        html = crawl_data.get("html", "")
        url = crawl_data.get("final_url") or crawl_data.get("requested_url", "")

        if not html:
            raise RuntimeError(f"Crawl file {crawl_file.name} contains no HTML content")

        # Generate comprehensive SEO report using the actual stored domain
        report = self.parser.generate_report_by_domain(actual_domain)
        if not report:
            raise RuntimeError(f"Failed to generate report for domain: {domain}")

        # Fix URL in report (crawl data uses final_url/requested_url keys)
        if not report.get("url"):
            report["url"] = url

        # Add source metadata
        report["source_crawl_file"] = crawl_file.name
        report["parsed_at"] = datetime.now().isoformat()

        # Save parsed data using actual stored domain
        filepath, test_number = self._save_parsed_data(report, actual_domain)

        logger.info(f"Parsing completed successfully. Saved to: {filepath}")

        return {
            "success": True,
            "message": "Parsing completed successfully",
            "website": actual_domain,
            "test_number": test_number,
            "file_path": str(filepath),
            "parsed_at": report["parsed_at"],
            "source_crawl_file": crawl_file.name,
            "data": {
                "url": report.get("url"),
                "seo_score": report.get("seo_score", {}).get("overall_score"),
                "seo_grade": report.get("seo_score", {}).get("overall_grade"),
                "title": report.get("basic_info", {}).get("title"),
                "word_count": report.get("basic_info", {}).get("word_count"),
                "total_links": report.get("links", {}).get("total_links"),
                "total_images": report.get("images", {}).get("total_images"),
            },
        }

    def _normalize_domain(self, website: str) -> str:
        """
        Normalize website input to a clean domain name.

        Matches the crawler's domain extraction (keeps www. prefix),
        so that the crawl directory lookup works correctly.

        Args:
            website: Website name or URL

        Returns:
            Clean domain name
        """
        domain = website.strip().lower()

        # Remove protocol
        if domain.startswith(("http://", "https://")):
            from urllib.parse import urlparse
            domain = urlparse(domain).netloc or domain

        # Remove trailing slash and path
        domain = domain.rstrip("/")
        domain = domain.split("/")[0]

        return domain

    def _get_latest_crawl_file(self, domain: str) -> Optional[Path]:
        """
        Get the latest crawl file for a domain.

        Tries both the exact domain and the www.-prefixed variant,
        since the crawler may store data under either.

        Args:
            domain: Domain name

        Returns:
            Path to latest crawl file or None
        """
        # Try candidates: exact domain first, then www. variant
        candidates = [domain]
        if not domain.startswith("www."):
            candidates.append(f"www.{domain}")
        else:
            candidates.append(domain[4:])

        for candidate in candidates:
            domain_dir = self.crawl_dir / candidate

            if not domain_dir.exists():
                continue

            # Get all JSON files sorted by name (test number is in filename)
            files = sorted(domain_dir.glob("*.json"), reverse=True)

            if files:
                return files[0]

        return None

    def _load_json(self, filepath: Path) -> Dict[str, Any]:
        """Load JSON data from file."""
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def _get_next_test_number(self, domain: str) -> int:
        """
        Get the next test number for a domain in parsed storage.

        Args:
            domain: Domain name

        Returns:
            Next test number
        """
        domain_dir = self.parsed_dir / domain

        if not domain_dir.exists():
            return 1

        # Find all test files
        test_files = list(domain_dir.glob(f"{domain}_test_*.json"))

        if not test_files:
            return 1

        # Extract test numbers
        test_numbers = []
        for filepath in test_files:
            try:
                # Format: {domain}_test_{number}_{timestamp}.json
                stem = filepath.stem
                match = re.search(r"_test_(\d+)", stem)
                if match:
                    test_numbers.append(int(match.group(1)))
            except (IndexError, ValueError):
                continue

        return max(test_numbers, default=0) + 1

    def _save_parsed_data(self, report: Dict[str, Any], domain: str) -> Tuple[Path, int]:
        """
        Save parsed data to file with incremental test number.

        Args:
            report: Parsed report dictionary
            domain: Domain name

        Returns:
            Tuple of (Path to saved file, test number)
        """
        # Create domain directory in parsed storage
        domain_dir = self.parsed_dir / domain
        domain_dir.mkdir(parents=True, exist_ok=True)

        # Get next test number
        test_number = self._get_next_test_number(domain)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{domain}_test_{test_number}_{timestamp}.json"
        filepath = domain_dir / filename

        # Save to file
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        return filepath, test_number
