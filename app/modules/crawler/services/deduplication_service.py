"""
DeduplicationService - Handles URL and content hash deduplication for crawler jobs.
"""
import hashlib
from typing import Set

from app.modules.crawler.utils.url import normalize_url_canonical


class DeduplicationService:
    """Tracks visited URLs, url hashes, and content hashes within a crawl scope."""

    def __init__(self):
        self.visited_urls: Set[str] = set()
        self.url_hashes: Set[str] = set()
        self.content_hashes: Set[str] = set()

    def hash_url(self, url: str) -> str:
        canonical = normalize_url_canonical(url)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def is_url_visited(self, url: str) -> bool:
        canonical = normalize_url_canonical(url)
        h = self.hash_url(canonical)
        return canonical in self.visited_urls or h in self.url_hashes

    def mark_url_visited(self, url: str) -> str:
        canonical = normalize_url_canonical(url)
        h = self.hash_url(canonical)
        self.visited_urls.add(canonical)
        self.url_hashes.add(h)
        return h

    def hash_content(self, text_or_bytes: bytes | str) -> str:
        if isinstance(text_or_bytes, str):
            data = text_or_bytes.encode("utf-8")
        else:
            data = text_or_bytes
        return hashlib.sha256(data).hexdigest()

    def is_duplicate_content(self, content_hash: str) -> bool:
        return content_hash in self.content_hashes

    def mark_content_seen(self, content_hash: str) -> None:
        if content_hash:
            self.content_hashes.add(content_hash)
