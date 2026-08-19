"""
Unified Audit Response Builder.

Single source of truth for the audit response JSON shape. Consolidates the
previously-duplicated assembly logic that lived in AnalysisScorerService,
response_builder.build_per_page_breakdown, and the three audit endpoints.

Pipeline inside this builder:
    RuleEvaluationResult rows (DB)
        -> reconstruct RuleResult[] (per page, homepage weighted)
        -> ScoreCalculator (overall_score / grade / per-category score)
        -> RuleResultToSEOIssueConverter (SEOIssue[] with page_url + affected_part)
        -> assemble unified {audit, summary, categories, issues, ...} dict

The crawler/parser evidence is already persisted (parsed_page_facts, page_seo_data,
page_network_data, crawl_pages); this builder only *reads* it — it never scrapes.
Metrics that the pipeline does not measure are reported with
{available: false, value: null, reason: ...} rather than misleading zeros.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.audit.repositories.parsed_page_fact_repository import (
    ParsedPageFactRepository,
)
from app.modules.audit.repositories.rule_evaluation_repository import (
    RuleEvaluationResultRepository,
)
from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
from app.modules.crawler.repositories.page_seo_data_repository import (
    PageSEODataRepository,
)
from app.modules.rule_engine.models.rule_evidence_map import (
    CATEGORY_DISPLAY,
    CHECK_KEY_TO_RULE_IDS,
    RECOMMENDATIONS,
    RULE_TITLES,
    SUBCATEGORY_NOT_AVAILABLE,
    SUBCATEGORY_OF,
)
from app.modules.rule_engine.models.rule_result import RuleResult, Severity
from app.modules.rule_engine.models.seo_issue import SEOIssue, SeverityTier
from app.modules.rule_engine.services.issue_factory import (
    RuleResultToSEOIssueConverter,
)
from app.modules.scorer.services.score_calculator import (
    ScoreCalculator,
    get_status,
    PASS_THRESHOLD,
)

logger = logging.getLogger(__name__)


class AuditResponseBuilder:
    """Assembles the unified audit response from persisted DB rows."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.crawl_job_repo = CrawlJobRepository(db)
        self.crawl_page_repo = CrawlPageRepository(db)
        self.parsed_fact_repo = ParsedPageFactRepository(db)
        self.rule_eval_repo = RuleEvaluationResultRepository(db)
        self.seo_repo = PageSEODataRepository(db)
        self.calculator = ScoreCalculator()
        self.converter = RuleResultToSEOIssueConverter()

    async def build(
        self,
        project_id: UUID,
        crawl_id: UUID,
        eval_errors: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Build the complete unified audit response.

        Args:
            project_id: project tracking key.
            crawl_id: crawl job ID.
            eval_errors: optional list of {page_id, url, error} dicts from the
                evaluation stage (synthetic ERROR rule results are also read
                from DB and included).

        Returns:
            Unified audit response dict matching audit_response_schemas.UnifiedAuditResponse.
        """
        logger.info(
            "AuditResponseBuilder.build: project_id=%s crawl_id=%s", project_id, crawl_id
        )

        crawl_job = await self.crawl_job_repo.get_by_id(crawl_id)
        domain = crawl_job.domain if crawl_job else ""
        project_id = _coerce_uuid(project_id)
        crawl_id = _coerce_uuid(crawl_id)

        # --- Crawl pages (URL map, status, depth, counts) ---
        crawl_pages = await self.crawl_page_repo.get_by_crawl_id(crawl_id)
        page_url_map: Dict[UUID, str] = {}
        homepage_ids: set = set()
        status_code_counts: Dict[str, int] = defaultdict(int)
        crawl_redirects = 0
        broken_pages = 0
        crawl_errors = 0
        for p in crawl_pages:
            page_url_map[p.id] = p.url or p.normalized_url
            if p.depth == 0:
                homepage_ids.add(p.id)
            if p.status_code:
                status_code_counts[str(p.status_code)] += 1
            if p.is_error:
                broken_pages += 1
            if p.is_redirect:
                crawl_redirects += 1
            if not p.is_success and not p.is_redirect:
                crawl_errors += 1

        pages_crawled = len([p for p in crawl_pages if p.is_crawled])
        pages_discovered = len(crawl_pages)

        # --- Parsed facts (per-page content/image/schema/link signals) ---
        parsed_facts = await self.parsed_fact_repo.get_by_crawl_id(crawl_id)
        parsed_facts = [f for f in parsed_facts if str(f.project_id) == str(project_id)]

        # --- Rule evaluation results ---
        eval_rows = await self.rule_eval_repo.get_by_project_id(project_id)
        eval_rows = [r for r in eval_rows if str(r.crawl_id) == str(crawl_id)]

        # Index eval errors (synthetic ERROR rows + caller-supplied)
        all_errors: List[Dict[str, Any]] = list(eval_errors or [])
        for er in eval_rows:
            if er.severity == Severity.ERROR.value:
                all_errors.append({
                    "rule_id": er.rule_id,
                    "page_id": str(er.page_id),
                    "url": page_url_map.get(er.page_id, str(er.page_id)),
                    "error": er.message,
                })

        # --- Canonical page ingestion (Section 1) -----------------------------
        # Collapse www / non-www + trailing-slash variants of the same logical
        # page into ONE canonical page so issues are never duplicated across the
        # two host variants. If both variants are crawled as separate pages
        # (neither redirects to the other), emit ONE site-level
        # missing_www_redirect issue instead of duplicating every check.
        canonical_of_page: Dict[UUID, str] = {}
        canonical_groups: Dict[str, List[UUID]] = defaultdict(list)
        canonical_url: Dict[str, str] = {}
        www_roots: set = set()
        nonwww_roots: set = set()
        for p in crawl_pages:
            url = p.url or p.normalized_url or ""
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            if not host:
                continue
            host_nw = host[4:] if host.startswith("www.") else host
            if host.startswith("www."):
                www_roots.add(host_nw)
            else:
                nonwww_roots.add(host_nw)
            path = parsed.path or "/"
            if path != "/" and path.endswith("/"):
                path = path.rstrip("/")
            key = f"{host_nw}{path}"
            canonical_of_page[p.id] = key
            if key not in canonical_url:
                canonical_url[key] = url
            canonical_groups[key].append(p.id)

        www_redirect_issue: Optional[SEOIssue] = None
        if www_roots & nonwww_roots:
            # Both www and non-www crawled for the same root -> one advisory issue.
            all_errors.append({
                "rule_id": "missing_www_redirect", "page_id": "",
                "url": "", "error": "Both www and non-www host variants resolve",
            })
            www_redirect_issue = SEOIssue(
                rule_id="missing_www_redirect",
                severity=SeverityTier.MEDIUM,
                category="technical",
                status="failed",
                page_url=domain or "",
                affected_part="canonical",
                evidence={"www_and_nonwww": sorted(www_roots & nonwww_roots)},
                score_impact=0.0,
                message=(
                    "Both www and non-www host variants resolve without a single "
                    "canonical redirect; pick one and 301-redirect the other."
                ),
                recommendation=(
                    "Choose one canonical host (www or non-www) and 301-redirect the other."
                ),
                page_id=None, crawl_id=str(crawl_id), project_id=str(project_id),
            )

        # Dedupe parsed_facts to one per canonical page so top-level link/image/
        # schema counts reflect the deduped page set (Section 5).
        _seen_canon = set()
        canonical_parsed_facts: List = []
        for f in parsed_facts:
            ck = canonical_of_page.get(f.page_id, str(f.page_id))
            if ck in _seen_canon:
                continue
            _seen_canon.add(ck)
            canonical_parsed_facts.append(f)

        # Group rule results by canonical page (merge underlying page_ids).
        # Within a canonical page, keep ONE result per rule_id (worst verdict wins)
        # so the same check is never duplicated when www + non-www resolve to the
        # same logical page (Section 1).
        canonical_results: Dict[str, Dict[str, RuleResult]] = defaultdict(dict)
        for er in eval_rows:
            if er.severity == Severity.ERROR.value:
                continue  # errors excluded from scoring/issues
            key = canonical_of_page.get(er.page_id, str(er.page_id))
            rule_id = er.rule_id
            new_rr = RuleResult(
                rule_id=rule_id,
                name=er.rule_name,
                category=er.category,
                severity=Severity(er.severity),
                passed=er.passed,
                score_impact=er.score_impact,
                message=er.message,
                recommendation=er.recommendation,
                data=er.rule_data,
                tags=er.tags or [],
            )
            existing = canonical_results[key].get(rule_id)
            if existing is None or (not new_rr.passed and existing.passed):
                canonical_results[key][rule_id] = new_rr
        canonical_results: Dict[str, List[RuleResult]] = {
            k: list(v.values()) for k, v in canonical_results.items()
        }

        total_pages_analyzed = len(canonical_groups)

        # --- Shared check-result cache (Section 2) ----------------------------
        # ONE canonical verdict per (canonical page, check_key). check_key is the
        # subcategory a rule rolls up into (SUBCATEGORY_OF). Multiple rules may map
        # to the same check_key; the worst (failed) verdict wins so the same check
        # can never contradict itself across categories.
        check_cache: Dict[str, Dict[str, bool]] = defaultdict(dict)
        check_rule_ids: Dict[str, set] = defaultdict(set)
        check_cats: Dict[str, set] = defaultdict(set)
        cat_checks: Dict[str, set] = defaultdict(set)
        for key, results in canonical_results.items():
            for r in results:
                sub = SUBCATEGORY_OF.get(r.rule_id, r.rule_id)
                existing = check_cache[key].get(sub)
                if existing is None or not r.passed:
                    check_cache[key][sub] = bool(r.passed)
                check_rule_ids[sub].add(r.rule_id)
                check_cats[sub].add(r.category)
                cat_checks[r.category].add(sub)

        # --- Per-page scoring (homepage weighted 2x) --------------------------
        per_page_scores: List[Dict[str, Any]] = []
        for key, results in canonical_results.items():
            scorable = [r for r in results if r.severity != Severity.ERROR]
            url = canonical_url.get(key, key)
            if scorable:
                page_score = self.calculator.calculate_score(scorable)
            else:
                page_score = {
                    "overall_score": 0.0,
                    "grade": "F",
                    "total_passed": 0,
                    "total_failed": len(results),
                    "critical_issues": 0,
                }
            weight = 2.0 if any(pid in homepage_ids for pid in canonical_groups[key]) else 1.0
            per_page_scores.append({
                "page_id": key,
                "url": url,
                "overall_score": page_score.get("overall_score", 0.0),
                "grade": page_score.get("grade", "F"),
                "weight": weight,
                "results": results,
            })

        # --- Project-level aggregate score ---
        if per_page_scores:
            total_weight = sum(p["weight"] for p in per_page_scores)
            weighted = sum(p["overall_score"] * p["weight"] for p in per_page_scores)
            overall_score = round(weighted / total_weight, 1) if total_weight else 0.0
        else:
            overall_score = 0.0
        grade = self.calculator._get_grade(overall_score)

        # --- Build SEOIssue[] via the centralized converter ---
        all_seo_issues: List[SEOIssue] = []
        for p in per_page_scores:
            for rr in p["results"]:
                issue = self.converter.from_rule_result(
                    rr, page_url=p["url"],
                    page_id=p["page_id"], crawl_id=str(crawl_id),
                    project_id=str(project_id),
                )
                if issue is not None:
                    all_seo_issues.append(issue)
        if www_redirect_issue is not None:
            all_seo_issues.append(www_redirect_issue)

        # --- Assemble sections ---
        summary = self._build_summary(overall_score, all_seo_issues)
        categories = self._build_categories(
            all_seo_issues, cat_checks, check_cache, total_pages_analyzed
        )
        issues = self._build_issues(all_seo_issues)
        category_results = self._build_category_results(
            all_seo_issues, check_cache, total_pages_analyzed
        )
        crawl = await self._build_crawl_section(
            crawl_job, pages_discovered, pages_crawled, total_pages_analyzed,
            status_code_counts, crawl_redirects, broken_pages, crawl_errors,
        )
        indexation = await self._build_indexation(crawl_pages, canonical_parsed_facts)
        performance = await self._build_performance(canonical_parsed_facts)
        structured_data = self._build_structured_data(canonical_parsed_facts)
        links = await self._build_links(canonical_parsed_facts)
        images = self._build_images(canonical_parsed_facts)
        content = self._build_content(canonical_parsed_facts)
        priorities = self._build_priorities(all_seo_issues)
        recommendations = self._build_recommendations(all_seo_issues)
        external_deps = self._build_external_dependencies()
        errors = all_errors
        metadata = self._build_metadata(
            total_issues=len([i for i in all_seo_issues if i.status == "failed"]),
            total_rules_evaluated=sum(len(p["results"]) for p in per_page_scores),
        )
        audit = self._build_audit_block(
            crawl_job, crawl_id, project_id,
            pages_discovered, pages_crawled, total_pages_analyzed,
        )

        return {
            "audit": audit,
            "summary": summary,
            "categories": categories,
            "issues": issues,
            "category_results": category_results,
            "crawl": crawl,
            "indexation": indexation,
            "performance": performance,
            "structured_data": structured_data,
            "links": links,
            "images": images,
            "content": content,
            "priorities": priorities,
            "recommendations": recommendations,
            "external_dependencies": external_deps,
            "errors": errors,
            "metadata": metadata,
        }

    # ------------------------------------------------------------------ summary
    def _build_summary(
        self,
        overall_score: float,
        all_seo_issues: List[SEOIssue],
    ) -> Dict[str, Any]:
        failed = [i for i in all_seo_issues if i.status == "failed"]
        passed = [i for i in all_seo_issues if i.status == "passed"]
        tier_counts = {t.value: 0 for t in SeverityTier}
        for i in failed:
            tier_counts[i.severity.value] += 1

        return {
            "overall_score": overall_score,
            "health": get_status(overall_score),
            "critical_issues": tier_counts["critical"],
            "high_issues": tier_counts["high"],
            "medium_issues": tier_counts["medium"],
            "low_issues": tier_counts["low"],
            "passed_checks": len(passed),
            "failed_checks": len(failed),
        }

    # ------------------------------------------------------------------ categories
    def _build_categories(
        self,
        all_seo_issues: List[SEOIssue],
        cat_checks: Dict[str, set],
        check_cache: Dict[str, Dict[str, bool]],
        total_pages: int,
    ) -> List[Dict[str, Any]]:
        # Per check_key: pass-rate across canonical pages (Section 3).
        #   check_score = 100 * pages_passing / total_pages_checked
        #   checks_passed = #checks with check_score >= PASS_THRESHOLD
        # categories[].issues carries that category's failed issues (Section 8);
        # the key is omitted entirely when a category has no failures.
        issues_by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for i in all_seo_issues:
            if i.status == "failed":
                issues_by_cat[i.category].append({
                    "rule_id": i.rule_id,
                    "severity": i.severity.value,
                    "message": i.message or i.affected_part,
                    "page_url": i.page_url,
                    "affected_part": i.affected_part,
                })

        out: List[Dict[str, Any]] = []
        for cat, display in CATEGORY_DISPLAY.items():
            checks = cat_checks.get(cat, set())
            checks_total = len(checks)
            check_scores: List[float] = []
            checks_passed = 0
            for sub in checks:
                passed_pages = sum(
                    1 for ck in check_cache
                    if check_cache[ck].get(sub) is not False
                )
                check_score = round(100.0 * passed_pages / total_pages, 1) if total_pages else 0.0
                check_scores.append(check_score)
                if check_score >= PASS_THRESHOLD:
                    checks_passed += 1
            checks_failed = checks_total - checks_passed
            # Invariant (Section 3): every category satisfies
            #   checks_total == checks_passed + checks_failed
            category_score = round(sum(check_scores) / len(check_scores), 1) if check_scores else 0.0
            entry: Dict[str, Any] = {
                "id": display["id"],
                "name": display["name"],
                "score": category_score,
                "status": get_status(category_score),
                "checks_total": checks_total,
                "checks_passed": checks_passed,
                "checks_failed": checks_failed,
            }
            cat_issues = issues_by_cat.get(cat)
            if cat_issues:
                entry["issues"] = cat_issues
            out.append(entry)
        return out

    # ------------------------------------------------------------------ issues
    def _build_issues(self, all_seo_issues: List[SEOIssue]) -> List[Dict[str, Any]]:
        # One entry per failed issue, carrying the rule_id scheme (Section 6) so
        # every entry is traceable to recommendations[] / priorities{}.
        return [
            {
                "rule_id": i.rule_id,
                "severity": i.severity.value,
                "message": i.message or i.affected_part,
                "page_url": i.page_url,
                "affected_part": i.affected_part,
            }
            for i in all_seo_issues
            if i.status == "failed"
        ]

    # ---------------------------------------------------------- category_results
    def _build_category_results(
        self,
        all_seo_issues: List[SEOIssue],
        check_cache: Dict[str, Dict[str, bool]],
        total_pages: int,
    ) -> Dict[str, Any]:
        # Affected (failed) canonical pages per subcheck, derived from the shared
        # check-result cache (Section 5) — the same source the categories use.
        subcat_failed: Dict[str, set] = defaultdict(set)
        for ck, subs in check_cache.items():
            for sub, passed in subs.items():
                if not passed:
                    subcat_failed[sub].add(ck)

        result: Dict[str, Any] = {}
        # Ensure every response category appears, even with no failures
        for cat, display in CATEGORY_DISPLAY.items():
            resp_id = display["id"]
            result[resp_id] = self._build_subchecks(resp_id, subcat_failed, total_pages)
        return result

    def _build_subchecks(
        self,
        resp_category_id: str,
        subcat_failed: Dict[str, set],
        total_pages: int,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        # Known sub-checks derived from SUBCATEGORY_OF values for rules in this category
        subcheck_ids = _subcategories_for_response_category(resp_category_id)
        for sub in subcheck_ids:
            if sub in SUBCATEGORY_NOT_AVAILABLE:
                out[sub] = _unavailable("check_not_implemented")
                continue
            affected_pages = len(subcat_failed.get(sub, set()))
            if total_pages > 0:
                score = round(100.0 * (total_pages - affected_pages) / total_pages, 1)
                status = get_status(score)
            else:
                score = None
                status = "not_available"
            out[sub] = {
                "status": status,
                "score": score,
                "affected_pages": affected_pages,
            }
        return out

    # ------------------------------------------------------------- crawl stats
    async def _build_crawl_section(
        self,
        crawl_job,
        pages_discovered: int,
        pages_crawled: int,
        pages_analyzed: int,
        status_code_counts: Dict[str, int],
        redirect_count: int,
        broken_pages: int,
        crawl_errors: int,
    ) -> Dict[str, Any]:
        started_at = _iso(crawl_job.created_at) if crawl_job else None
        completed_at = _iso(crawl_job.completed_at) if crawl_job else None
        return {
            "pages_discovered": pages_discovered,
            "pages_crawled": pages_crawled,
            "pages_analyzed": pages_analyzed,
            "blocked_by_robots": _unavailable("robots_txt_rules_not_analyzed"),
            "redirects": redirect_count,
            "broken_pages": broken_pages,
            "orphan_pages": _unavailable("link_graph_analysis_not_implemented"),
            "crawl_errors": crawl_errors,
            "status_codes": dict(status_code_counts),
            "started_at": started_at,
            "completed_at": completed_at,
        }

    # ---------------------------------------------------------- indexation
    async def _build_indexation(
        self, crawl_pages: List, parsed_facts: List
    ) -> Dict[str, Any]:
        noindex_pages: set = set()
        canonical_pages: set = set()
        for p in crawl_pages:
            seo = await self.seo_repo.get_by_page_id(p.id)
            if seo is None:
                continue
            robots = (seo.robots_meta or "").lower()
            if "noindex" in robots:
                noindex_pages.add(p.id)
            if seo.canonical:
                canonical_pages.add(p.id)
        total = len(crawl_pages)
        indexable = total - len(noindex_pages)
        return {
            "indexable": indexable,
            "noindex": len(noindex_pages),
            "canonicalized": len(canonical_pages),
            "blocked_by_robots": _unavailable("robots_txt_rules_not_analyzed"),
            "not_indexable": len(noindex_pages),
        }
    async def _build_performance(self, parsed_facts: List) -> Dict[str, Any]:
        ttfb_ms_values = []
        for fact in parsed_facts:
            page_facts = fact.page_facts or {}
            rt = page_facts.get("response_time_ms")
            if rt and rt > 0:
                ttfb_ms_values.append(rt)
        ttfb_value = (
            round(sum(ttfb_ms_values) / len(ttfb_ms_values), 1) if ttfb_ms_values else None
        )
        ttfb = {
            "available": ttfb_value is not None,
            "value": ttfb_value,
            "unit": "milliseconds",
                "status": get_status(_ttbf_bucket(ttfb_value)) if ttfb_value else "unknown",
            "reason": None if ttfb_value else "response_time_ms_not_available",
        }
        return {
            "available": ttfb_value is not None,
            "core_web_vitals": _unavailable("browser_performance_measurement_not_available"),
            "ttfb": ttfb,
        }

    # --------------------------------------------------------- structured_data
    def _build_structured_data(self, parsed_facts: List) -> Dict[str, Any]:
        type_counts: Dict[str, int] = defaultdict(int)
        with_schema = 0
        without_schema = 0
        valid = 0
        invalid = 0
        for fact in parsed_facts:
            parsed_data = fact.parsed_data or {}
            schemas = parsed_data.get("schemas", []) or []
            if schemas:
                with_schema += 1
                valid += len(schemas)  # parsed OK → treat as valid instances
            else:
                without_schema += 1
                invalid += 1  # no schema present = invalid for this check
            for s in schemas:
                t = None
                if isinstance(s, dict):
                    t = s.get("type") or s.get("@type")
                    if not t and isinstance(s.get("types"), list) and s["types"]:
                        t = s["types"][0]
                    if not t and isinstance(s.get("parsed"), dict):
                        t = s["parsed"].get("@type") or s["parsed"].get("type")
                if t:
                    type_counts[str(t)] += 1
        return {
            "pages_with_schema": with_schema,
            "pages_without_schema": without_schema,
            "valid": valid,
            "invalid": invalid,
            "types": dict(type_counts),
        }

    # ------------------------------------------------------------------- links
    async def _build_links(self, parsed_facts: List) -> Dict[str, Any]:
        internal = 0
        external = 0
        total = 0
        for fact in parsed_facts:
            parsed_data = fact.parsed_data or {}
            links = parsed_data.get("links") or {}
            if isinstance(links, dict):
                # rule_evaluator stores a summary: {internal_count, external_count, total_links}
                internal += int(links.get("internal_count", 0) or 0)
                external += int(links.get("external_count", 0) or 0)
                total += int(links.get("total_links", 0) or 0)
            elif isinstance(links, list):
                for link in links:
                    if not isinstance(link, dict):
                        continue
                    total += 1
                    is_ext = (
                        link.get("link_type") == "external"
                        or link.get("is_external", False)
                    )
                    if is_ext:
                        external += 1
                    else:
                        internal += 1
        return {
            "internal": {"total": internal, "broken": _unavailable("live_link_check_not_enabled")},
            "external": {"total": external, "broken": _unavailable("live_link_check_not_enabled")},
            "orphan_pages": _unavailable("link_graph_analysis_not_implemented"),
            "total_links": total,
        }

    # ------------------------------------------------------------------ images
    def _build_images(self, parsed_facts: List) -> Dict[str, Any]:
        total = 0
        missing_alt = 0
        empty_alt = 0
        missing_dimensions = 0
        oversized = 0
        modern_format = 0
        lazy_loading = 0
        for fact in parsed_facts:
            parsed_data = fact.parsed_data or {}
            images = parsed_data.get("images") or {}
            if isinstance(images, dict):
                # rule_evaluator stores a summary: {total_count, without_alt, sample:[...]}
                total += int(images.get("total_count", 0) or 0)
                missing_alt += int(images.get("without_alt", 0) or 0)
                for img in images.get("sample", []) or []:
                    if not isinstance(img, dict):
                        continue
                    if not img.get("width") and not img.get("height"):
                        missing_dimensions += 1
                    fmt = (img.get("format") or img.get("url", "") or "").lower()
                    if any(ext in fmt for ext in (".webp", ".avif", ".heic")):
                        modern_format += 1
                    if (img.get("loading") or "").strip().lower() == "lazy":
                        lazy_loading += 1
                    size = img.get("file_size") or 0
                    if isinstance(size, (int, float)) and size > 100 * 1024:
                        oversized += 1
            elif isinstance(images, list):
                for img in images:
                    if not isinstance(img, dict):
                        continue
                    total += 1
                    alt = img.get("alt", "")
                    if not alt or (isinstance(alt, str) and not alt.strip()):
                        missing_alt += 1
                    elif isinstance(alt, str) and alt.strip() == "":
                        empty_alt += 1
                    if not img.get("width") and not img.get("height"):
                        missing_dimensions += 1
                    fmt = (img.get("format") or img.get("url", "") or "").lower()
                    if any(ext in fmt for ext in (".webp", ".avif", ".heic")):
                        modern_format += 1
                    if (img.get("loading") or "").strip().lower() == "lazy":
                        lazy_loading += 1
                    size = img.get("file_size") or 0
                    if isinstance(size, (int, float)) and size > 100 * 1024:
                        oversized += 1
        return {
            "total": total,
            "missing_alt": missing_alt,
            "empty_alt": empty_alt,
            "missing_dimensions": missing_dimensions,
            "oversized": oversized,
            "modern_format": modern_format,
            "lazy_loading": lazy_loading,
        }

    # ------------------------------------------------------------------ content
    def _build_content(self, parsed_facts: List) -> Dict[str, Any]:
        thin_pages = 0
        content_hashes: Dict[str, int] = defaultdict(int)
        for fact in parsed_facts:
            page_facts = fact.page_facts or {}
            word_count = page_facts.get("word_count", 0) or 0
            if word_count < 300:
                thin_pages += 1
            h = page_facts.get("content_hash")
            if h:
                content_hashes[h] += 1
        # duplicate_pages = number of pages that share a content_hash with >=1 other page
        duplicate_groups = [c for c in content_hashes.values() if c > 1]
        duplicate_pages = sum(duplicate_groups)
        return {
            "thin_pages": thin_pages,
            "duplicate_pages": duplicate_pages,
            "duplicate_groups": len(duplicate_groups),
            "near_duplicate_pages": _unavailable("content_similarity_analysis_not_implemented"),
            "missing_author": _unavailable("author_extraction_not_implemented"),
            "outdated_pages": _unavailable("content_freshness_tracking_not_implemented"),
        }

    # -------------------------------------------------------------- priorities
    def _build_priorities(self, all_seo_issues: List[SEOIssue]) -> Dict[str, List[str]]:
        grouped: Dict[str, set] = {t.value: set() for t in SeverityTier}
        for issue in all_seo_issues:
            if issue.status == "failed":
                grouped[issue.severity.value].add(issue.rule_id)
        return {
            "critical": sorted(grouped["critical"]),
            "high": sorted(grouped["high"]),
            "medium": sorted(grouped["medium"]),
            "low": sorted(grouped["low"]),
        }

    # ----------------------------------------------------------- recommendations
    def _build_recommendations(self, all_seo_issues: List[SEOIssue]) -> List[Dict[str, Any]]:
        affected_by_rule: Dict[str, set] = defaultdict(set)
        rule_highest_tier: Dict[str, SeverityTier] = {}
        _tier_rank = {
            SeverityTier.CRITICAL: 0, SeverityTier.HIGH: 1,
            SeverityTier.MEDIUM: 2, SeverityTier.LOW: 3,
        }
        for issue in all_seo_issues:
            if issue.status != "failed":
                continue
            affected_by_rule[issue.rule_id].add(issue.page_url)
            cur = rule_highest_tier.get(issue.rule_id)
            if cur is None or _tier_rank[issue.severity] < _tier_rank[cur]:
                rule_highest_tier[issue.rule_id] = issue.severity

        recs: List[Dict[str, Any]] = []
        for rule_id, tier in rule_highest_tier.items():
            rec = RECOMMENDATIONS.get(rule_id)
            if not rec:
                continue
            recs.append({
                "priority": _tier_priority(tier),
                "rule_id": rule_id,
                "title": RULE_TITLES.get(rule_id, rule_id),
                "action": rec["action"],
                "effort": rec["effort"],
                "affected_pages": len(affected_by_rule[rule_id]),
            })
        recs.sort(key=lambda r: r["priority"])
        return recs

    # --------------------------------------------------------- external deps
    def _build_external_dependencies(self) -> List[Dict[str, Any]]:
        return [
            {"feature": "Core Web Vitals (LCP/INP/CLS)", "status": "not_available",
             "reason": "browser_performance_measurement_not_available"},
            {"feature": "Backlink analysis", "status": "not_available",
             "reason": "backlink_data_provider_not_configured"},
            {"feature": "Keyword search volume / SERP data", "status": "not_available",
             "reason": "keyword_serp_data_provider_not_configured"},
            {"feature": "Google Search Console", "status": "not_available",
             "reason": "not_connected"},
        ]

    # ---------------------------------------------------------------- metadata
    def _build_metadata(self, total_issues: int, total_rules_evaluated: int) -> Dict[str, Any]:
        return {
            "crawler_version": _version("crawler"),
            "parser_version": _version("parser"),
            "rule_engine_version": "1.0.0",
            "rules_executed": total_rules_evaluated,
            "total_issues": total_issues,
            "output_shape": "unified_v1",
        }

    # --------------------------------------------------------------- audit blk
    def _build_audit_block(
        self, crawl_job, crawl_id, project_id,
        pages_discovered, pages_crawled, pages_analyzed,
    ) -> Dict[str, Any]:
        return {
            "audit_id": str(crawl_id),
            "project_id": str(project_id),
            "url": crawl_job.url if crawl_job else None,
            "domain": crawl_job.domain if crawl_job else None,
            "started_at": _iso(crawl_job.created_at) if crawl_job else None,
            "completed_at": _iso(crawl_job.completed_at) if crawl_job else None,
            "status": crawl_job.status if crawl_job else None,
            "pages_discovered": pages_discovered,
            "pages_crawled": pages_crawled,
            "pages_analyzed": pages_analyzed,
        }


# ===================================================================== helpers

def _coerce_uuid(value) -> UUID:
    """Return value as UUID if possible, else pass through."""
    from uuid import UUID
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except Exception:
        return value


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _unavailable(reason: str) -> Dict[str, Any]:
    """Spec §17/#21: never report 0 for not-measured metrics."""
    return {"available": False, "value": None, "reason": reason}


def _health_from_score(score: float) -> str:
    # Kept as a thin delegate so any legacy caller stays consistent with the
    # single authoritative status helper (Section 4).
    return get_status(score)


def _tier_priority(tier: SeverityTier) -> int:
    return {SeverityTier.CRITICAL: 1, SeverityTier.HIGH: 2,
            SeverityTier.MEDIUM: 3, SeverityTier.LOW: 4}.get(tier, 5)


def _ttbf_bucket(ttfb_ms: Optional[float]) -> float:
    """Map a TTFB to a 0-100 health score for the ttfb.status field."""
    if not ttfb_ms:
        return 0.0
    if ttfb_ms < 200:
        return 100.0
    if ttfb_ms < 500:
        return 90.0
    if ttfb_ms < 1000:
        return 70.0
    if ttfb_ms < 2000:
        return 50.0
    return 20.0


def _group_results_by_category(page_rule_results: Dict[UUID, List[RuleResult]]) -> Dict[str, List[RuleResult]]:
    out: Dict[str, List[RuleResult]] = defaultdict(list)
    for results in page_rule_results.values():
        for r in results:
            out[r.category].append(r)
    return out


def _subcategories_for_response_category(resp_category_id: str) -> List[str]:
    """All subcategory keys whose rules belong to the given response category."""
    mapping = {
        "technical_seo": {"https", "mixed_content", "ssl_certificate", "hsts",
                          "xss_protection", "security_headers", "robots_txt", "sitemap",
                          "structured_data", "viewport", "charset", "doctype",
                          "html_lang", "language"},
        "on_page": {"titles", "meta_descriptions", "h1", "headings", "meta_keywords",
                    "canonical", "robots", "open_graph", "twitter_cards"},
        "content_quality": {"word_count", "reading_time", "paragraph_structure",
                            "text_html_ratio", "keyword_density", "duplicate_content",
                            "content_freshness"},
        "internal_linking": {"internal_links", "external_links", "broken_links",
                             "anchor_text", "nofollow_links"},
        "images_media": {"image_alt_text", "image_file_size", "lazy_loading",
                         "image_dimensions", "responsive_images", "image_formats"},
        "structured_data": {"structured_data", "organization_schema", "breadcrumb_schema",
                            "article_schema", "product_schema", "json_ld_format"},
        "social": {"open_graph", "twitter_cards", "social_media_links",
                   "facebook_domain", "social_image"},
        "security_trust": {"https", "mixed_content", "security_headers",
                           "ssl_certificate", "hsts", "xss_protection"},
        "accessibility": {"image_alt_text", "language", "heading_structure", "link_text",
                          "color_contrast", "keyboard_navigation", "aria_labels",
                          "form_labels"},
        "performance": {"response_time", "html_document_size", "code_minification",
                        "resource_count", "browser_caching", "compression",
                        "total_page_size", "javascript_errors"},
    }
    # Always include crawlability sub-checks for the dedicated crawlability category
    extra = {"redirects", "robots_txt", "sitemap", "status_codes", "canonical"}
    return sorted(mapping.get(resp_category_id, set()) | (extra if resp_category_id == "crawlability" else set()))


def _version(module: str) -> str:
    """Return the package version if tracked, else 'unknown' (no fabrication)."""
    try:
        mod = __import__(f"app.modules.{module}", fromlist=[module])
        return getattr(mod, "__version__", "unknown")
    except Exception:
        return "unknown"
