"""Graph dataclasses for the link_analysis module.

Pure data containers — no I/O, no business logic beyond trivial helpers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

from app.modules.seprate_checks.link_analysis.model import LinkStatusClass
from app.shared.utils.url_utils import is_same_site as check_same_site, normalize_host


@dataclass
class RedirectInfo:
    """A single redirect hop."""

    url: str
    status_code: int
    location: Optional[str] = None


@dataclass
class CheckResult:
    """Result of checking a single URL (crawled or link-checked)."""

    status_class: LinkStatusClass
    status_code: int
    final_url: Optional[str] = None
    redirect_chain: List[RedirectInfo] = field(default_factory=list)
    error_type: Optional[str] = None


@dataclass
class PageNode:
    """Represents a crawled page in the link graph."""

    url: str
    final_url: str
    status_code: int
    content_type: Optional[str]
    depth: int
    redirect_chain: List[RedirectInfo] = field(default_factory=list)
    error_type: Optional[str] = None
    outgoing_edges: List["LinkEdge"] = field(default_factory=list)
    blocked_by_robots: bool = False
    is_asset: bool = False


@dataclass
class LinkEdge:
    """A directed link edge from source page to target URL."""

    source_url: str
    target_url: str
    anchor_text: str
    rel: List[str] = field(default_factory=list)
    is_internal: bool = True
    href_raw: str = ""


@dataclass
class LinkGraph:
    """In-memory full link graph from a complete site crawl."""

    pages: Dict[str, PageNode] = field(default_factory=dict)
    sitemap_urls: Set[str] = field(default_factory=set)
    edges_by_source: Dict[str, Set[str]] = field(default_factory=dict)
    inbound_counts: Dict[str, int] = field(default_factory=dict)
    base_host: str = ""
    base_scheme: str = "https"
    crawl_truncated: bool = False
    blocked_by_robots: int = 0
    assets_skipped: int = 0

    def _ensure_edge_index(self, source: str) -> None:
        if source not in self.edges_by_source:
            self.edges_by_source[source] = set()

    def add_edge(self, edge: LinkEdge) -> None:
        self._ensure_edge_index(edge.source_url)
        self.edges_by_source[edge.source_url].add(edge.target_url)
        self.inbound_counts[edge.target_url] = (
            self.inbound_counts.get(edge.target_url, 0) + 1
        )

    def add_page(self, node: PageNode) -> None:
        self.pages[node.url] = node

    def is_same_site(self, host: str) -> bool:
        if not host:
            return False
        return normalize_host(host) == self.base_host or check_same_site(host, self.base_host)
