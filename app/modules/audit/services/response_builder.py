"""
Response Builder — shared per-page audit response builder.

Factors out the per-page grouping logic that was previously inline in
`results.py::get_analysis_result` and `analyze.py` Step 9, so both
endpoints produce a consistent per-page breakdown.

Each per-page entry includes:
  - page_id, url (resolved via CrawlPage join)
  - Per-page score + grade (via ScoreCalculator)
  - rule_results (each with page_url and page_id)
  - crawl_details (from CrawlPage)
  - parsed_info (from PageSEOData)
  - links_analysis (filtered views over a single links list)
"""
from collections import defaultdict
from typing import Dict, Any, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.modules.audit.repositories.parsed_page_fact_repository import ParsedPageFactRepository
from app.modules.audit.repositories.rule_evaluation_repository import RuleEvaluationResultRepository
from app.modules.crawler.repositories.crawl_page_repository import CrawlPageRepository
from app.modules.crawler.repositories.page_seo_data_repository import PageSEODataRepository
from app.modules.crawler.repositories.page_network_data_repository import PageNetworkDataRepository
from app.modules.rule_engine.models.rule_result import RuleResult as RR, Severity
from app.modules.scorer.services.score_calculator import ScoreCalculator


def _summarize_rule_result(rr: Any, page_id: str, page_url: str) -> Dict[str, Any]:
    """Convert an ORM rule result row to a dict, attaching page context."""
    return {
        "rule_id": rr.rule_id,
        "name": rr.rule_name,
        "category": rr.category,
        "severity": rr.severity,
        "passed": rr.passed,
        "score_impact": rr.score_impact,
        "message": rr.message,
        "recommendation": rr.recommendation,
        "data": rr.rule_data,
        "tags": rr.tags or [],
        "page_url": page_url,
        "page_id": page_id,
    }


def _build_links_analysis(parsed_links: List[Dict[str, Any]], page_url: str) -> Dict[str, Any]:
    """
    Build links_analysis as filtered views over a single stored list.

    Instead of three separate arrays (total_links, external_links, internal_links)
    holding the same objects, we store one ``links`` array and provide
    counts + a ``related_issues`` slot for future use.
    """
    internal_count = 0
    external_count = 0

    links = []
    for link in parsed_links:
        if not isinstance(link, dict):
            continue
        is_external = (
            link.get("external", False)
            or link.get("link_type", "") == "external"
        )
        if is_external:
            external_count += 1
        else:
            internal_count += 1

        links.append({
            "page_url": page_url,
            "url": link.get("url", link.get("href", "")),
            "label": link.get("label", link.get("text", "")),
            "link_type": link.get("link_type", "internal" if not is_external else "external"),
            "external": is_external,
            "nofollow": link.get("nofollow", False),
            "anchor_text": link.get("label", link.get("text", "")),
        })

    return {
        "total_count": len(links),
        "internal_count": internal_count,
        "external_count": external_count,
        "links": links,
    }


