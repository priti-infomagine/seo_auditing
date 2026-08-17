"""
DBParserService - DB-backed parser service for the SSEO Analyzer pipeline.

Reads crawl pages + HTML snapshots from PostgreSQL (stored by CrawlPersistenceService),
runs ParserOrchestrator on each page's HTML, and persists the structured parsed
facts to `parsed_page_facts` table.

Replaces the file-based BatchParserService for production DB-backed pipelines.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.modules.audit.models.parsed_page_facts import ParsedPageFact
from app.modules.audit.repositories.parsed_page_fact_repository import ParsedPageFactRepository
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.page_seo_data import PageSEOData
from app.modules.crawler.models.page_snapshots import PageSnapshot
from app.modules.crawler.models.page_network_data import PageNetworkData
from app.modules.crawler.models.page_resources import PageResource
from app.modules.crawler.models.page_links import PageLink
from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
from app.modules.crawler.repositories.page_seo_data_repository import PageSEODataRepository
from app.modules.crawler.repositories.page_snapshot_repository import PageSnapshotRepository
from app.modules.crawler.repositories.page_network_data_repository import PageNetworkDataRepository
from app.modules.crawler.repositories.page_resource_repository import PageResourceRepository
from app.modules.crawler.repositories.page_link_repository import PageLinkRepository
from app.modules.parser.services.parser_orchestrator import ParserOrchestrator
from app.shared.exceptions import ParserError


class DBParserService:
    """
    DB-backed parser service.

    Replaces the file-based BatchParserService for production DB-backed pipelines.
    Reads HTML snapshots from PostgreSQL, runs the parser, and persists results
    back to PostgreSQL as `ParsedPageFact` rows.

    Each page is processed independently — a parse failure on one page does not
    stop the remaining pages.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.parsed_fact_repo = ParsedPageFactRepository(db)
        self.crawl_page_repo = CrawlPageRepository(db)
        self.seo_repo = PageSEODataRepository(db)
        self.snapshot_repo = PageSnapshotRepository(db)
        self.network_repo = PageNetworkDataRepository(db)
        self.resource_repo = PageResourceRepository(db)
        self.link_repo = PageLinkRepository(db)
        self.parser = ParserOrchestrator()

    async def parse_crawl(
        self,
        project_id: UUID,
        crawl_id: UUID,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Parse all successfully-crawled pages for a crawl job.

        Steps:
          1. Load all CrawlPages for crawl_id where is_success=True.
          2. For each page: load snapshot HTML, run ParserOrchestrator.
          3. Build flat page_facts + elements + attributes dicts.
          4. Persist via upsert (ON CONFLICT DO UPDATE — no duplicates).
          5. Return summary with counts and any errors.

        Fault-tolerant: each page is wrapped in try/except; failures are
        logged and recorded, remaining pages continue processing.

        Args:
            project_id: The project tracking key.
            crawl_id: The crawl job ID.
            force: If True, re-parse pages that already have parsed facts.

        Returns:
            Dict with keys: project_id, crawl_id, pages_parsed, pages_failed,
                            pages_skipped, errors, parsed_at.
        """
        try:
            logger.info(
                f"DBParserService.parse_crawl: project_id={project_id}, crawl_id={crawl_id}, force={force}"
            )

            pages = await self.crawl_page_repo.get_by_crawl_id(crawl_id)
            pages_to_parse = [p for p in pages if p.is_success]

            if not pages_to_parse:
                logger.warning(
                    f"DBParserService.parse_crawl: no crawled pages found for crawl_id={crawl_id}"
                )
                return {
                    "project_id": str(project_id),
                    "crawl_id": str(crawl_id),
                    "pages_parsed": 0,
                    "pages_failed": 0,
                    "pages_skipped": len(pages),
                    "errors": [],
                    "parsed_at": datetime.now(timezone.utc).isoformat(),
                }

            parsed_count = 0
            failed_count = 0
            skipped_count = 0
            errors: List[Dict[str, Any]] = []

            for page in pages_to_parse:
                try:
                    if not force and await self.parsed_fact_repo.exists(project_id, page.id):
                        skipped_count += 1
                        continue

                    fact = await self.parse_page(project_id, crawl_id, page.id)
                    if fact:
                        parsed_count += 1
                    else:
                        failed_count += 1
                        errors.append({
                            "page_id": str(page.id),
                            "url": page.url,
                            "error": "Parse returned no result",
                        })
                except Exception as exc:
                    failed_count += 1
                    logger.error(
                        f"DBParserService: parse failed for page_id={page.id}: {exc}",
                        exc_info=True,
                    )
                    errors.append({
                        "page_id": str(page.id),
                        "url": page.url,
                        "error": str(exc),
                    })

            logger.info(
                f"DBParserService.parse_crawl: parsed={parsed_count}, "
                f"failed={failed_count}, skipped={skipped_count} for project_id={project_id}"
            )

            return {
                "project_id": str(project_id),
                "crawl_id": str(crawl_id),
                "pages_parsed": parsed_count,
                "pages_failed": failed_count,
                "pages_skipped": skipped_count,
                "errors": errors,
                "parsed_at": datetime.now(timezone.utc).isoformat(),
            }

        except ParserError:
            raise
        except Exception as exc:
            logger.error(
                f"DBParserService.parse_crawl: unhandled error for crawl_id={crawl_id}: {exc}",
                exc_info=True,
            )
            raise ParserError(f"Crawl parse failed: {exc}") from exc

    async def parse_page(
        self,
        project_id: UUID,
        crawl_id: UUID,
        page_id: UUID,
        force: bool = False,
    ) -> Optional[ParsedPageFact]:
        """
        Parse a single page and persist the parsed facts.

        Loads the HTML snapshot, network data, SEO data, resources, and links
        from PostgreSQL, runs the parser, and builds a ParsedPageFact.

        Args:
            project_id: The project tracking key.
            crawl_id: The crawl job ID.
            page_id: The page ID to parse.
            force: If True, re-parse even if facts already exist.

        Returns:
            ParsedPageFact if successful, None if no HTML snapshot.
        """
        try:
            # Check for existing facts (unless force)
            if not force and await self.parsed_fact_repo.exists(project_id, page_id):
                logger.debug(
                    f"DBParserService.parse_page: skipping existing fact for page_id={page_id}"
                )
                return await self.parsed_fact_repo.get_by_page_id(project_id, page_id)

            # Load page
            page = await self.crawl_page_repo.get_by_id(page_id)
            if not page:
                logger.warning(f"DBParserService.parse_page: page_id={page_id} not found")
                return None

            # Load snapshot HTML
            snapshot = await self.snapshot_repo.get_by_page_id(page_id)
            if not snapshot or not snapshot.content:
                logger.warning(f"DBParserService.parse_page: no snapshot for page_id={page_id}")
                return None

            # Load network data
            network_data = await self.network_repo.get_by_page_id(page_id)
            network_dict: Dict[str, Any] = {}
            if network_data:
                network_dict = {
                    "status_code": network_data.status_code or 0,
                    "content_type": network_data.content_type or "",
                    "response_time_ms": network_data.response_time_ms or 0,
                    "headers": network_data.headers or {},
                    "redirects": network_data.redirects or [],
                    "security": network_data.security or {},
                    "performance": network_data.performance or {},
                }

            # Load SEO data
            seo_data = await self.seo_repo.get_by_page_id(page_id)
            seo_dict: Dict[str, Any] = {}
            if seo_data:
                seo_dict = {
                    "title": seo_data.title or "",
                    "title_length": seo_data.title_length or 0,
                    "meta_description": seo_data.meta_description or "",
                    "meta_description_length": seo_data.meta_description_length or 0,
                    "canonical": seo_data.canonical or "",
                    "robots_meta": seo_data.robots_meta or "",
                    "language": seo_data.language or "",
                    "charset": seo_data.charset or "",
                    "viewport": seo_data.viewport or "",
                    "favicon": seo_data.favicon or "",
                    "word_count": seo_data.word_count or 0,
                    "headings": seo_data.headings or {},
                    "structured_data": seo_data.structured_data or {},
                    "social": seo_data.social or {},
                    "indexability": seo_data.indexability or {},
                    "accessibility": seo_data.accessibility or {},
                    "page_metadata": seo_data.page_metadata or {},
                }

            # Run parser on the HTML
            html = snapshot.content
            parsed = self.parser.parse(html=html, url=page.normalized_url)

            # Build parsed_data dict
            parsed_data = parsed.model_dump(mode="json")

            # Build flat page_facts for easy querying
            page_facts = self._build_page_facts(parsed, page, network_dict, seo_dict)

            # Build elements (structured headings, paragraphs, lists, tables)
            elements = self._build_elements(parsed)

            # Build attributes (element attributes: ids, classes, ARIA, data-*)
            attributes = self._build_attributes(parsed)

            # Compute content hash for duplicate detection
            text_content = parsed.content.text if parsed.content and parsed.content.text else ""
            content_hash = hashlib.md5(text_content.encode("utf-8")).hexdigest() if text_content else None

            # Build parse errors list
            parse_errors = []
            if parsed.parser_metadata:
                parse_errors = list(parsed.parser_metadata.warnings or [])
                parse_errors.extend(parsed.parser_metadata.errors or [])

            # Create ParsedPageFact
            fact = ParsedPageFact(
                project_id=project_id,
                crawl_id=crawl_id,
                page_id=page_id,
                url=page.normalized_url,
                domain=page.host or "",
                parsed_data=parsed_data,
                page_facts=page_facts,
                elements=elements,
                attributes=attributes,
                parse_errors=parse_errors or None,
                content_hash=content_hash,
                parsed_at=datetime.now(timezone.utc),
            )

            # Persist (upsert)
            result = await self.parsed_fact_repo.upsert(fact)

            logger.debug(
                f"DBParserService.parse_page: parsed page_id={page_id}, "
                f"url={page.normalized_url}"
            )
            return result

        except Exception as exc:
            logger.error(
                f"DBParserService.parse_page: error for page_id={page_id}: {exc}",
                exc_info=True,
            )
            raise ParserError(f"Page parse failed for page_id={page_id}: {exc}") from exc

    def _build_page_facts(
        self,
        parsed,
        page: CrawlPage,
        network_dict: Dict[str, Any],
        seo_dict: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build flat page_facts dict from parsed data + DB rows."""
        return {
            "title": seo_dict.get("title", ""),
            "title_length": seo_dict.get("title_length", 0),
            "meta_description": seo_dict.get("meta_description", ""),
            "meta_description_length": seo_dict.get("meta_description_length", 0),
            "canonical": seo_dict.get("canonical", ""),
            "robots_meta": seo_dict.get("robots_meta", ""),
            "language": seo_dict.get("language", ""),
            "charset": seo_dict.get("charset", ""),
            "viewport": seo_dict.get("viewport", ""),
            "favicon": seo_dict.get("favicon", ""),
            "word_count": seo_dict.get("word_count", 0),
            "content_hash": seo_dict.get("content_hash", ""),
            "url": parsed.document.url if parsed.document else page.normalized_url,
            "scheme": page.scheme or "https",
            "host": page.host or "",
            "status_code": network_dict.get("status_code", 0),
            "response_time_ms": network_dict.get("response_time_ms", 0),
            "content_type": network_dict.get("content_type", ""),
            "html_size": parsed.document.html_size if parsed.document else 0,
            "doctype": parsed.document.doctype if parsed.document else "",
            "content_text": parsed.content.text[:10000] if parsed.content and parsed.content.text else "",
            "paragraph_count": parsed.content.paragraph_count if parsed.content else 0,
            "sentence_count": parsed.content.sentence_count if parsed.content else 0,
            "total_links": len(parsed.links) if parsed.links else 0,
            "total_images": len(parsed.images) if parsed.images else 0,
            "total_resources": len(parsed.resources) if parsed.resources else 0,
            "total_headings": len(parsed.headings) if parsed.headings else 0,
            "structured_data_count": len(parsed.schemas) if parsed.schemas else 0,
            "redirect_count": len(network_dict.get("redirects", [])),
            "security": network_dict.get("security", {}),
            "performance": network_dict.get("performance", {}),
            "headers": network_dict.get("headers", {}),
        }

    def _build_elements(self, parsed) -> Dict[str, Any]:
        """Build structured elements dict (headings, paragraphs, lists, tables)."""
        headings = []
        if parsed.headings:
            for h in parsed.headings:
                headings.append({
                    "level": h.level,
                    "text": h.text,
                    "id": h.id,
                })

        paragraphs = []
        if parsed.content and parsed.content.paragraphs:
            for p in parsed.content.paragraphs:
                paragraphs.append({
                    "text": p.text[:500],
                    "word_count": len(p.text.split()) if p.text else 0,
                })

        lists = []
        if parsed.content and parsed.content.lists:
            for l in parsed.content.lists:
                lists.append({
                    "items": l.items,
                    "type": l.type if hasattr(l, "type") else "ul",
                })

        tables = []
        if parsed.content and parsed.content.tables:
            for t in parsed.content.tables:
                tables.append({
                    "rows": t.rows if hasattr(t, "rows") else 0,
                    "columns": t.columns if hasattr(t, "columns") else 0,
                })

        return {
            "headings": headings,
            "paragraphs": paragraphs,
            "lists": lists,
            "tables": tables,
        }

    def _build_attributes(self, parsed) -> Dict[str, Any]:
        """Build element attributes dict (ids, classes, ARIA, data-*)."""
        attrs: Dict[str, Any] = {
            "links": [],
            "images": [],
            "resources": [],
        }

        if parsed.links:
            for link in parsed.links:
                attrs["links"].append({
                    "href": link.href,
                    "anchor_text": link.anchor_text,
                    "rel": link.rel,
                    "is_internal": link.is_internal,
                    "is_external": link.is_external,
                    "id": link.id,
                    "classes": link.class_names if hasattr(link, "class_names") else [],
                    "aria_label": link.aria_label if hasattr(link, "aria_label") else None,
                })

        if parsed.images:
            for img in parsed.images:
                attrs["images"].append({
                    "src": img.src,
                    "alt": img.alt,
                    "width": img.width,
                    "height": img.height,
                    "loading": img.loading if hasattr(img, "loading") else None,
                    "id": img.id,
                    "classes": img.class_names if hasattr(img, "class_names") else [],
                })

        if parsed.resources:
            for res in parsed.resources:
                attrs["resources"].append({
                    "url": res.url,
                    "resource_type": res.resource_type if hasattr(res, "resource_type") else "",
                    "id": res.id if hasattr(res, "id") else None,
                })

        return attrs
