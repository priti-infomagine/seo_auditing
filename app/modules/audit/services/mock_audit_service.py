"""
Mock Audit Service
==================
Mock implementation of the combined crawler + parser pipeline.

This service simulates what would happen when running a full crawl
followed by parsing, without actually performing either operation.
Used as a placeholder/blueprint for the future real implementation.
"""
import hashlib
import random
from urllib.parse import urlparse
from typing import Dict, Any

from app.core.logger import logger


class MockAuditService:
    """Mock service for the combined crawl + parse audit pipeline."""

    def audit_website(self, url: str, deep_crawl: bool = False) -> Dict[str, Any]:
        """
        Simulate a full crawl + parse audit for a website.

        Args:
            url: URL to audit
            deep_crawl: Whether to simulate a deep crawl

        Returns:
            Dictionary with mock crawl and parse results
        """
        logger.info(f"[MOCK] Running audit for URL: {url} (deep_crawl={deep_crawl})")

        # Extract domain
        parsed = urlparse(url)
        domain = parsed.netloc or url.split("/")[0]

        # Generate deterministic values based on URL hash so same URL → same result
        seed = int(hashlib.md5(url.encode()).hexdigest(), 16)
        rng = random.Random(seed)

        # ── Mock Crawl Phase ──────────────────────────────────────────
        pages_crawled = 5 if not deep_crawl else 2
        html_size = rng.randint(40_000, 250_000)
        response_time = round(rng.uniform(0.5, 4.5), 2)

        crawl_result = {
            "status_code": 200,
            "html_size_bytes": html_size,
            "response_time_ms": response_time * 1000,
            "pages_crawled": pages_crawled,
        }

        # ── Mock Parse Phase ──────────────────────────────────────────
        # Generate plausible parse results
        seo_score = rng.randint(55, 95)
        seo_grade = self._get_grade(seo_score)

        parse_result = {
            "title": f"{domain} - {self._pick(rng, ['Home', 'Official Website', 'Products', 'Services', 'Contact'])}",
            "meta_description": f"Explore {domain} - comprehensive information about products, services, and solutions offered by {domain}.",
            "word_count": rng.randint(150, 1200),
            "total_links": rng.randint(10, 80),
            "total_images": rng.randint(5, 40),
            "seo_score": seo_score,
            "seo_grade": seo_grade,
        }

        logger.info(f"[MOCK] Audit complete for {url}. SEO Score: {seo_score} ({seo_grade})")

        return {
            "success": True,
            "message": "Mock audit completed successfully (crawl + parse pipeline)",
            "url": url,
            "domain": domain,
            "crawl": crawl_result,
            "parse": parse_result,
            "mock": True,
        }

    def _pick(self, rng: random.Random, options: list) -> str:
        """Pick a random element deterministically."""
        return options[rng.randint(0, len(options) - 1)]

    def _get_grade(self, score: int) -> str:
        """Convert score to letter grade (mirrors real parser service)."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"