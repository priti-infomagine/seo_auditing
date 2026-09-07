"""
AuditReadModelService — read-only projection layer for compact audit data.

This service is the additive counterpart of ``AuditResponseBuilder``. It
reads the same DB tables (no schema change, no migration) and produces a
much smaller response shape designed for a dashboard frontend:

    AuditOverview
        ├── audit         (id, url, status, pages, duration_ms)
        ├── summary       (score, grade, health, issue counts, check counts)
        ├── categories    (aggregate counts only — no nested issues)
        └── top_issues    (≤ 10 compact summaries, ≤ 3 sample URLs each)

The service is strictly read-only. It does not crawl, parse, evaluate
rules, score, or write. The only mutations it triggers are read-side
``flush()`` calls inside repositories (no observable effect).

Caching is intentionally NOT implemented in this cut (see plan §11). The
reserved cache key namespaces are documented at the bottom of this file.

Compatibility note:
    ``sample[].found`` in top_issues is a stringified ``rule_data['message']``
    — NOT the legacy ``current_value`` produced by the SEOIssue converter.
    Frontends needing exact parity should call the lazy evidence endpoint.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import to_iso
from app.modules.audit.repositories.audit_read_repository import AuditReadRepository
from app.modules.audit.schemas.audit_summary_schemas import (
    AuditMeta,
    AuditOverview,
    AuditSummary,
    CategorySummary,
    CheckCounts,
    IssuePageSample,
    IssueTierCounts,
    PagesBlock,
    TopIssueSummary,
)
from app.modules.audit.schemas.issue_detail_schemas import (
    AffectedSummary,
    EvidenceImage,
    EvidenceItem,
    EvidenceLink,
    IssueDetailResponse,
    IssueEvidenceResponse,
    IssueListResponse,
    IssuePageRow,
    IssuePagesResponse,
    PageDetailResponse,
    RuleMeta,
)
from app.modules.rule_engine.models.rule_evidence_map import (
    CATEGORY_DISPLAY,
    RECOMMENDATIONS,
    RULE_TITLES,
)
from app.modules.scorer.services.score_calculator import get_status

logger = logging.getLogger(__name__)


class AuditReadModelService:
    """Compact read-only projection of an audit's persisted data."""

    MAX_TOP_ISSUES: int = 10
    MAX_ISSUE_SAMPLES: int = 3
    DEFAULT_PAGE_LIMIT: int = 20
    MAX_PAGE_LIMIT: int = 100
    EVIDENCE_DEFAULT_LIMIT: int = 25
    EVIDENCE_MAX_LIMIT: int = 100

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AuditReadRepository(db)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _derive_issue_id(crawl_id: UUID, rule_id: str) -> str:
        return f"{crawl_id}:{rule_id}"

    @staticmethod
    def _parse_issue_id(issue_id: str) -> str:
        """Return the rule_id component of an issue id.

        ``issue_id`` is the opaque string ``f"{crawl_id}:{rule_id}"``. We split
        on the FIRST colon so rule_ids containing a colon are preserved.
        """
        if ":" not in issue_id:
            return issue_id
        return issue_id.split(":", 1)[1]

    @staticmethod
    def _impact_tier(score_impact: float) -> str:
        """Derive a human impact tier from the absolute score impact.

        Mirrors the impact tier logic used in ``report_assembler.py``:
            |impact| >= 15  -> high
            |impact| >= 8   -> medium
            otherwise        -> low
        """
        a = abs(float(score_impact or 0.0))
        if a >= 15:
            return "high"
        if a >= 8:
            return "medium"
        return "low"

    @staticmethod
    def _severity_rank(sev: str) -> int:
        return {
            "critical": 1, "high": 2, "medium": 3, "low": 4,
        }.get((sev or "").lower(), 5)

    @staticmethod
    def _impact_rank(impact: str) -> int:
        return {
            "high": 1, "medium": 2, "low": 3,
        }.get((impact or "").lower(), 4)

    def _top_issue_sort_key(self, grp: Dict[str, Any]) -> Tuple[int, int, int, str]:
        return (
            self._severity_rank(grp["severity"]),
            self._impact_rank(grp["impact"]),
            -int(grp["affected_pages"]),
            grp["rule_id"],
        )

    def _group_failed_results(
        self, failed_results: List[Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Group failed rule results by rule_id → per-rule aggregate.

        Returns ``{rule_id: {severity, impact, affected_pages, sample_urls, ...}}``.
        """
        groups: Dict[str, Dict[str, Any]] = {}
        for r in failed_results:
            rid = r.rule_id
            if rid not in groups:
                groups[rid] = {
                    "rule_id": rid,
                    "category": r.category or "unknown",
                    "severity": r.severity or "medium",
                    "impact": self._impact_tier(r.score_impact),
                    "affected_pages": 0,
                    "sample_urls": [],
                    "_seen_urls": set(),
                    "_score_impact": 0.0,
                    "_first_message": None,
                }
            g = groups[rid]
            g["affected_pages"] += 1
            # Promote the worst severity / impact within the rule
            if self._severity_rank(r.severity) < self._severity_rank(g["severity"]):
                g["severity"] = r.severity
            # Promote score_impact: keep the maximum absolute value as the impact driver
            a = abs(float(r.score_impact or 0.0))
            if a > abs(g["_score_impact"]):
                g["_score_impact"] = r.score_impact
                g["impact"] = self._impact_tier(r.score_impact)
            # Capture the first non-empty message as a sample fallback for `found`
            if g["_first_message"] is None and r.message:
                g["_first_message"] = r.message
        return groups

    @staticmethod
    def _category_display(cat: str) -> Tuple[str, str]:
        d = CATEGORY_DISPLAY.get(cat)
        if d:
            return d["id"], d["name"]
        return cat, cat.replace("_", " ").title()

    @staticmethod
    def _build_pages_block(crawl_pages: List[Any]) -> PagesBlock:
        crawled = sum(1 for p in crawl_pages if getattr(p, "is_crawled", False))
        failed = sum(1 for p in crawl_pages if getattr(p, "is_error", False))
        analyzed = len(crawl_pages) - failed
        return PagesBlock(
            crawled=crawled or len(crawl_pages),
            analyzed=analyzed if analyzed > 0 else len(crawl_pages),
            failed=failed,
        )

    @staticmethod
    def _duration_ms(crawl_job: Any) -> Optional[int]:
        if not crawl_job:
            return None
        start = getattr(crawl_job, "created_at", None)
        end = getattr(crawl_job, "completed_at", None)
        if not start or not end:
            return None
        try:
            return int((end - start).total_seconds() * 1000)
        except Exception:
            return None

    # ---------------------------------------------------------------- overview
    async def build_overview(self, audit_id: UUID) -> AuditOverview:
        """Build the compact overview for an audit (= crawl_id).

        Performs a small constant number of queries (≤ 5). Does NOT load
        per-page SEO/network/parsed data.
        """
        inputs = await self.repo.load_compact_inputs(audit_id)
        if inputs is None:
            raise LookupError(f"No analysis run for audit_id={audit_id}")

        run = inputs["analysis_run"]
        crawl_job = inputs["crawl_job"]
        crawl_pages = inputs["crawl_pages"]
        failed_results = inputs["failed_results"]

        # --- summary ---------------------------------------------------------
        overall = float(getattr(run, "overall_score", 0.0) or 0.0)
        health = get_status(overall) if overall is not None else "unknown"
        tier_counts: Dict[str, int] = defaultdict(int)
        for r in failed_results:
            tier_counts[(r.severity or "low").lower()] += 1
        total_failed = sum(tier_counts.values())
        total_passed = int(getattr(run, "total_passed", 0) or 0)
        total_failed_db = int(getattr(run, "total_failed", 0) or total_failed)
        summary = AuditSummary(
            score=overall,
            grade=getattr(run, "grade", None),
            health=health,
            issues=IssueTierCounts(
                critical=tier_counts.get("critical", 0),
                high=tier_counts.get("high", 0),
                medium=tier_counts.get("medium", 0),
                low=tier_counts.get("low", 0),
                total=total_failed,
            ),
            checks=CheckCounts(
                passed=total_passed,
                failed=total_failed_db,
                total=total_passed + total_failed_db,
            ),
        )

        # --- categories (aggregate only) -------------------------------------
        # Group tier counts by category so categories[].issues has per-cat totals.
        by_cat: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        cat_rule_counts: Dict[str, set] = defaultdict(set)
        for r in failed_results:
            by_cat[r.category or "unknown"][(r.severity or "low").lower()] += 1
            cat_rule_counts[r.category or "unknown"].add(r.rule_id)

        categories: List[CategorySummary] = []
        for cat_id, d in CATEGORY_DISPLAY.items():
            counts = by_cat.get(cat_id, {})
            failed_for_cat = sum(counts.values())
            categories.append(
                CategorySummary(
                    id=d["id"],
                    name=d["name"],
                    score=0.0,
                    status="not_available" if failed_for_cat == 0 else "needs_improvement",
                    issues=IssueTierCounts(
                        critical=counts.get("critical", 0),
                        high=counts.get("high", 0),
                        medium=counts.get("medium", 0),
                        low=counts.get("low", 0),
                        total=failed_for_cat,
                    ),
                    checks_total=len(cat_rule_counts.get(cat_id, set())),
                    checks_passed=0,
                    checks_failed=len(cat_rule_counts.get(cat_id, set())),
                )
            )

        # --- top issues -------------------------------------------------------
        groups = self._group_failed_results(failed_results)
        ordered = sorted(groups.values(), key=self._top_issue_sort_key)
        top_issues: List[TopIssueSummary] = []
        for g in ordered[: self.MAX_TOP_ISSUES]:
            sample: List[IssuePageSample] = []
            seen: set = set()
            for r in failed_results:
                if r.rule_id != g["rule_id"]:
                    continue
                url = getattr(r, "page_id", None) and None  # placeholder; we need a real url
                # We do not have a URL map here (that would require an extra
                # batched fetch of crawl_pages). For the overview, we use the
                # rule's first message as a free-form "found" signal and rely
                # on the page-id for the detail endpoint.
                if id(r) in seen:
                    continue
                seen.add(id(r))
                if len(sample) >= self.MAX_ISSUE_SAMPLES:
                    break
                sample.append(IssuePageSample(
                    url=f"page:{r.page_id}",
                    found=g["_first_message"],
                ))
            top_issues.append(
                TopIssueSummary(
                    id=self._derive_issue_id(audit_id, g["rule_id"]),
                    rule_id=g["rule_id"],
                    category=g["category"],
                    severity=g["severity"],
                    impact=g["impact"],
                    affected_pages=g["affected_pages"],
                    sample=sample,
                )
            )

        # --- audit metadata ---------------------------------------------------
        meta = AuditMeta(
            id=str(audit_id),
            url=getattr(crawl_job, "url", None) if crawl_job else None,
            status=getattr(crawl_job, "status", None) if crawl_job else None,
            pages=self._build_pages_block(crawl_pages),
            duration_ms=self._duration_ms(crawl_job),
        )

        return AuditOverview(
            audit=meta,
            summary=summary,
            categories=categories,
            top_issues=top_issues,
        )

    # ---------------------------------------------------------------- issue list
    async def build_issue_list(
        self,
        audit_id: UUID,
        *,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> IssueListResponse:
        """Paginated compact issue list."""
        project_id, crawl_id = await self.repo.resolve_audit(audit_id)
        if project_id is None:
            raise LookupError(f"No analysis run for audit_id={audit_id}")

        # Clamp pagination params silently (do not 400 on user input)
        limit = max(1, min(int(limit or 20), self.MAX_PAGE_LIMIT))
        offset = max(0, int(offset or 0))

        rows, total = await self.repo.rule_eval_repo.list_failed_by_crawl_id_paginated(
            project_id, crawl_id,
            category=category, severity=severity, status=status,
            limit=limit, offset=offset,
        )

        # Group by rule_id within the page
        by_rule: Dict[str, List[Any]] = defaultdict(list)
        for r in rows:
            by_rule[r.rule_id].append(r)

        items: List[TopIssueSummary] = []
        for rule_id, group in by_rule.items():
            # Use the worst severity in this batch
            worst = min(group, key=lambda r: self._severity_rank(r.severity))
            impact_score = max(
                (abs(float(r.score_impact or 0.0)) for r in group),
                default=0.0,
            )
            sample: List[IssuePageSample] = []
            for r in group[: self.MAX_ISSUE_SAMPLES]:
                sample.append(IssuePageSample(
                    url=f"page:{r.page_id}",
                    found=r.message,
                ))
            items.append(
                TopIssueSummary(
                    id=self._derive_issue_id(crawl_id, rule_id),
                    rule_id=rule_id,
                    category=worst.category or "unknown",
                    severity=worst.severity or "medium",
                    impact=self._impact_tier(impact_score * -1 if impact_score else 0.0)
                    if impact_score == 0.0 else self._impact_tier(-impact_score),
                    affected_pages=len(group),
                    sample=sample,
                )
            )

        # Stable sort: by severity, impact, -affected_pages, rule_id
        items.sort(key=lambda x: self._top_issue_sort_key({
            "severity": x.severity,
            "impact": x.impact,
            "affected_pages": x.affected_pages,
            "rule_id": x.rule_id,
        }))

        return IssueListResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=items,
        )

    # --------------------------------------------------------------- issue detail
    async def build_issue_detail(
        self, audit_id: UUID, issue_id: str
    ) -> IssueDetailResponse:
        """Detailed view of one issue (rule-level)."""
        project_id, crawl_id = await self.repo.resolve_audit(audit_id)
        if project_id is None:
            raise LookupError(f"No analysis run for audit_id={audit_id}")

        rule_id = self._parse_issue_id(issue_id)
        samples = await self.repo.rule_eval_repo.get_first_samples_for_rule(
            project_id, crawl_id, rule_id, n=3
        )
        if not samples:
            # Allow zero-affected: still return a skeleton
            head = None
            worst_severity = "medium"
            impact_score = 0.0
            total_affected = 0
        else:
            head = samples[0]
            worst_severity = min(
                (r.severity for r in samples),
                key=lambda s: self._severity_rank(s),
            ) if samples else "medium"
            impact_score = max(
                (abs(float(r.score_impact or 0.0)) for r in samples),
                default=0.0,
            )
            # Count actual affected pages via a single count
            _, total_affected = await self.repo.rule_eval_repo.get_failed_pages_for_rule(
                project_id, crawl_id, rule_id, limit=1, offset=0,
            )

        title = RULE_TITLES.get(rule_id, rule_id)
        rec = RECOMMENDATIONS.get(rule_id, {})
        fix_text = rec.get("action") if isinstance(rec, dict) else None

        rule_meta = RuleMeta(
            id=rule_id,
            title=title,
            description=None,
            fix=fix_text,
        )

        examples: List[IssuePageSample] = []
        for r in samples:
            examples.append(IssuePageSample(
                url=f"page:{r.page_id}",
                found=r.message,
            ))

        return IssueDetailResponse(
            id=issue_id,
            rule=rule_meta,
            severity=worst_severity,
            impact=self._impact_tier(-impact_score if impact_score else 0.0),
            affected=AffectedSummary(pages=total_affected, items=total_affected),
            fix=fix_text,
            examples=examples,
        )

    # -------------------------------------------------------------- issue pages
    async def build_issue_pages(
        self,
        audit_id: UUID,
        issue_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> IssuePagesResponse:
        """Paginated affected pages for one issue."""
        project_id, crawl_id = await self.repo.resolve_audit(audit_id)
        if project_id is None:
            raise LookupError(f"No analysis run for audit_id={audit_id}")

        rule_id = self._parse_issue_id(issue_id)
        limit = max(1, min(int(limit or self.DEFAULT_PAGE_LIMIT), self.MAX_PAGE_LIMIT))
        offset = max(0, int(offset or 0))

        rows, total = await self.repo.rule_eval_repo.get_failed_pages_for_rule(
            project_id, crawl_id, rule_id, limit=limit, offset=offset,
        )

        # Resolve a URL map for the page_ids in this batch (batched single query)
        page_ids = [r.page_id for r in rows]
        url_map: Dict[UUID, str] = {}
        if page_ids:
            page_map = await self.repo.crawl_page_repo.get_by_ids(page_ids)
            url_map = {pid: (p.url or p.normalized_url) for pid, p in page_map.items() if p}

        items: List[IssuePageRow] = []
        for r in rows:
            items.append(IssuePageRow(
                page_id=str(r.page_id),
                url=url_map.get(r.page_id, f"page:{r.page_id}"),
                found=r.message,
                status="failed",
            ))

        return IssuePagesResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=items,
        )

    # ------------------------------------------------------------ issue evidence
    async def build_issue_evidence(
        self,
        audit_id: UUID,
        issue_id: str,
        *,
        links_limit: int = 25,
        links_offset: int = 0,
        images_limit: int = 25,
        images_offset: int = 0,
    ) -> IssueEvidenceResponse:
        """Lazy-load heavy evidence for one issue (links, images, rule_data)."""
        project_id, crawl_id = await self.repo.resolve_audit(audit_id)
        if project_id is None:
            raise LookupError(f"No analysis run for audit_id={audit_id}")

        rule_id = self._parse_issue_id(issue_id)
        links_limit = max(1, min(int(links_limit or self.EVIDENCE_DEFAULT_LIMIT), self.EVIDENCE_MAX_LIMIT))
        links_offset = max(0, int(links_offset or 0))
        images_limit = max(1, min(int(images_limit or self.EVIDENCE_DEFAULT_LIMIT), self.EVIDENCE_MAX_LIMIT))
        images_offset = max(0, int(images_offset or 0))

        # Load all failed rows for this rule (cap to a reasonable upper bound so a
        # pathological rule with 100k pages does not blow memory; a full list
        # endpoint is not the goal of this endpoint).
        HARD_CAP = 1000
        rows, total = await self.repo.rule_eval_repo.get_failed_pages_for_rule(
            project_id, crawl_id, rule_id, limit=HARD_CAP, offset=0,
        )

        # Batch-load URLs for the involved pages
        page_ids = [r.page_id for r in rows]
        page_url_map: Dict[UUID, str] = {}
        if page_ids:
            page_map = await self.repo.crawl_page_repo.get_by_ids(page_ids)
            page_url_map = {
                pid: (p.url or p.normalized_url) for pid, p in page_map.items() if p
            }

        # Items: serialize the rule_data per row (small dict, no JSONB on the wire)
        items: List[EvidenceItem] = []
        for r in rows:
            url = page_url_map.get(r.page_id, f"page:{r.page_id}")
            evidence_dict: Dict[str, Any] = {}
            if isinstance(r.rule_data, dict):
                evidence_dict = r.rule_data
            items.append(EvidenceItem(
                page_id=str(r.page_id),
                url=url,
                found_value=None,
                expected_value=None,
                evidence=evidence_dict,
            ))

        # Links / images: load parsed facts in one batched query, then slice
        facts_map = await self.repo.parsed_fact_repo.get_by_page_ids(page_ids)
        all_links: List[EvidenceLink] = []
        all_images: List[EvidenceImage] = []
        for pid, fact in facts_map.items():
            page_url = page_url_map.get(pid, f"page:{pid}")
            parsed = (fact.parsed_data or {}) if fact else {}
            for link in (parsed.get("links") or []):
                if not isinstance(link, dict):
                    continue
                is_ext = (
                    link.get("link_type") == "external"
                    or link.get("is_external", False)
                    or link.get("external", False)
                )
                all_links.append(EvidenceLink(
                    page_id=str(pid),
                    url=page_url,
                    link_type="external" if is_ext else "internal",
                    href=link.get("url") or link.get("href") or "",
                    anchor=link.get("label") or link.get("text") or link.get("anchor_text"),
                    nofollow=bool(link.get("nofollow", False)),
                ))
            for img in (parsed.get("images") or []):
                if not isinstance(img, dict):
                    continue
                src = img.get("src") or img.get("url") or ""
                alt = img.get("alt")
                all_images.append(EvidenceImage(
                    page_id=str(pid),
                    url=page_url,
                    src=src,
                    alt=alt,
                    has_alt=bool(alt and alt.strip()) if isinstance(alt, str) else False,
                    width=img.get("width"),
                    height=img.get("height"),
                ))

        total_links = len(all_links)
        total_images = len(all_images)
        links_slice = all_links[links_offset: links_offset + links_limit]
        images_slice = all_images[images_offset: images_offset + images_limit]

        return IssueEvidenceResponse(
            rule_id=rule_id,
            items=items,
            links=links_slice,
            images=images_slice,
            total_links=total_links,
            total_images=total_images,
            total_items=len(items),
        )

    # ---------------------------------------------------------------- page detail
    async def build_page_detail(
        self,
        audit_id: UUID,
        page_id: UUID,
        *,
        include_facts: bool = False,
    ) -> PageDetailResponse:
        """Per-page breakdown for a single page (lazy, on demand)."""
        project_id, crawl_id = await self.repo.resolve_audit(audit_id)
        if project_id is None:
            raise LookupError(f"No analysis run for audit_id={audit_id}")

        # Page metadata (batched single-page)
        page = await self.repo.crawl_page_repo.get_by_id(page_id)
        if page is None or str(page.crawl_id) != str(crawl_id):
            raise LookupError(f"Page {page_id} not found in audit {audit_id}")

        url = page.url or page.normalized_url or ""

        # All failed rules for this page
        failed = await self.repo.rule_eval_repo.get_failed_for_page(
            project_id, crawl_id, page_id
        )
        page_issues: List[IssuePageRow] = []
        for r in failed:
            page_issues.append(IssuePageRow(
                page_id=str(page_id),
                url=url,
                found=r.message,
                status="failed",
            ))

        facts: Optional[Dict[str, Any]] = None
        if include_facts:
            parsed_fact = await self.repo.parsed_fact_repo.get_by_page_id(
                project_id, page_id
            )
            seo = await self.repo.seo_repo.get_by_page_id(page_id)
            network = await self.repo.network_repo.get_by_page_id(page_id)
            facts = {
                "parsed": (parsed_fact.parsed_data if parsed_fact else None),
                "page_facts": (parsed_fact.page_facts if parsed_fact else None),
                "elements": (parsed_fact.elements if parsed_fact else None),
                "attributes": (parsed_fact.attributes if parsed_fact else None),
                "seo": {
                    "title": getattr(seo, "title", None) if seo else None,
                    "meta_description": getattr(seo, "meta_description", None) if seo else None,
                    "word_count": getattr(seo, "word_count", None) if seo else None,
                    "language": getattr(seo, "language", None) if seo else None,
                    "canonical": getattr(seo, "canonical", None) if seo else None,
                    "headings": getattr(seo, "headings", None) if seo else None,
                    "robots_meta": getattr(seo, "robots_meta", None) if seo else None,
                } if seo else None,
                "network": {
                    "status_code": getattr(network, "status_code", None) if network else None,
                    "response_time_ms": getattr(network, "response_time_ms", None) if network else None,
                    "headers": getattr(network, "headers", None) if network else None,
                    "redirects": getattr(network, "redirects", None) if network else None,
                } if network else None,
            }

        return PageDetailResponse(
            page_id=str(page_id),
            url=url,
            status=page.status_code,
            score=None,  # intentionally None: per-page score requires scoring recompute; not exposed
            grade=None,
            issues=page_issues,
            facts=facts,
        )


# Reserved cache key namespaces (NOT USED IN THIS PR — placeholder for a
# follow-up caching layer that must be opt-in and use a separate Redis client
# from the Celery broker/backend):
#   audit:overview:{audit_id}
#   audit:issues:{audit_id}:{filter_hash}:{offset}:{limit}
#   audit:issue:{audit_id}:{issue_id}
#   audit:issue_pages:{audit_id}:{issue_id}:{offset}:{limit}
#   audit:issue_evidence:{audit_id}:{issue_id}
#   audit:page:{audit_id}:{page_id}
