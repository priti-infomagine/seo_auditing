"""
RuleEvaluatorService - DB-backed rule evaluation for the SSEO Analyzer pipeline.

Reads parsed page facts + crawler data from PostgreSQL, reconstructs the
`data` dict that the 60+ SEO rules expect, runs each rule, and persists
RuleResult objects to `rule_evaluation_results`.

Fault-tolerant: each rule is evaluated in a try/except. Failed rules get a
synthetic RuleResult with severity=error. Processing continues for all
remaining rules and pages.
"""
from __future__ import annotations

import asyncio
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.logger import logger
from app.modules.audit.repositories.parsed_page_fact_repository import ParsedPageFactRepository
from app.modules.audit.repositories.rule_evaluation_repository import RuleEvaluationResultRepository
from app.modules.audit.models.rule_evaluation_results import RuleEvaluationResult
from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
from app.modules.crawler.repositories.page_seo_data_repository import PageSEODataRepository
from app.modules.crawler.repositories.page_network_data_repository import PageNetworkDataRepository
from app.modules.crawler.repositories.page_resource_repository import PageResourceRepository
from app.modules.crawler.repositories.page_link_repository import PageLinkRepository
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.rule_engine.models.rule_result import RuleResult, Severity
from app.modules.scorer.services.scorer_service import ScorerService
from app.modules.scorer.services.base_rule import BaseRule
from app.shared.exceptions import RuleEvaluationError


