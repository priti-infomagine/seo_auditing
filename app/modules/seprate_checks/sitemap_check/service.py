"""Asynchronous sitemap discovery, evaluation, and recommendation service."""
import asyncio
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from typing import Callable, Dict, List, Optional, Tuple, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.logger import logger
from app.modules.crawler.services.site_discovery_service import (
    SiteDiscoveryResult,
    SiteDiscoveryService,
)
from app.shared.utils.url_utils import normalize_host

from .model import (
    SitemapCheck,
    SitemapCheckStatus,
    SitemapOverallStatus,
    SitemapSeverity,
)
from .repository import SitemapCheckRepository
from .schema import (
    SitemapFileItem,
    SitemapIssue,
    SitemapRecommendation,
    SitemapSummary,
)


def _normalize_target_url(raw_url: str) -> Tuple[str, str]:
    """Normalize input URL or bare domain into (canonical_url, domain)."""
    cleaned = raw_url.strip()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"

    parsed = urlparse(cleaned)
    host = normalize_host(parsed.netloc or parsed.path)
    if not host:
        raise ValueError(f"Invalid URL or domain provided: {raw_url}")

    canonical_url = f"{parsed.scheme or 'https'}://{host}"
    return canonical_url, host


class SitemapCheckService:
    """Service to execute async sitemap validation jobs."""

    MAX_SITEMAP_FILES = 40
    MAX_URLS_PER_SITEMAP = 50_000
    MAX_TOTAL_PAGE_URLS = 50_000
    MAX_INDEX_DEPTH = 5
    FETCH_TIMEOUT_SECONDS = 15
    TOTAL_TIMEOUT_SECONDS = 90

    @classmethod
    async def prepare_check(
        cls,
        url: str,
        db: AsyncSession,
    ) -> SitemapCheck:
        """Validate input and create initial queued record in DB."""
        canonical_url, domain = _normalize_target_url(url)

        check = SitemapCheck(
            url=canonical_url,
            domain=domain,
            status=SitemapCheckStatus.QUEUED,
            progress={"phase": "queued", "message": "Check queued in worker"},
        )
        repo = SitemapCheckRepository(db)
        saved = await repo.create(check)
        await db.commit()
        return saved

    async def run_check_async(
        self,
        check_id: UUID,
        url: str,
        db: Optional[AsyncSession] = None,
        update_state: Optional[Callable[[str, Optional[dict]], None]] = None,
    ) -> Dict[str, Any]:
        """Execute the sitemap discovery, parsing, and rule evaluation workflow."""
        start_time = time.perf_counter()
        if db is not None:
            return await self._execute_check(check_id, url, db, update_state, start_time)

        async with async_session_factory() as session:
            return await self._execute_check(check_id, url, session, update_state, start_time)

    async def _execute_check(
        self,
        check_id: UUID,
        url: str,
        db: AsyncSession,
        update_state: Optional[Callable[[str, Optional[dict]], None]],
        start_time: float,
    ) -> Dict[str, Any]:
        canonical_url, domain = _normalize_target_url(url)
        repo = SitemapCheckRepository(db)
        try:
            # 1. Update status to PROCESSING
            progress_data = {
                "phase": "discovering",
                "message": f"Discovering sitemaps and robots.txt for {domain}...",
            }
            await repo.update_progress(
                check_id,
                SitemapCheckStatus.PROCESSING,
                progress=progress_data,
            )
            await db.commit()

            if update_state:
                update_state("PROGRESS", meta=progress_data)

            # 2. Run Site Discovery
            discovery = SiteDiscoveryService(
                canonical_url,
                timeout=self.FETCH_TIMEOUT_SECONDS,
                max_child_sitemaps=self.MAX_SITEMAP_FILES,
                max_urls_per_sitemap=self.MAX_URLS_PER_SITEMAP,
                max_total_page_urls=self.MAX_TOTAL_PAGE_URLS,
                max_sitemap_index_depth=self.MAX_INDEX_DEPTH,
            )

            result: SiteDiscoveryResult = await asyncio.wait_for(
                discovery.discover(),
                timeout=self.TOTAL_TIMEOUT_SECONDS,
            )

            # 3. Update Progress (evaluation phase)
            progress_data = {
                "phase": "evaluating",
                "message": f"Evaluating {len(result.sitemaps)} sitemap file(s)...",
                "sitemaps_discovered": len(result.sitemaps),
            }
            await repo.update_progress(
                check_id,
                SitemapCheckStatus.PROCESSING,
                progress=progress_data,
            )
            await db.commit()

            if update_state:
                update_state("PROGRESS", meta=progress_data)

            # 4. Serialize & Evaluate each sitemap file
            sitemap_items: List[SitemapFileItem] = []
            total_urls_declared = 0
            sitemap_indexes = 0
            url_sitemaps = 0

            for item in result.sitemaps:
                file_item = self._evaluate_sitemap_file(item, domain)
                sitemap_items.append(file_item)
                if file_item.is_index:
                    sitemap_indexes += 1
                else:
                    url_sitemaps += 1
                    total_urls_declared += file_item.entry_count

            # 5. Domain-level checks (robots.txt & missing sitemap)
            domain_issues, domain_recs = self._evaluate_domain_level(
                result, sitemap_items, domain
            )

            # Aggregate all findings and recommendations
            all_findings: List[SitemapIssue] = list(domain_issues)
            all_recommendations: List[SitemapRecommendation] = list(domain_recs)

            for item in sitemap_items:
                all_findings.extend(item.issues)
                all_recommendations.extend(item.recommendations)

            # Deduplicate recommendations by code
            seen_rec_codes = set()
            deduped_recommendations = []
            for rec in all_recommendations:
                if rec.code not in seen_rec_codes:
                    seen_rec_codes.add(rec.code)
                    deduped_recommendations.append(rec)

            # 6. Overall Status and Severity Calculation
            overall_status, overall_severity = self._compute_overall_status(
                all_findings
            )

            summary = SitemapSummary(
                total_sitemaps=len(sitemap_items),
                sitemap_indexes=sitemap_indexes,
                url_sitemaps=url_sitemaps,
                total_urls_declared=total_urls_declared,
                total_issues=len(all_findings),
            )

            cost_seconds = round(time.perf_counter() - start_time, 3)
            report_markdown = self._generate_markdown_report(
                domain=domain,
                summary=summary,
                overall_status=overall_status.value,
                severity=overall_severity.value,
                sitemaps=sitemap_items,
                findings=all_findings,
                recommendations=deduped_recommendations,
            )

            # 7. Persist COMPLETED State
            await repo.update_completed(
                check_id=check_id,
                overall_status=overall_status,
                severity=overall_severity,
                summary=summary.model_dump(mode="json"),
                sitemaps=[s.model_dump(mode="json") for s in sitemap_items],
                findings=[f.model_dump(mode="json") for f in all_findings],
                recommendations=[
                    r.model_dump(mode="json") for r in deduped_recommendations
                ],
                report_markdown=report_markdown,
                cost_seconds=cost_seconds,
            )
            await db.commit()

            return {
                "status": SitemapCheckStatus.COMPLETED.value,
                "check_id": str(check_id),
                "domain": domain,
                "overall_status": overall_status.value,
                "total_sitemaps": len(sitemap_items),
                "total_urls": total_urls_declared,
            }

        except Exception as exc:
            logger.error(
                f"run_check_async failed for check_id={check_id}: {exc}",
                exc_info=True,
            )
            await repo.update_progress(
                check_id,
                SitemapCheckStatus.FAILED,
                error=str(exc),
            )
            await db.commit()
            raise

    def _evaluate_sitemap_file(self, item, domain: str) -> SitemapFileItem:
        """Inspect a single sitemap file for protocol, syntax, and SEO rules."""
        urls = list(item.urls or [])
        url_count = len(urls)
        issues: List[SitemapIssue] = []

        # 1. HTTP Status check
        if item.status_code != 200:
            issues.append(
                SitemapIssue(
                    code="sitemap_unreachable",
                    severity="high"
                    if item.status_code == 0 or item.status_code >= 500
                    else "medium",
                    status="fail" if item.status_code >= 500 else "warning",
                    message=f"Sitemap returned HTTP {item.status_code or 'unreachable'}",
                    evidence=f"{item.url}: HTTP {item.status_code} - {item.error or 'Failed to fetch'}",
                )
            )

        # 2. Parse Error check
        if item.error:
            issues.append(
                SitemapIssue(
                    code="sitemap_parse_error",
                    severity="high",
                    status="fail",
                    message="Sitemap XML could not be parsed",
                    evidence=f"{item.url}: {item.error}",
                )
            )

        # 3. Content-Type check
        if item.content_type:
            valid_content_types = {
                "application/xml",
                "text/xml",
                "application/x-xml",
                "application/rss+xml",
                "application/gzip",
                "application/x-gzip",
            }
            ct_clean = item.content_type.split(";")[0].strip().lower()
            if ct_clean and ct_clean not in valid_content_types:
                issues.append(
                    SitemapIssue(
                        code="sitemap_wrong_content_type",
                        severity="low",
                        status="warning",
                        message=f"Sitemap served with unexpected Content-Type: '{item.content_type}'",
                        evidence=f"Expected XML Content-Type, got '{item.content_type}'",
                    )
                )

        # 4. XML Root tag validation
        if item.raw_content:
            try:
                root = ET.fromstring(item.raw_content)
                root_tag = root.tag.rsplit("}", 1)[-1].lower()
                expected_root = "sitemapindex" if item.is_index else "urlset"
                if root_tag != expected_root:
                    issues.append(
                        SitemapIssue(
                            code="sitemap_invalid_root",
                            severity="high",
                            status="fail",
                            message=f"Invalid XML root element: expected <{expected_root}>, got <{root_tag}>",
                            evidence=f"{item.url}: root element is <{root_tag}>",
                        )
                    )
            except ET.ParseError:
                pass

        # 5. Empty Sitemap check
        if not item.is_index and url_count == 0 and item.status_code == 200:
            issues.append(
                SitemapIssue(
                    code="sitemap_empty",
                    severity="medium",
                    status="warning",
                    message="Sitemap file contains 0 URLs",
                    evidence=f"{item.url}: 0 <loc> entries found",
                )
            )

        # 6. URL count and file size limits
        if url_count > 50_000 and not item.is_index:
            issues.append(
                SitemapIssue(
                    code="sitemap_url_limit_exceeded",
                    severity="high",
                    status="fail",
                    message="Sitemap exceeds 50,000 URL limit",
                    evidence=f"{item.url}: contains {url_count} URLs",
                )
            )

        if item.content_length > 50 * 1024 * 1024:
            issues.append(
                SitemapIssue(
                    code="sitemap_file_size_exceeded",
                    severity="high",
                    status="fail",
                    message="Sitemap exceeds 50 MB uncompressed limit",
                    evidence=f"{item.url}: {round(item.content_length / (1024 * 1024), 2)} MB",
                )
            )

        # 7. Duplicates & Host consistency
        if urls:
            unique_urls = set(urls)
            if len(unique_urls) < len(urls):
                diff = len(urls) - len(unique_urls)
                issues.append(
                    SitemapIssue(
                        code="sitemap_duplicate_urls",
                        severity="low",
                        status="warning",
                        message=f"Sitemap contains {diff} duplicate URL(s)",
                        evidence=f"{item.url}: {diff} duplicate entries",
                    )
                )

            cross_host_count = 0
            for u in urls:
                p = urlparse(u)
                if p.netloc and normalize_host(p.netloc) != domain:
                    cross_host_count += 1
            if cross_host_count > 0:
                issues.append(
                    SitemapIssue(
                        code="sitemap_cross_host_urls",
                        severity="medium",
                        status="warning",
                        message=f"Sitemap contains {cross_host_count} cross-host URL(s)",
                        evidence=f"{item.url}: URLs found pointing outside {domain}",
                    )
                )

        recommendations = self._generate_recommendations_for_issues(issues)

        return SitemapFileItem(
            url=item.url,
            is_index=item.is_index,
            status_code=item.status_code or 0,
            content_type=item.content_type or "unknown",
            entry_count=url_count,
            content_length=item.content_length or 0,
            response_time_ms=0,
            error=item.error,
            issues=issues,
            recommendations=recommendations,
        )

    def _evaluate_domain_level(
        self,
        result: SiteDiscoveryResult,
        sitemap_items: List[SitemapFileItem],
        domain: str,
    ) -> Tuple[List[SitemapIssue], List[SitemapRecommendation]]:
        """Evaluate domain-wide issues like robots.txt Sitemap: directives."""
        issues: List[SitemapIssue] = []

        if not sitemap_items:
            issues.append(
                SitemapIssue(
                    code="sitemap_none_found",
                    severity="high",
                    status="fail",
                    message="No sitemap files were found for this website",
                    evidence=f"Checked robots.txt and standard locations on {domain}; 0 sitemaps found",
                )
            )
        else:
            # Check if robots.txt exists but missing Sitemap declaration
            if result.robots.exists and not result.robots.sitemap_references:
                issues.append(
                    SitemapIssue(
                        code="sitemap_not_in_robots",
                        severity="medium",
                        status="warning",
                        message="robots.txt does not declare any Sitemap: directive",
                        evidence=f"{result.robots.url} returned HTTP 200 without Sitemap:",
                    )
                )

        recommendations = self._generate_recommendations_for_issues(issues)
        return issues, recommendations

    def _generate_recommendations_for_issues(
        self, issues: List[SitemapIssue]
    ) -> List[SitemapRecommendation]:
        """Convert issue codes into actionable recommendations."""
        REC_CATALOG = {
            "sitemap_none_found": SitemapRecommendation(
                code="sitemap_none_found",
                priority="critical",
                title="Create and publish XML sitemap",
                message="Your website has no discoverable XML sitemaps for search engines.",
                fix="Generate an XML sitemap at /sitemap.xml and declare it in robots.txt.",
                where_to_fix="cms",
            ),
            "sitemap_not_in_robots": SitemapRecommendation(
                code="sitemap_not_in_robots",
                priority="medium",
                title="Declare Sitemap in robots.txt",
                message="Search engine crawlers check robots.txt first to locate your sitemaps.",
                fix="Add 'Sitemap: https://yourdomain.com/sitemap.xml' to your robots.txt file.",
                where_to_fix="robots_txt",
            ),
            "sitemap_unreachable": SitemapRecommendation(
                code="sitemap_unreachable",
                priority="high",
                title="Fix sitemap accessibility",
                message="One or more sitemap URLs returned an error status code.",
                fix="Ensure the sitemap URL returns HTTP 200 with valid XML. Check server routing and permissions.",
                where_to_fix="server_config",
            ),
            "sitemap_parse_error": SitemapRecommendation(
                code="sitemap_parse_error",
                priority="high",
                title="Fix XML syntax errors",
                message="The sitemap XML is malformed and cannot be parsed by crawlers.",
                fix="Validate and fix XML syntax errors, closing tags, and UTF-8 encoding.",
                where_to_fix="sitemap_xml",
            ),
            "sitemap_invalid_root": SitemapRecommendation(
                code="sitemap_invalid_root",
                priority="high",
                title="Correct XML root element",
                message="The sitemap root element does not match the XML sitemap standard.",
                fix="Use <urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'> for URL sitemaps or <sitemapindex> for indexes.",
                where_to_fix="sitemap_xml",
            ),
            "sitemap_empty": SitemapRecommendation(
                code="sitemap_empty",
                priority="medium",
                title="Populate empty sitemap",
                message="The sitemap file exists but contains no URLs.",
                fix="Add canonical page URLs to the sitemap or remove the file if unneeded.",
                where_to_fix="cms",
            ),
            "sitemap_url_limit_exceeded": SitemapRecommendation(
                code="sitemap_url_limit_exceeded",
                priority="high",
                title="Split large sitemap file",
                message="Search engines enforce a 50,000 URL limit per individual sitemap file.",
                fix="Split the sitemap into multiple files (max 50,000 URLs each) and link them via a sitemap index.",
                where_to_fix="cms",
            ),
            "sitemap_file_size_exceeded": SitemapRecommendation(
                code="sitemap_file_size_exceeded",
                priority="high",
                title="Compress or split oversized sitemap",
                message="Sitemap exceeds the 50 MB uncompressed file size limit.",
                fix="Enable gzip compression (.xml.gz) or split into smaller sitemaps.",
                where_to_fix="cms",
            ),
            "sitemap_duplicate_urls": SitemapRecommendation(
                code="sitemap_duplicate_urls",
                priority="low",
                title="Deduplicate URLs in sitemap",
                message="Multiple entries for the same URL waste crawl budget.",
                fix="Ensure each canonical URL is listed only once in the sitemap.",
                where_to_fix="sitemap_xml",
            ),
            "sitemap_cross_host_urls": SitemapRecommendation(
                code="sitemap_cross_host_urls",
                priority="medium",
                title="Remove cross-host URLs",
                message="Sitemaps should only list URLs belonging to the same domain host.",
                fix="Move external URLs to their respective domain sitemaps.",
                where_to_fix="sitemap_xml",
            ),
            "sitemap_wrong_content_type": SitemapRecommendation(
                code="sitemap_wrong_content_type",
                priority="low",
                title="Set correct Content-Type header",
                message="Sitemaps should be served with application/xml or text/xml.",
                fix="Configure your web server to serve .xml files with Content-Type: application/xml.",
                where_to_fix="server_config",
            ),
        }

        recs = []
        for issue in issues:
            if issue.code in REC_CATALOG:
                recs.append(REC_CATALOG[issue.code])
        return recs

    def _compute_overall_status(
        self, findings: List[SitemapIssue]
    ) -> Tuple[SitemapOverallStatus, SitemapSeverity]:
        """Compute aggregated status and severity."""
        if not findings:
            return SitemapOverallStatus.PASS, SitemapSeverity.NONE

        has_critical = any(
            f.severity == "critical" or f.status == "fail" for f in findings
        )
        has_high = any(f.severity == "high" for f in findings)
        has_medium = any(f.severity == "medium" for f in findings)
        has_low = any(f.severity == "low" for f in findings)

        if has_critical or has_high:
            severity = (
                SitemapSeverity.CRITICAL if has_critical else SitemapSeverity.HIGH
            )
            return SitemapOverallStatus.FAIL, severity
        elif has_medium or has_low:
            severity = SitemapSeverity.MEDIUM if has_medium else SitemapSeverity.LOW
            return SitemapOverallStatus.WARNING, severity

        return SitemapOverallStatus.PASS, SitemapSeverity.NONE

    def _generate_markdown_report(
        self,
        domain: str,
        summary: SitemapSummary,
        overall_status: str,
        severity: str,
        sitemaps: List[SitemapFileItem],
        findings: List[SitemapIssue],
        recommendations: List[SitemapRecommendation],
    ) -> str:
        """Generate formatted markdown audit report."""
        lines = [
            f"# Sitemap Audit Report for `{domain}`",
            "",
            f"**Overall Status:** `{overall_status.upper()}` | **Severity:** `{severity.upper()}`",
            "",
            "## Summary",
            f"- **Total Sitemaps:** {summary.total_sitemaps} ({summary.sitemap_indexes} index, {summary.url_sitemaps} urlset)",
            f"- **Total URLs Declared:** {summary.total_urls_declared:,}",
            f"- **Total Issues Found:** {summary.total_issues}",
            "",
            "## Discovered Sitemap Files",
        ]

        if not sitemaps:
            lines.append("- *No sitemaps discovered.*")
        else:
            for item in sitemaps:
                file_type = "Index" if item.is_index else "URLset"
                lines.append(
                    f"- {item.url} | HTTP {item.status_code} | {file_type} | {item.entry_count:,} entries"
                )

        lines.extend(["", "## Issues and Findings"])
        if not findings:
            lines.append("- *No issues detected. All sitemap checks passed successfully.*")
        else:
            for f in findings:
                lines.append(f"- **[{f.severity.upper()}] `{f.code}`**: {f.message}")
                if f.evidence:
                    lines.append(f"  - *Evidence:* {f.evidence}")

        lines.extend(["", "## Recommendations"])
        if not recommendations:
            lines.append("- *No action required.*")
        else:
            for r in recommendations:
                lines.append(f"### `{r.code}`: {r.title}")
                lines.append(f"- **Priority:** {r.priority.capitalize()} | **Fix Location:** `{r.where_to_fix}`")
                lines.append(f"- **Action:** {r.fix}")
                lines.append("")

        return "\n".join(lines).rstrip()
