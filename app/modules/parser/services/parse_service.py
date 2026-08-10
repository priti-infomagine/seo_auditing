import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from app.core.logger import logger

from .parser_service import ParserService


class ParseService:
    """
    Pipeline / storage adapter for the parser module.

    Responsibilities:
    - locate latest crawl result on disk
    - load crawl result JSON
    - pass crawl result to ParserService
    - attach source crawl metadata
    - persist parsed output

    ParserService knows nothing about filesystem paths.
    """

    def __init__(
        self,
        crawl_dir: str = "app/storage/crawler",
        parsed_dir: str = "app/storage/parsed",
    ):
        self.crawl_dir = Path(crawl_dir)
        self.parsed_dir = Path(parsed_dir)
        self.parser = ParserService()

    def parse_website(self, website: str) -> Dict[str, Any]:
        domain = self._normalize_domain(website)

        crawl_file = self._get_latest_crawl_file(domain)
        if not crawl_file:
            raise ValueError(
                f"No crawled data found for website '{domain}'. "
                f"Please crawl the website first."
            )

        actual_domain = crawl_file.parent.name
        logger.info("Parsing crawl file: %s", crawl_file)

        crawl_data = self._load_json(crawl_file)
        html = crawl_data.get("html", "")

        if not html:
            raise RuntimeError(
                f"Crawl file {crawl_file.name} contains no HTML content"
            )

        url = (
            crawl_data.get("final_url")
            or crawl_data.get("requested_url")
            or website
        )

        parsed_document = self.parser.parse(html=html, url=url)

        parsed_output = parsed_document.model_dump(mode="json")

        parsed_output["crawl_context"] = {
            "requested_url": crawl_data.get("requested_url"),
            "final_url": crawl_data.get("final_url"),
            "status_code": crawl_data.get("status_code"),
            "content_type": crawl_data.get("content_type"),
            "response_time_ms": crawl_data.get("response_time_ms"),
            "source_crawl_file": crawl_file.name,
        }

        parsed_output["parsed_at"] = datetime.now().isoformat()

        filepath, test_number = self._save_parsed_data(parsed_output, actual_domain)

        logger.info("Parsing completed: %s", filepath)

        return {
            "success": True,
            "message": "Parsing completed successfully",
            "website": actual_domain,
            "test_number": test_number,
            "file_path": str(filepath),
            "parsed_at": parsed_output["parsed_at"],
            "source_crawl_file": crawl_file.name,
            "data": {
                "url": parsed_output["document"].get("url"),
                "title": parsed_output["metadata"].get("title"),
                "word_count": parsed_output["content"].get("word_count"),
                "total_links": len(parsed_output.get("links", [])),
                "total_resources": len(parsed_output.get("resources", [])),
                "structured_data_items": len(
                    parsed_output.get("structured_data", [])
                ),
            },
        }

    def _normalize_domain(self, website: str) -> str:
        value = website.strip().lower()

        if not value:
            raise ValueError("Website cannot be empty")

        if not value.startswith(("http://", "https://")):
            value = f"https://{value}"

        parsed = urlparse(value)
        if not parsed.netloc:
            raise ValueError(f"Invalid website: {website}")

        return parsed.netloc.rstrip("/")

    def _get_latest_crawl_file(self, domain: str) -> Optional[Path]:
        candidates = [domain]
        if domain.startswith("www."):
            candidates.append(domain[4:])
        else:
            candidates.append(f"www.{domain}")

        for candidate in candidates:
            domain_dir = self.crawl_dir / candidate
            if not domain_dir.exists():
                continue
            files = list(domain_dir.glob("*.json"))
            if not files:
                continue
            return max(files, key=lambda path: path.stat().st_mtime)

        return None

    @staticmethod
    def _load_json(filepath: Path) -> Dict[str, Any]:
        with filepath.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _get_next_test_number(self, domain: str) -> int:
        domain_dir = self.parsed_dir / domain
        if not domain_dir.exists():
            return 1

        test_numbers = []
        for filepath in domain_dir.glob(f"{domain}_test_*.json"):
            match = re.search(r"_test_(\d+)", filepath.stem)
            if match:
                test_numbers.append(int(match.group(1)))

        return max(test_numbers, default=0) + 1

    def _save_parsed_data(
        self, data: Dict[str, Any], domain: str
    ) -> Tuple[Path, int]:
        domain_dir = self.parsed_dir / domain
        domain_dir.mkdir(parents=True, exist_ok=True)

        test_number = self._get_next_test_number(domain)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = domain_dir / f"{domain}_test_{test_number}_{timestamp}.json"

        with filepath.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)

        return filepath, test_number