class RuleEvaluatorService:
    """
    Bridges DB-fetched facts → rules → persisted results.

    The 60+ SEO rules expect a `data` dict with keys like `basic`, `http`,
    `url`, `ssl`, `content`, `headings`, `links`, `images`, `schemas`,
    `social`, `performance`, etc. This service reconstructs that dict from
    the DB and passes it to each rule's `evaluate()` method.
    """

    # Keys that the rule data dict should contain
    RULE_DATA_KEYS = [
        "basic", "http", "url", "ssl", "performance",
        "javascript", "seo", "social", "media",
        "content", "headings", "links", "images",
        "schemas", "hreflang", "resources", "technical",
    ]

    def __init__(self, db: AsyncSession):
        self.db = db
        self.parsed_fact_repo = ParsedPageFactRepository(db)
        self.rule_eval_repo = RuleEvaluationResultRepository(db)
        self.crawl_page_repo = CrawlPageRepository(db)
        self.seo_repo = PageSEODataRepository(db)
        self.network_repo = PageNetworkDataRepository(db)
        self.resource_repo = PageResourceRepository(db)
        self.link_repo = PageLinkRepository(db)
        self.scorer_service = ScorerService()
        self.rules: List[BaseRule] = self.scorer_service.rules

    async def evaluate_crawl(
        self,
        project_id: UUID,
        crawl_id: UUID,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluate all rules for all parsed pages of a crawl.

        Steps:
          1. Load all ParsedPageFact rows for (project_id, crawl_id).
          2. For each page: reconstruct the `data` dict rules expect.
          3. Run all 60+ rules against each page's data (concurrently per page).
          4. Bulk upsert RuleEvaluationResult rows (ON CONFLICT DO UPDATE).
          5. Return summary with counts and any errors.

        Fault-tolerant: per-rule and per-page failures are caught and recorded.

        Args:
            project_id: The project tracking key.
            crawl_id: The crawl job ID.
            force: If True, re-evaluate rules even if results exist.

        Returns:
            Dict with project_id, crawl_id, pages_evaluated, rules_run,
            total_results, errors, evaluated_at.
        """
        try:
            logger.info(
                f"RuleEvaluatorService.evaluate_crawl: project_id={project_id}, crawl_id={crawl_id}, force={force}"
            )

            parsed_facts = await self.parsed_fact_repo.get_by_crawl_id(crawl_id)

            # Filter to only this project's facts (defensive — crawl_id is scoped to project)
            parsed_facts = [f for f in parsed_facts if str(f.project_id) == str(project_id)]

            if not parsed_facts:
                logger.warning(
                    f"RuleEvaluatorService.evaluate_crawl: no parsed facts for "
                    f"project_id={project_id}, crawl_id={crawl_id}"
                )
                return {
                    "project_id": str(project_id),
                    "crawl_id": str(crawl_id),
                    "pages_evaluated": 0,
                    "rules_run": 0,
                    "total_results": 0,
                    "errors": [],
                    "evaluated_at": utc_now().isoformat(),
                }

            pages_evaluated = 0
            total_results = 0
            rules_run = 0
            all_results: List[RuleEvaluationResult] = []
            errors: List[Dict[str, Any]] = []

            for fact in parsed_facts:
                try:
                    if not force:
                        # Check if results already exist for this page
                        existing = await self.rule_eval_repo.get_by_page_id(project_id, fact.page_id)
                        if existing:
                            pages_evaluated += 1
                            continue

                    page_results = await self.evaluate_page(project_id, crawl_id, fact.page_id)
                    all_results.extend(page_results)
                    total_results += len(page_results)
                    rules_run += len(self.rules)
                    pages_evaluated += 1
                except Exception as exc:
                    logger.error(
                        f"RuleEvaluatorService: evaluation failed for page_id={fact.page_id}: {exc}",
                        exc_info=True,
                    )
                    errors.append({
                        "page_id": str(fact.page_id),
                        "url": fact.url,
                        "error": str(exc),
                    })
                    # Create a single error result for the page
                    error_result = RuleEvaluationResult(
                        project_id=project_id,
                        crawl_id=crawl_id,
                        page_id=fact.page_id,
                        rule_id="evaluation_error",
                        rule_name="Page Evaluation Error",
                        category="error",
                        severity=Severity.ERROR.value,
                        passed=False,
                        score_impact=0,
                        message=str(exc),
                        recommendation="Fix data or rule configuration",
                        evaluated_at=utc_now(),
                    )
                    all_results.append(error_result)
                    total_results += 1

            # Bulk upsert all results
            if all_results:
                await self.rule_eval_repo.bulk_upsert(all_results)

            logger.info(
                f"RuleEvaluatorService.evaluate_crawl: pages_evaluated={pages_evaluated}, "
                f"rules_run={rules_run}, total_results={total_results}, "
                f"errors={len(errors)} for project_id={project_id}"
            )

            return {
                "project_id": str(project_id),
                "crawl_id": str(crawl_id),
                "pages_evaluated": pages_evaluated,
                "rules_run": rules_run,
                "total_results": total_results,
                "errors": errors,
                "evaluated_at": utc_now().isoformat(),
            }

        except Exception as exc:
            logger.error(
                f"RuleEvaluatorService.evaluate_crawl: unhandled error for crawl_id={crawl_id}: {exc}",
                exc_info=True,
            )
            raise RuleEvaluationError(f"Crawl evaluation failed: {exc}") from exc

    async def evaluate_page(
        self,
        project_id: UUID,
        crawl_id: UUID,
        page_id: UUID,
    ) -> List[RuleEvaluationResult]:
        """
        Evaluate all rules for a single page.

        Reconstructs the `data` dict from DB rows, then runs each rule.
        Each rule is wrapped in try/except — failures become synthetic
        RuleEvaluationResult rows with severity=error.

        Args:
            project_id: The project tracking key.
            crawl_id: The crawl job ID.
            page_id: The page ID to evaluate.

        Returns:
            List of RuleEvaluationResult objects (one per rule, or synthetic
            error result if evaluation fails).
        """
        try:
            # Reconstruct data dict
            data = await self._build_rule_data(project_id, crawl_id, page_id)

            # Run all rules concurrently for speed
            rule_results: List[RuleResult] = []
            for rule in self.rules:
                try:
                    results = await asyncio.wait_for(rule.evaluate(data), timeout=30.0)
                    rule_results.extend(results)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Rule {rule.rule_id} timed out for page_id={page_id}"
                    )
                    rule_results.append(self._create_error_result(
                        rule, page_id, "Rule evaluation timed out after 30s"
                    ))
                except Exception as exc:
                    logger.error(
                        f"Rule {rule.rule_id} failed for page_id={page_id}: {exc}",
                        exc_info=True,
                    )
                    rule_results.append(self._create_error_result(
                        rule, page_id, f"Rule evaluation failed: {exc}"
                    ))

            # Convert to RuleEvaluationResult and set project_id/crawl_id/page_id
            now = utc_now()
            eval_results = [
                RuleEvaluationResult(
                    project_id=project_id,
                    crawl_id=crawl_id,
                    page_id=page_id,
                    rule_id=rr.rule_id,
                    rule_name=rr.name,
                    category=rr.category,
                    severity=rr.severity.value,
                    passed=rr.passed,
                    score_impact=rr.score_impact,
                    message=rr.message,
                    recommendation=rr.recommendation,
                    rule_data=rr.data,
                    tags=rr.tags,
                    evaluated_at=now,
                )
                for rr in rule_results
            ]

            return eval_results

        except Exception as exc:
            logger.error(
                f"RuleEvaluatorService.evaluate_page: error for page_id={page_id}: {exc}",
                exc_info=True,
            )
            raise RuleEvaluationError(f"Page evaluation failed for page_id={page_id}: {exc}") from exc

    async def _build_rule_data(
        self,
        project_id: UUID,
        crawl_id: UUID,
        page_id: UUID,
    ) -> Dict[str, Any]:
        """
        Reconstruct the `data` dict that SEO rules expect.

        Maps DB tables → rule data dict keys:

        | Rule key    | Source                                         |
        |-------------|-------------------------------------------------|
        | basic       | page_seo_data(title, meta_description, etc.)   |
        | http        | page_network_data(status_code, headers, etc.)  |
        | url         | crawl_pages(scheme, host, normalized_url)       |
        | ssl         | page_network_data.security                     |
        | performance | page_network_data.performance                  |
        | content     | parsed_page_facts.parsed_data.content          |
        | headings    | parsed_page_facts.parsed_data.headings         |
        | links       | parsed_page_facts.parsed_data.links            |
        | images      | parsed_page_facts.parsed_data.images           |
        | schemas     | parsed_page_facts.parsed_data.schemas          |
        | social      | parsed_page_facts.parsed_data.social           |
        | hreflang    | parsed_page_facts.parsed_data.hreflang         |
        | resources   | parsed_page_facts.parsed_data.resources        |
        | technical   | page_seo_data.accessibility, network.security  |
        | javascript  | page_network_data.performance (or empty)       |
        | seo         | page_seo_data (basic SEO facts)                |
        | media       | parsed_page_facts.parsed_data.images           |
        """
        # Start with safe empty defaults
        data: Dict[str, Any] = {key: {} for key in self.RULE_DATA_KEYS}

        try:
            # --- Load parsed facts ---
            parsed_fact = await self.parsed_fact_repo.get_by_page_id(project_id, page_id)
            if parsed_fact:
                parsed_data = parsed_fact.parsed_data or {}
                # Map parsed data keys to rule data keys
                data["content"] = parsed_data.get("content", {})
                data["headings"] = self._build_headings_summary(parsed_data.get("headings", []))
                data["links"] = self._build_links_summary(parsed_data.get("links", []))
                data["images"] = self._build_images_summary(parsed_data.get("images", []))
                data["schemas"] = parsed_data.get("schemas", [])
                data["structured_data"] = self._build_structured_data(parsed_data.get("schemas", []))
                data["hreflang"] = parsed_data.get("hreflang", [])
                data["social"] = parsed_data.get("social", {}) or {}
                data["resources"] = parsed_data.get("resources", [])
                data["technical"] = parsed_data.get("technical", {}) or {}
                # Flatten page_facts for quick access
                data["_page_facts"] = parsed_fact.page_facts or {}
        except Exception as exc:
            logger.debug(f"Could not load parsed facts for page_id={page_id}: {exc}")

        try:
            # --- Load crawl page (url info) ---
            page = await self.crawl_page_repo.get_by_id(page_id)
            if page:
                data["url"] = {
                    "https": page.scheme == "https" if page.scheme else False,
                    "domain": page.host or "",
                    "path": page.path or "",
                    "query": page.query or "",
                    "normalized_url": page.normalized_url or "",
                    "final_url": page.final_url or "",
                    "status_code": page.status_code or 0,
                    "url": page.url or "",
                }
        except Exception as exc:
            logger.debug(f"Could not load crawl page for page_id={page_id}: {exc}")

        try:
            # --- Load SEO data (basic) ---
            seo_data = await self.seo_repo.get_by_page_id(page_id)
            if seo_data:
                data["basic"] = {
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
                    "content_hash": seo_data.content_hash or "",
                    "headings": seo_data.headings or {},
                    "structured_data": seo_data.structured_data or {},
                    "social": seo_data.social or {},
                    "indexability": seo_data.indexability or {},
                    "accessibility": seo_data.accessibility or {},
                    "page_metadata": seo_data.page_metadata or {},
                }
                data["seo"] = data["basic"].copy()
        except Exception as exc:
            logger.debug(f"Could not load SEO data for page_id={page_id}: {exc}")

        try:
            # --- Load network data ---
            network_data = await self.network_repo.get_by_page_id(page_id)
            if network_data:
                data["http"] = {
                    "status_code": network_data.status_code or 0,
                    "content_type": network_data.content_type or "",
                    "content_length": network_data.content_length or 0,
                    "response_time_ms": network_data.response_time_ms or 0,
                    "response_time": (network_data.response_time_ms or 0) / 1000.0,
                    "content_size": network_data.content_length or 0,
                    "headers": network_data.headers or {},
                    "redirects": network_data.redirects or [],
                }
                data["ssl"] = network_data.security or {}
                data["performance"] = network_data.performance or {}
                data["javascript"] = (network_data.performance or {}).get("javascript", {})
                # Merge security into technical
                if "technical" not in data or not data["technical"]:
                    data["technical"] = {}
                if isinstance(data["technical"], dict):
                    data["technical"]["security"] = network_data.security or {}
        except Exception as exc:
            logger.debug(f"Could not load network data for page_id={page_id}: {exc}")

        # Set defaults for remaining keys if not already populated
        data.setdefault("media", data.get("images", {}))
        data.setdefault("seo", data.get("basic", {}))
        data.setdefault("javascript", {})

        return data

    def _build_links_summary(self, links: list) -> dict:
        """Transform raw parsed links list into the dict structure that SEO rules expect."""
        internal_count = 0
        external_count = 0
        nofollow_count = 0
        internal_links = []
        external_links = []
        for link in links:
            if not isinstance(link, dict):
                continue
            is_external = (
                link.get("link_type") == "external" or link.get("is_external", False)
            )
            if is_external:
                external_count += 1
                external_links.append(link)
            else:
                internal_count += 1
                internal_links.append(link)
            if link.get("nofollow") or link.get("is_nofollow"):
                nofollow_count += 1
        return {
            "total_links": len(links),
            "internal_count": internal_count,
            "external_count": external_count,
            "nofollow_count": nofollow_count,
            "internal_links": internal_links,
            "external_links": external_links,
        }

    def _build_images_summary(self, images: list) -> dict:
        """Transform raw parsed images list into the dict structure that SEO rules expect."""
        total_count = len(images)
        without_alt = 0
        lazy_loading = False
        sample = []
        for img in images:
            if not isinstance(img, dict):
                continue
            alt = img.get('alt', '')
            if not alt or not alt.strip():
                without_alt += 1
            if img.get('loading', '').strip().lower() == 'lazy':
                lazy_loading = True
            if len(sample) < 20:
                sample.append({
                    'src': img.get('url', img.get('src', '')),
                    'alt': alt,
                    'title': img.get('title', ''),
                    'width': img.get('width', ''),
                    'height': img.get('height', ''),
                    'loading': img.get('loading', ''),
                    'srcset': img.get('srcset', ''),
                    'sizes': img.get('sizes', ''),
                    'file_size': 0,
                })
        return {
            'total_count': total_count,
            'without_alt': without_alt,
            'with_alt': total_count - without_alt,
            'lazy_loading': lazy_loading,
            'sample': sample,
            'has_alt_text': without_alt == 0,
        }


    def _build_headings_summary(self, headings: list) -> dict:
        """Transform raw parsed headings list into the dict structure that rules expect."""
        result = {'h' + str(i): [] for i in range(1, 7)}
        result['heading_stats'] = {'is_sequential': True, 'max_level': 0, 'heading_count': 0}
        for h in headings:
            if not isinstance(h, dict):
                continue
            level = h.get('level', 0)
            text = h.get('text', '')
            if 1 <= level <= 6:
                result['h' + str(level)].append(text)
            result['heading_stats']['heading_count'] += 1
            if level > result['heading_stats']['max_level']:
                result['heading_stats']['max_level'] = level
        return result


    def _build_structured_data(self, schemas: list) -> dict:
        """Wrap schemas list into the structured_data dict that rules expect."""
        schema_markup = []
        for schema in schemas:
            if isinstance(schema, dict):
                parsed_val = schema.get('parsed', schema.get('raw', {}))
                if isinstance(parsed_val, dict):
                    schema_markup.append(parsed_val)
                else:
                    type_val = schema.get('types', [])
                    type_name = type_val[0] if type_val else 'Unknown'
                    schema_markup.append({'@type': str(type_name)})
            else:
                schema_markup.append({'@type': str(schema)})
        return {
            'schema_markup': schema_markup,
            'schema_count': len(schema_markup),
            'formats': list(set(s.get('format', '') for s in schemas if isinstance(s, dict))),
        }


    def _create_error_result(
        self,
        rule: BaseRule,
        page_id: UUID,
        message: str,
    ) -> RuleResult:
        """Create a synthetic RuleResult for a rule that failed to evaluate."""
        return RuleResult(
            rule_id=rule.rule_id,
            name=rule.name,
            category=rule.category,
            severity=Severity.ERROR,
            passed=False,
            score_impact=0,
            message=message,
            recommendation="Check rule implementation for data mismatch or missing fields",
            data={"page_id": str(page_id)},
            tags=rule.tags if hasattr(rule, "tags") else [],
        )
