"""
Link Graph Service - builds site-wide link graph for dead-end page detection.

Analyzes the crawl's internal link structure to identify pages with zero
outbound internal links (dead ends) and computes link graph metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.modules.crawler.models.page_links import PageLink
from app.modules.crawler.repositories.page_link_repository import PageLinkRepository
from app.shared.utils.url_utils import normalize_url


@dataclass
class LinkGraphStats:
    """Site-wide link graph statistics."""
    total_pages: int = 0
    total_internal_links: int = 0
    dead_end_pages: List[str] = field(default_factory=list)
    out_degree: Dict[str, int] = field(default_factory=dict)
    in_degree: Dict[str, int] = field(default_factory=dict)
    orphan_pages: List[str] = field(default_factory=list)  # Pages with no inbound links


class LinkGraphService:
    """Builds and analyzes site-wide internal link graph."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.page_link_repo = PageLinkRepository(db)

    async def build_graph(self, audit_id: UUID) -> LinkGraphStats:
        """
        Build internal link graph for an audit.
        
        Returns LinkGraphStats with:
        - dead_end_pages: URLs with zero outbound internal links
        - out_degree: {normalized_url: count of outbound internal links}
        - in_degree: {normalized_url: count of inbound internal links}
        - orphan_pages: URLs with zero inbound internal links (except homepage)
        """
        logger.info(f"LinkGraphService.build_graph: starting audit_id={audit_id}")

        # Load all internal links for this crawl job
        links: List[PageLink] = await self.page_link_repo.get_by_crawl_job_id(audit_id)
        
        # Filter to internal links only
        internal_links = [l for l in links if l.is_internal and l.target_url]
        
        # Build adjacency maps using normalized URLs
        out_edges: Dict[str, Set[str]] = {}
        in_edges: Dict[str, Set[str]] = {}
        all_pages: Set[str] = set()
        
        for link in internal_links:
            try:
                source = normalize_url(link.source_url) if link.source_url else ""
                target = normalize_url(link.target_url)
            except Exception:
                continue
            
            if not source or not target:
                continue
                
            all_pages.add(source)
            all_pages.add(target)
            
            out_edges.setdefault(source, set()).add(target)
            in_edges.setdefault(target, set()).add(source)
        
        # Compute dead-end pages (pages with 0 outbound internal links)
        dead_ends = []
        out_degree = {}
        for page in all_pages:
            out_count = len(out_edges.get(page, set()))
            out_degree[page] = out_count
            if out_count == 0:
                dead_ends.append(page)
        
        # Compute in-degree
        in_degree = {}
        for page in all_pages:
            in_degree[page] = len(in_edges.get(page, set()))
        
        # Find orphan pages (no inbound links, excluding likely homepage)
        orphans = []
        for page in all_pages:
            if in_degree[page] == 0:
                # Heuristic: homepage often has no inbound internal links
                # Check if it's a root path
                if page.rstrip("/") not in ("", "/"):
                    orphans.append(page)
        
        stats = LinkGraphStats(
            total_pages=len(all_pages),
            total_internal_links=len(internal_links),
            dead_end_pages=dead_ends,
            out_degree=out_degree,
            in_degree=in_degree,
            orphan_pages=orphans,
        )
        
        logger.info(
            f"LinkGraphService.build_graph: done audit_id={audit_id} "
            f"pages={stats.total_pages} dead_ends={len(dead_ends)} orphans={len(orphans)}"
        )
        
        return stats


async def get_dead_end_pages(audit_id: UUID, db: AsyncSession) -> List[str]:
    """
    Convenience function to get dead-end page URLs for an audit.
    
    Returns list of normalized URLs that have zero outbound internal links.
    """
    service = LinkGraphService(db)
    stats = await service.build_graph(audit_id)
    return stats.dead_end_pages