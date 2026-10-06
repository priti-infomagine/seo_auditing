import base64
from typing import Any, Dict, List, Sequence
from urllib.parse import urlparse

import httpx


class DataForSEOClient:
    BASE_URL = "https://api.dataforseo.com/v3"
    MAX_EVIDENCE_URLS = 1000

    def __init__(self, login: str, password: str):
        credentials = f"{login}:{password}".encode()
        encoded = base64.b64encode(credentials).decode()

        self.headers = {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
        }

    async def _post(self, endpoint: str, payload: List[Dict[str, Any]]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.BASE_URL}{endpoint}",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _first_result(response: Dict[str, Any], description: str) -> Dict[str, Any]:
        status_code = response.get("status_code")
        if status_code is not None and status_code != 20000:
            raise RuntimeError(
                f"DataForSEO {description} failed: "
                f"{response.get('status_message', status_code)}"
            )

        tasks = response.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise ValueError(f"DataForSEO {description} response has no tasks")

        task = tasks[0]
        task_status = task.get("status_code")
        if task_status is not None and task_status != 20000:
            raise RuntimeError(
                f"DataForSEO {description} task failed: "
                f"{task.get('status_message', task_status)}"
            )

        results = task.get("result")
        if not isinstance(results, list) or not results or not isinstance(results[0], dict):
            raise ValueError(f"DataForSEO {description} response has no result")
        return results[0]

    @staticmethod
    def _response_cost(response: Dict[str, Any], description: str) -> float:
        cost = response.get("cost")
        if not isinstance(cost, (int, float)):
            raise ValueError(f"DataForSEO {description} response has no numeric cost")
        return float(cost)

    @staticmethod
    def _unique_urls(
        items: Sequence[Dict[str, Any]],
        limit: int,
        unique_by_domain: bool = False,
        domain_field: str = "domain_from",
    ) -> List[str]:
        urls: List[str] = []
        seen = set()

        for item in items:
            url = item.get("url_from")
            if not isinstance(url, str) or not url:
                continue

            key = item.get(domain_field) if unique_by_domain else url
            if not isinstance(key, str) or not key:
                key = urlparse(url).hostname if unique_by_domain else url
            if not key or key in seen:
                continue

            seen.add(key)
            urls.append(url)
            if len(urls) >= limit:
                break

        return urls

    @classmethod
    def _build_evidence(
        cls,
        items: Sequence[Dict[str, Any]],
        limit: int,
    ) -> Dict[str, List[str]]:
        all_urls = cls._unique_urls(items, limit)
        broken_items = [item for item in items if item.get("is_broken") is True]

        return {
            "rank": all_urls,
            "backlinks": all_urls,
            "referringDomains": cls._unique_urls(items, limit, unique_by_domain=True),
            "referringMainDomains": cls._unique_urls(
                items,
                limit,
                unique_by_domain=True,
                domain_field="main_domain_from",
            ),
            "spamScore": all_urls,
            "brokenBacklinks": cls._unique_urls(broken_items, limit),
            "referringPages": all_urls,
        }

    async def get_backlink_summary(
        self,
        domain: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        if not 1 <= limit <= self.MAX_EVIDENCE_URLS:
            raise ValueError(
                f"limit must be between 1 and {self.MAX_EVIDENCE_URLS}"
            )

        summary_response = await self._post(
            "/backlinks/summary/live",
            [
                {
                    "target": domain,
                    "include_subdomains": True,
                    "exclude_internal_backlinks": True,
                    "backlinks_status_type": "live",
                }
            ],
        )
        backlinks_response = await self._post(
            "/backlinks/backlinks/live",
            [{"target": domain, "limit": limit, "mode": "as_is"}],
        )

        summary = self._first_result(summary_response, "backlink summary")
        backlink_result = self._first_result(backlinks_response, "backlink evidence")
        if "items" not in backlink_result:
            raise ValueError("DataForSEO backlink evidence response has no items")
        items = backlink_result["items"]
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError("DataForSEO backlink evidence has an invalid items list")

        metric_fields = {
            "rank": ("rank",),
            "backlinks": ("backlinks",),
            "referringDomains": ("referring_domains",),
            "referringMainDomains": ("referring_main_domains",),
            "spamScore": (
                "target_spam_score",
                "spam_score",
                "backlinks_spam_score",
            ),
            "brokenBacklinks": ("broken_backlinks",),
            "referringPages": ("referring_pages",),
        }
        data: Dict[str, Any] = {"target": summary.get("target", domain)}
        for output_name, provider_names in metric_fields.items():
            sources = [summary]
            if output_name == "spamScore" and isinstance(summary.get("info"), dict):
                sources.insert(0, summary["info"])
            for provider_name in provider_names:
                value_found = False
                for source in sources:
                    if provider_name in source:
                        data[output_name] = source[provider_name]
                        value_found = True
                        break
                if value_found:
                    break
            else:
                raise ValueError(
                    f"DataForSEO backlink summary is missing {provider_names[0]}"
                )

        total_cost = self._response_cost(
            summary_response, "backlink summary"
        ) + self._response_cost(backlinks_response, "backlink evidence")

        return [
            {
                "data": data,
                "cost": round(total_cost, 6),
                "evidence": self._build_evidence(items, limit),
            }
        ]

    async def get_backlinks(
        self,
        domain: str,
        limit: int = 100,
    ) -> Dict[str, Any]:
        return await self._post(
            "/backlinks/backlinks/live",
            [{"target": domain, "limit": limit, "mode": "as_is"}],
        )