async def build_per_page_breakdown(
    db: AsyncSession,
    project_id: UUID,
    crawl_id: UUID,
) -> List[Dict[str, Any]]:
    """
    Build a per-page audit breakdown from DB rows.

    Groups ``RuleEvaluationResult`` rows by ``page_id``, resolves each
    page's URL via a join to ``CrawlPage``, computes per-page scores
    via ``ScoreCalculator``, and attaches crawl details, parsed SEO
    info, and links analysis.

    Used by both ``analyze.py`` (post-crawl response) and
    ``results.py`` (GET /audit/result/{crawl_id}).

    Args:
        db: Async database session.
        project_id: Project tracking key.
        crawl_id: Crawl job ID.

    Returns:
        List of per-page dicts, one per crawled page with rule results.
    """
    logger.info(
        f"build_per_page_breakdown: project_id={project_id}, crawl_id={crawl_id}"
    )

    rule_eval_repo = RuleEvaluationResultRepository(db)
    crawl_page_repo = CrawlPageRepository(db)
    seo_repo = PageSEODataRepository(db)
    network_repo = PageNetworkDataRepository(db)
    parsed_fact_repo = ParsedPageFactRepository(db)
    calculator = ScoreCalculator()

    # Load all rule evaluation results for this crawl+project
    all_results = await rule_eval_repo.get_by_project_id(project_id)
    crawl_results = [r for r in all_results if str(r.crawl_id) == str(crawl_id)]

    # Group by page_id
    page_groups: Dict[UUID, List[Any]] = defaultdict(list)
    for er in crawl_results:
        page_groups[er.page_id].append(er)

    # Load crawl pages for URL mapping
    crawl_pages = await crawl_page_repo.get_by_crawl_id(crawl_id)
    page_url_map: Dict[UUID, str] = {
        p.id: p.url or p.normalized_url for p in crawl_pages
    }
    page_obj_map: Dict[UUID, Any] = {p.id: p for p in crawl_pages}

    per_page: List[Dict[str, Any]] = []

    for page_id, results in page_groups.items():
        url = page_url_map.get(page_id, str(page_id))
        page_obj = page_obj_map.get(page_id)

        # Build RuleResult objects for scoring
        rule_results = [
            RR(
                rule_id=r.rule_id,
                name=r.rule_name,
                category=r.category,
                severity=Severity(r.severity),
                passed=r.passed,
                score_impact=r.score_impact,
                message=r.message,
                recommendation=r.recommendation,
                data=r.rule_data,
                tags=r.tags or [],
            )
            for r in results
        ]

        # Score: exclude ERROR severity from scoring
        scorable = [r for r in rule_results if r.severity != Severity.ERROR]
        if scorable:
            score = calculator.calculate_score(scorable)
        else:
            score = {
                "overall_score": 0.0,
                "grade": "F",
                "total_passed": 0,
                "total_failed": len(rule_results),
                "critical_issues": 0,
            }

        # Build rule_results for response (with page context)
        rule_results_dicts = [
            _summarize_rule_result(r, str(page_id), url) for r in results
        ]

        # Build crawl_details from CrawlPage
        crawl_details: Dict[str, Any] = {}
        if page_obj:
            network_data = await network_repo.get_by_page_id(page_id)
            crawl_details = {
                "status_code": page_obj.status_code,
                "response_time_ms": page_obj.response_time_ms,
                "content_length": page_obj.content_length,
                "content_type": page_obj.content_type,
                "is_success": page_obj.is_success,
                "is_error": page_obj.is_error,
                "is_redirect": page_obj.is_redirect,
                "depth": page_obj.depth,
                "normalized_url": page_obj.normalized_url,
                "final_url": page_obj.final_url,
                "network": {
                    "response_time_ms": network_data.response_time_ms if network_data else 0,
                    "content_length": network_data.content_length if network_data else 0,
                    "headers": network_data.headers if network_data else {},
                    "redirects": network_data.redirects if network_data else [],
                } if network_data else None,
            }

        # Build parsed_info from PageSEOData
        seo_data = await seo_repo.get_by_page_id(page_id)
        parsed_info: Dict[str, Any] = {}
        if seo_data:
            parsed_info = {
                "title": seo_data.title or "",
                "meta_description": seo_data.meta_description or "",
                "word_count": seo_data.word_count or 0,
                "language": seo_data.language or "",
                "canonical": seo_data.canonical or "",
                "charset": seo_data.charset or "",
                "viewport": seo_data.viewport or "",
                "favicon": seo_data.favicon or "",
                "robots_meta": seo_data.robots_meta or "",
                "structured_data": seo_data.structured_data or {},
                "social": seo_data.social or {},
                "headings": seo_data.headings or {},
                "accessibility": seo_data.accessibility or {},
            }

        # Build links_analysis from ParsedPageFact (filtered views over single list)
        links_analysis: Dict[str, Any] = {}
        parsed_fact = await parsed_fact_repo.get_by_page_id(project_id, page_id)
        if parsed_fact and parsed_fact.parsed_data:
            parsed_links = parsed_fact.parsed_data.get("links", []) or []
            links_analysis = _build_links_analysis(parsed_links, url)

        per_page.append({
            "page_id": str(page_id),
            "url": url,
            "overall_score": score.get("overall_score", 0.0),
            "grade": score.get("grade", "F"),
            "rules_passed": score.get("total_passed", 0),
            "rules_failed": score.get("total_failed", 0),
            "critical_issues": score.get("critical_issues", 0),
            "warnings": score.get("warnings", 0),
            "rule_results": rule_results_dicts,
            "crawl_details": crawl_details,
            "parsed_info": parsed_info,
            "links_analysis": links_analysis,
        })

    # Sort by overall_score ascending (worst pages first) for actionable output
    per_page.sort(key=lambda p: p["overall_score"])

    logger.info(
        f"build_per_page_breakdown: built {len(per_page)} page entries "
        f"for project_id={project_id}"
    )
    return per_page
