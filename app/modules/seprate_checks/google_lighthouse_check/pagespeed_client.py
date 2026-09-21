"""
Pagespeed / Lighthouse API client.

Wraps Google PageSpeed Insights API (v5) which internally runs Lighthouse.
Endpoint: https://www.googleapis.com/pagespeedonline/v5/runPagespeed
"""
import httpx
from typing import Optional

from app.core.config import settings
from app.core.#loggger import #loggger


class PagespeedClient:
    """Thin async wrapper around the Google PageSpeed Insights API."""

    BASE_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GOOGLE_PAGESPEED_API_KEY

    async def fetch(
        self,
        url: str,
        strategy: str = "mobile",  # or "desktop"
        category: Optional[list[str]] = None,
    ) -> dict:
        """
        Call the Pagespeed API for a single URL.

        Args:
            url: The page URL to audit.
            strategy: 'mobile' or 'desktop'.
            category: Lighthouse categories (default: ['performance', 'seo', 'best-practices', 'accessibility']).

        Returns:
            Parsed JSON response from the API.

        Raises:
            httpx.HTTPStatusError on non-200.
            ValueError if API key is missing.
        """
        if not self.api_key:
            raise ValueError("GOOGLE_PAGESPEED_API_KEY is not configured")

        if category is None:
            category = ["performance", "seo", "best-practices", "accessibility"]

        params = {
            "url": url,
            "key": self.api_key,
            "strategy": strategy,
            "category": category,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(self.BASE_URL, params=params)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def parse_result(raw: dict, url: str, device: str) -> dict:
        """
        Extract Lighthouse metrics from the raw API response.

        Maps the nested API JSON structure to the flat fields
        defined in LighthousePageResult / LighthouseCheckResponse.
        """
        lighthouse = raw.get("lighthouseResult", {})
        categories = lighthouse.get("categories", {})
        audits = lighthouse.get("audits", {})

        # Category scores are 0.0–1.0 floats in the API; convert to 0–100 int
        def _score(cat_name: str) -> Optional[int]:
            score = categories.get(cat_name, {}).get("score")
            return int(score * 100) if score is not None else None

        def _audit_value(audit_id: str):
            audit = audits.get(audit_id, {})
            return audit.get("numericValue") or audit.get("displayValue")

        # FCP / LCP are in the 'load-render' / 'largest-contentful-paint' audits
        fcp_display = _audit_value("first-contentful-paint")
        lcp_display = _audit_value("largest-contentful-paint")
        tbt_display = _audit_value("total-blocking-time")
        cls_display = _audit_value("cumulative-layout-shift")

        def _to_ms(val) -> Optional[int]:
            """Pagespeed returns ms in numericValue but sometimes displayValue too."""
            if val is None:
                return None
            try:
                # numericValue is already in milliseconds (float)
                return int(float(val))
            except (ValueError, TypeError):
                return None

        return {
            "url": url,
            "device": device,
            "performance_score": _score("performance"),
            "seo_score": _score("seo"),
            "fcp_ms": _to_ms(fcp_display),
            "lcp_ms": _to_ms(lcp_display),
            "tbt_ms": _to_ms(tbt_display),
            "cls": float(cls_display) if cls_display is not None else None,
        }