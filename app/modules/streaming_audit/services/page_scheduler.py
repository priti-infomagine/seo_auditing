from __future__ import annotations

from typing import Iterable

from app.modules.streaming_audit.services.streaming_audit_service import dedupe_urls, normalize_url


class PageScheduler:
    """Minimal scheduler abstraction for the experimental streaming audit model.

    The production crawler remains unchanged; this scheduler only enforces the
    experimental concurrency/backpressure and deduplication rules.
    """

    def __init__(self, max_pages: int = 100, max_depth: int = 3):
        self.max_pages = max_pages
        self.max_depth = max_depth

    def should_enqueue(self, url: str, depth: int = 0) -> bool:
        if depth > self.max_depth:
            return False
        return bool(normalize_url(url))

    def schedule_batch(self, urls: Iterable[str], depth: int = 0) -> list[str]:
        discovered: list[str] = []
        for value in urls:
            normalized = normalize_url(value)
            if not self.should_enqueue(normalized, depth):
                continue
            discovered.append(normalized)
        return dedupe_urls(discovered)[: self.max_pages]

    def schedule_fanout(
        self,
        urls: Iterable[str],
        depth: int = 0,
        active_slots: int = 0,
        concurrency_limit: int | None = None,
    ) -> list[str]:
        capacity = max(0, (concurrency_limit or self.max_pages) - max(0, active_slots))
        if capacity <= 0:
            return []
        queued = self.schedule_batch(urls, depth=depth)
        return queued[: min(len(queued), capacity, self.max_pages)]
