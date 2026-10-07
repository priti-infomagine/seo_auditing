import asyncio
import base64
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx


def normalize_domain(value: str) -> str:
    value = (value or "").strip().lower()
    if not value:
        raise ValueError("domain must not be empty")

    try:
        parsed = urlparse(value if "://" in value else f"//{value}")
        host = parsed.hostname or ""
    except ValueError as exc:
        raise ValueError("could not extract a domain") from exc

    if host.startswith("www."):
        host = host[4:]
    if not host or any(character.isspace() for character in host):
        raise ValueError("could not extract a domain")
    return host


class DataForSEOClient:
    BASE_URL = "https://api.dataforseo.com/v3"
    RETRY_STATUS = {429, 500, 502, 503, 504}
    MAX_ATTEMPTS = 3
    EVIDENCE_LIMIT = 5

    def __init__(self, login: str, password: str):
        token = base64.b64encode(f"{login}:{password}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60, headers=self.headers)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _post(self, endpoint: str, payload: list[dict[str, Any]]) -> Dict[str, Any]:
        client = self._get_client()
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                response = await client.post(
                    f"{self.BASE_URL}{endpoint}",
                    json=payload,
                )
                if (
                    response.status_code in self.RETRY_STATUS
                    and attempt < self.MAX_ATTEMPTS
                ):
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict):
                    raise ValueError("DataForSEO returned an invalid response")
                return body
            except httpx.TransportError:
                if attempt == self.MAX_ATTEMPTS:
                    raise
                await asyncio.sleep(2 ** (attempt - 1))
        raise RuntimeError("DataForSEO request exhausted retries")

    @staticmethod
    def _first_result(body: Dict[str, Any], description: str) -> Dict[str, Any]:
        if body.get("status_code") != 20000:
            raise RuntimeError(
                f"DataForSEO {description} failed: {body.get('status_message')}"
            )
        tasks = body.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise ValueError(f"DataForSEO {description} response has no tasks")
        task = tasks[0]
        if not isinstance(task, dict):
            raise ValueError(f"DataForSEO {description} response has an invalid task")
        if task.get("status_code") != 20000:
            raise RuntimeError(
                f"DataForSEO {description} task failed: {task.get('status_message')}"
            )
        results = task.get("result")
        if (
            not isinstance(results, list)
            or not results
            or not isinstance(results[0], dict)
        ):
            raise ValueError(f"DataForSEO {description} returned no result")
        return results[0]

    @staticmethod
    def _evidence_urls(result: Dict[str, Any]) -> list[str]:
        items = result.get("items")
        if not isinstance(items, list):
            raise ValueError("DataForSEO backlink evidence response has no items")
        urls = []
        for item in items:
            if isinstance(item, dict):
                url = item.get("url_from")
                if isinstance(url, str) and url and url not in urls:
                    urls.append(url)
        return urls[: DataForSEOClient.EVIDENCE_LIMIT]

    @staticmethod
    def _broken_evidence(result: Dict[str, Any]) -> list[dict[str, Any]]:
        items = result.get("items")
        if not isinstance(items, list):
            raise ValueError(
                "DataForSEO broken backlink evidence response has no items"
            )
        seen: set[str] = set()
        evidence: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url_to = item.get("url_to")
            if not isinstance(url_to, str) or not url_to or url_to in seen:
                continue
            seen.add(url_to)
            evidence.append(
                {
                    "url_from": item.get("url_from"),
                    "url_to": url_to,
                    "url_to_status_code": item.get("url_to_status_code"),
                }
            )
            if len(evidence) == DataForSEOClient.EVIDENCE_LIMIT:
                break
        return evidence

    async def get_backlink_summary(self, domain: str) -> Dict[str, Any]:
        target = normalize_domain(domain)
        summary_body = await self._post(
            "/backlinks/summary/live",
            [
                {
                    "target": target,
                    "include_subdomains": True,
                    "exclude_internal_backlinks": True,
                    "backlinks_status_type": "live",
                }
            ],
        )
        summary = self._first_result(summary_body, "backlink summary")

        base_evidence_task = {
            "target": target,
            "limit": self.EVIDENCE_LIMIT,
            "mode": "as_is",
        }
        referring_pages_body = await self._post(
            "/backlinks/backlinks/live",
            [base_evidence_task],
        )
        referring_pages_result = self._first_result(
            referring_pages_body, "referring page evidence"
        )
        referring_pages = self._evidence_urls(referring_pages_result)
        response_bodies = [summary_body, referring_pages_body]

        broken_backlinks: list[dict[str, Any]] = []
        broken_count = summary.get("broken_backlinks")
        if isinstance(broken_count, (int, float)) and broken_count > 0:
            broken_evidence_task = {
                **base_evidence_task,
                "filters": ["is_broken", "=", True],
            }
            broken_body = await self._post(
                "/backlinks/backlinks/live",
                [broken_evidence_task],
            )
            broken_result = self._first_result(
                broken_body, "broken backlink evidence"
            )
            broken_backlinks = self._broken_evidence(broken_result)
            response_bodies.append(broken_body)
        return {
            "domain": summary.get("target") or target,
            "domainRank": summary.get("rank"),
            "backlinks": summary.get("backlinks"),
            "referringDomains": summary.get("referring_domains"),
            "referringMainDomains": summary.get("referring_main_domains"),
            "referringPages": summary.get("referring_pages"),
            "brokenBacklinks": summary.get("broken_backlinks"),
            "backlinksSpamScore": summary.get("backlinks_spam_score"),
            "cost": round(
                sum(float(body.get("cost") or 0) for body in response_bodies),
                6,
            ),
            "evidence": {
                "referringPages": referring_pages,
                "brokenBacklinks": broken_backlinks,
            },
        }
