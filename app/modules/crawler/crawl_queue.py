"""
Crawl queue service - manages crawl queue with BFS/DFS and retries.
Business logic for queue management.
"""
from collections import deque
from typing import Optional
from uuid import UUID

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
        max_pages: int = 1000,
        base_domain: Optional[str] = None,
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.base_domain = base_domain
        self.queue: deque[QueueItem] = deque()
        self.visited: set[str] = set()
        self.crawled_count = 0

    def add_url(
        self,
        url: str,
        depth: int,
        parent_page_id: Optional[UUID] = None,
    ) -> bool:
        """
        Add URL to queue if not visited and within depth/page limits.

        When ``base_domain`` is set, only internal links are enqueued
        (i.e. links whose domain matches ``base_domain``).

        Args:
            url: URL to add
            depth: Current depth
            parent_page_id: Parent page ID

        Returns:
            True if added, False otherwise
        """
        # Check depth limit
        if depth > self.max_depth:
            return False

        # Check page limit
        if self.crawled_count >= self.max_pages:
            return False

        # Normalize URL
        normalized = normalize_url(url)

        # Only enqueue internal links when a base domain is configured
        if self.base_domain:
            if not is_internal_link(self.base_domain, url):
                return False

        # Check if already visited
        if normalized in self.visited:
            return False

        # Add to queue
        self.queue.append(QueueItem(url, depth, parent_page_id))
        self.visited.add(normalized)
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
        """Mark URL as visited."""
        normalized = normalize_url(url)
        self.visited.add(normalized)

    @property
    def remaining(self) -> int:
        """Get number of items remaining in queue."""
        return len(self.queue)

    @property
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self.queue) == 0
