"""
Pagespeed / Lighthouse API client.

Wraps Google PageSpeed Insights API (v5) which internally runs Lighthouse.
Endpoint: https://www.googleapis.com/pagespeedonline/v5/runPagespeed
"""
import httpx
from typing import Optional

from app.core.config import settings
from app.core.logger import logger


_CATEGORY_LABELS = {
    "performance": "Performance",
    "accessibility": "Accessibility",
    "best-practices": "Best Practices",
    "seo": "SEO",
}


class PagespeedClient:
    """Thin async wrapper around the Google PageSpeed Insights API."""

    BASE_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GOOGLE_PAGESPEED_API_KEY
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily create a shared, connection-pooled httpx client.

        Reuses a single client across all fetch() calls to avoid
        socket exhaustion (WinError 10055) from creating a new client
        per request. Connection limits prevent unbounded socket growth.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=120.0,
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    max_connections=10,
                    keepalive_expiry=60,
                ),
            )
            logger.debug("PagespeedClient: created pooled httpx.AsyncClient")
        return self._client

    async def close(self) -> None:
        """Close the underlying pooled client. Call after the pagespeed batch."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("PagespeedClient: closed pooled client")
            self._client = None

    async def __aenter__(self) -> "PagespeedClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

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

        client = self._get_client()
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

        def _location(audit: dict) -> str:
            """Extract the most useful page/code location from audit details."""
            details = audit.get("details") or {}
            locations: list[str] = []
            for item in details.get("items", [])[:5]:
                if not isinstance(item, dict):
                    continue
                for key in ("url", "source", "selector", "nodeLabel", "snippet"):
                    value = item.get(key)
                    if value and str(value) not in locations:
                        locations.append(str(value))
            if locations:
                return "; ".join(locations)
            return "Review the page and assets referenced by this Lighthouse audit."

        def _evidence(audit: dict) -> list[dict]:
            """Keep actionable evidence from Lighthouse detail items."""
            details = audit.get("details") or {}
            evidence: list[dict] = []
            for item in details.get("items", [])[:10]:
                if not isinstance(item, dict):
                    continue
                selected = {
                    key: str(item[key])
                    for key in ("url", "source", "selector", "nodeLabel", "snippet")
                    if item.get(key) is not None
                }
                if selected:
                    evidence.append(selected)
            return evidence

        def _recommendations() -> list[dict]:
            """Keep actionable Lighthouse audits in a stable API shape."""
            items: list[dict] = []
            category_by_audit: dict[str, str] = {}
            weight_by_audit: dict[str, float] = {}
            for category_id, category in categories.items():
                for audit_ref in category.get("auditRefs", []):
                    if isinstance(audit_ref, dict) and audit_ref.get("id"):
                        category_by_audit.setdefault(audit_ref["id"], category_id)
                        weight = audit_ref.get("weight")
                        if isinstance(weight, (int, float)):
                            weight_by_audit.setdefault(audit_ref["id"], float(weight))

            for audit_id, audit in audits.items():
                if not isinstance(audit, dict):
                    continue
                score_mode = audit.get("scoreDisplayMode")
                score = audit.get("score")
                details = audit.get("details") or {}
                is_actionable = (
                    score_mode in {"binary", "numeric", "metricSavings", "error"}
                    and (score is None or score < 0.9)
                ) or details.get("type") in {"opportunity", "diagnostic"}
                if not is_actionable:
                    continue

                category_id = category_by_audit.get(audit_id, "performance")
                category_label = _CATEGORY_LABELS.get(category_id, category_id.title())
                score_percent = int(score * 100) if isinstance(score, (int, float)) else None
                savings_ms = details.get("overallSavingsMs")
                savings_bytes = details.get("overallSavingsBytes")
                items.append({
                    "audit_id": audit_id,
                    "category": category_label,
                    "category_weight": weight_by_audit.get(audit_id),
                    "title": audit.get("title") or audit_id.replace("-", " ").title(),
                    "score": score_percent,
                    "score_display_mode": score_mode,
                    "display_value": audit.get("displayValue"),
                    "numeric_value": audit.get("numericValue"),
                    "numeric_unit": audit.get("numericUnit"),
                    "description": audit.get("description"),
                    "explanation": audit.get("explanation"),
                    "details_type": details.get("type"),
                    "estimated_savings_ms": (
                        int(savings_ms) if isinstance(savings_ms, (int, float)) else None
                    ),
                    "estimated_savings_bytes": (
                        int(savings_bytes)
                        if isinstance(savings_bytes, (int, float))
                        else None
                    ),
                    "where_to_fix": _location(audit),
                    "evidence": _evidence(audit),
                    "warnings": [str(value) for value in audit.get("warnings", [])],
                    "error_message": audit.get("errorMessage"),
                    "recommendation": (
                        f"Fix {audit.get('title', audit_id)}. "
                        "Apply the changes shown in the audit details and re-run Lighthouse."
                    ),
                })

            return sorted(
                items,
                key=lambda item: item["estimated_savings_ms"] or 0,
                reverse=True,
            )[:50]

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
            "accessibility_score": _score("accessibility"),
            "best_practices_score": _score("best-practices"),
            "fcp_ms": _to_ms(fcp_display),
            "lcp_ms": _to_ms(lcp_display),
            "tbt_ms": _to_ms(tbt_display),
            "cls": float(cls_display) if cls_display is not None else None,
            "recommendations": _recommendations(),
        }