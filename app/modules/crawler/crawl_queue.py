"""
Crawl queue service - manages crawl queue with BFS/DFS and retries.
Business logic for queue management.
"""
from collections import deque
from typing import Optional
from uuid import UUID

from app.modules.crawler.utils.url_classifier import classify_url, strip_tracking_params
from app.shared.utils.url_utils import get_domain, is_internal_link, normalize_url


class QueueItem:
    """Item in crawl queue."""
    def __init__(self, url: str, depth: int, parent_page_id: Optional[UUID] = None):
        self.url = url
        self.depth = depth
        self.parent_page_id = parent_page_id


class CrawlQueueService:
    """Service for crawl queue management (BFS)."""

    def __init__(
        self,
        max_depth: int = 5,
        max_pages: int = 100,
        base_domain: Optional[str] = None,
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.base_domain = base_domain
        self.queue: deque[QueueItem] = deque()
        self.visited: set[str] = set()
        self.crawled_count = 0
        self.rejected: list[dict] = []
        # Per (url, depth) dedup — allows the same URL at different depths
        # (e.g. discovered via a longer path later) while preventing the same
        # URL at the same depth from being queued twice.
        self._queued: set[tuple[str, int]] = set()
        # URLs explicitly marked as visited via mark_visited() block all
        # depths from re-entering the queue.
        self._manually_visited: set[str] = set()

    def add_url(
        self,
        url: str,
        depth: int,
        parent_page_id: Optional[UUID] = None,
    ) -> bool:
        """
        Add URL to queue if not visited, within limits, and crawlable.

        Classifies the URL before enqueuing. Non-HTML, invalid, ignored,
        and external URLs are rejected rather than silently dropped.

        Args:
            url: URL to add
            depth: Current depth
            parent_page_id: Parent page ID

        Returns:
            True if added, False otherwise
        """
        if depth > self.max_depth:
            self.rejected.append({"url": url, "depth": depth, "reason": "depth_limit"})
            return False

        if len(self.queue) + self.crawled_count >= self.max_pages:
            self.rejected.append({"url": url, "reason": "page_limit"})
            return False

        classification, reason = classify_url(url, self.base_domain)

        if classification in ("INVALID", "IGNORED", "ROBOTS", "SITEMAP", "API"):
            self.rejected.append({"url": url, "classification": classification, "reason": reason})
            return False

        if classification == "EXTERNAL":
            self.rejected.append({"url": url, "classification": classification, "reason": reason})
            return False

        if classification == "RESOURCE":
            self.rejected.append({"url": url, "classification": classification, "reason": reason})
            return False

        normalized = normalize_url(url)

        if normalized in self._manually_visited:
            self.rejected.append({"url": url, "reason": "duplicate"})
            return False

        if (normalized, depth) in self._queued:
            self.rejected.append({"url": url, "reason": "duplicate"})
            return False

        self.queue.append(QueueItem(url, depth, parent_page_id))
        self.visited.add(normalized)
        self._queued.add((normalized, depth))
        return True

    def get_next(self) -> Optional[QueueItem]:
        """
        Get next URL from queue (BFS).

        Returns:
            QueueItem or None if empty
        """
        if self.queue:
            self.crawled_count += 1
            return self.queue.popleft()
        return None

    def mark_visited(self, url: str) -> None:
        """Mark URL as visited (blocks all future add_url calls for this URL)."""
        normalized = normalize_url(url)
        self._manually_visited.add(normalized)
        self.visited.add(normalized)

    @property
    def remaining(self) -> int:
        """Get number of items remaining in queue."""
        return len(self.queue)

    @property
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self.queue) == 0
