"""Sitemap discovery, evaluation, and recommendation service."""
import asyncio
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from app.modules.crawler.services.site_discovery_service import (
    SiteDiscoveryResult,
    SiteDiscoveryService,
)

from .schema import (
    SitemapCheckResponse,
    SitemapCheckSummary,
    SitemapFileResult,
    SitemapFinding,
    SitemapRecommendation,
    SitemapRobotsSummary,
)


class SitemapCheckService:
    """Run a complete sitemap check without crawling page HTML."""

    # Keep this endpoint bounded: it returns raw XML and parsed URLs in one
    # response, so unbounded sitemap expansion can overwhelm Swagger and the API.
    MAX_SITEMAP_FILES = 40
    MAX_URLS_PER_SITEMAP = 50_000
    MAX_TOTAL_PAGE_URLS = 50_000
    MAX_INDEX_DEPTH = 5
    FETCH_TIMEOUT_SECONDS = 10
    TOTAL_TIMEOUT_SECONDS = 90

    async def run_check(self, url: str) -> SitemapCheckResponse:
        discovery = SiteDiscoveryService(
            url,
            timeout=self.FETCH_TIMEOUT_SECONDS,
            max_child_sitemaps=self.MAX_SITEMAP_FILES,
            max_urls_per_sitemap=self.MAX_URLS_PER_SITEMAP,
            max_total_page_urls=self.MAX_TOTAL_PAGE_URLS,
            max_sitemap_index_depth=self.MAX_INDEX_DEPTH,
        )
        try:
            result = await asyncio.wait_for(
                discovery.discover(),
                timeout=self.TOTAL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"Sitemap discovery exceeded {self.TOTAL_TIMEOUT_SECONDS} seconds"
            ) from exc
        sitemap_files = [self._serialize_sitemap(item) for item in result.sitemaps]
        findings = self._evaluate(url, result, sitemap_files)
        recommendation_items = self._recommendations(findings)
        recommendations = [item.fix for item in recommendation_items]
        report = self._render_report(url, result, sitemap_files, findings)

        status_order = {"fail": 4, "warning": 3, "pass": 2, "not_applicable": 1}
        severity_order = {"critical": 5, "high": 4, "medium": 3, "low": 2, "none": 1}
        overall_status = max(
            (item.status for item in findings),
            key=lambda value: status_order.get(value, 0),
            default="not_applicable",
        )
        severity = max(
            (item.severity for item in findings),
            key=lambda value: severity_order.get(value, 0),
            default="none",
        )

        return SitemapCheckResponse(
            checked_url=url,
            robots_url=result.robots.url,
            robots_status_code=result.robots.status_code,
            robots_sitemap_references=result.robots.sitemap_references,
            sitemap_files=sitemap_files,
            total_sitemap_files=len(sitemap_files),
            total_page_urls=sum(item.url_count for item in sitemap_files),
            findings=findings,
            overall_status=overall_status,
            severity=severity,
            recommendations=recommendations,
            recommendation_items=recommendation_items,
            summary=SitemapCheckSummary(
                status=overall_status,
                severity=severity,
                sitemap_files=len(sitemap_files),
                sitemap_indexes=sum(item.is_index for item in sitemap_files),
                url_sets=sum(not item.is_index for item in sitemap_files),
                page_urls=sum(item.url_count for item in sitemap_files),
                passed_checks=sum(item.status == "pass" for item in findings),
                warning_count=sum(item.status == "warning" for item in findings),
                failure_count=sum(item.status == "fail" for item in findings),
            ),
            robots=SitemapRobotsSummary(
                url=result.robots.url,
                exists=result.robots.exists,
                status_code=result.robots.status_code,
                sitemap_references=result.robots.sitemap_references,
            ),
            report_markdown=report,
        )

    @staticmethod
    def _serialize_sitemap(item) -> SitemapFileResult:
        urls = list(item.urls)
        url_set = set(urls)
        parsed_urls = [urlparse(value) for value in urls]
        source = urlparse(item.url)
        invalid_url_count = sum(
            not parsed.scheme in {"http", "https"} or not parsed.netloc
            for parsed in parsed_urls
        )
        cross_host_url_count = sum(
            bool(parsed.netloc and parsed.hostname != source.hostname)
            for parsed in parsed_urls
        )
        duplicate_url_count = len(urls) - len(url_set)
        issues: list[str] = []
        if item.raw_content:
            try:
                root = ET.fromstring(item.raw_content)
                root_name = root.tag.rsplit("}", 1)[-1].lower()
                expected_root = "sitemapindex" if item.is_index else "urlset"
                if root_name != expected_root:
                    issues.append("invalid_root")
            except ET.ParseError:
                # The discovery parser already records the parse error.
                pass
        if item.error:
            issues.append("parse_error")
        if item.status_code != 200:
            issues.append("http_error")
        if not item.is_index and not urls:
            issues.append("empty_sitemap")
        if invalid_url_count:
            issues.append("invalid_urls")
        if cross_host_url_count:
            issues.append("cross_host_urls")
        if duplicate_url_count:
            issues.append("duplicate_urls")
        if item.content_length > 50 * 1024 * 1024:
            issues.append("file_size_limit")
        if len(urls) > 50_000 and not item.is_index:
            issues.append("url_count_limit")
        return SitemapFileResult(
            url=item.url,
            status_code=item.status_code,
            exists=item.exists,
            is_index=item.is_index,
            content_type=item.content_type,
            content_length=item.content_length,
            child_sitemaps=item.child_sitemaps,
            url_count=len(item.urls),
            urls=urls,
            raw_content=item.raw_content,
            error=item.error,
            kind="sitemap_index" if item.is_index else "urlset",
            health="fail" if issues and any(issue in issues for issue in ("http_error", "parse_error", "invalid_root", "invalid_urls", "cross_host_urls", "url_count_limit", "file_size_limit")) else "warning" if issues else "pass",
            issues=issues,
            duplicate_url_count=duplicate_url_count,
            invalid_url_count=invalid_url_count,
            cross_host_url_count=cross_host_url_count,
        )

    @staticmethod
    def _recommendations(findings: list[SitemapFinding]) -> list[SitemapRecommendation]:
        priority_by_severity = {
            "critical": "critical", "high": "high", "medium": "medium", "low": "low"
        }
        return [
            SitemapRecommendation(
                code=finding.code,
                priority=priority_by_severity.get(finding.severity, "info"),
                title=finding.message,
                message=finding.message,
                evidence=[finding.evidence],
                fix=finding.recommendation,
            )
            for finding in findings
            if finding.status != "pass"
        ]

    @staticmethod
    def _finding(code: str, severity: str, status: str, message: str, evidence: str, recommendation: str) -> SitemapFinding:
        return SitemapFinding(
            code=code,
            severity=severity,
            status=status,
            message=message,
            evidence=evidence,
            recommendation=recommendation,
        )

    def _evaluate(self, url: str, result: SiteDiscoveryResult, files: list[SitemapFileResult]) -> list[SitemapFinding]:
        findings: list[SitemapFinding] = []
        domain = urlparse(url).hostname or url

        if not files:
            findings.append(self._finding(
                "sitemap_missing",
                "high",
                "fail",
                "No reachable sitemap file was found.",
                f"Checked robots.txt and known sitemap paths for {domain}; no valid sitemap was discovered.",
                f"Create an XML sitemap and publish it at https://{domain}/sitemap.xml, then reference it in robots.txt.",
            ))
        else:
            findings.append(self._finding(
                "sitemap_present",
                "none",
                "pass",
                "At least one sitemap file was discovered and parsed.",
                f"{len(files)} sitemap file(s), {sum(item.url_count for item in files)} page URL(s).",
                "Keep the sitemap files current and submit the sitemap index in Google Search Console.",
            ))

        if result.robots.exists and not result.robots.sitemap_references:
            findings.append(self._finding(
                "sitemap_not_in_robots",
                "medium",
                "warning",
                "robots.txt does not declare a Sitemap directive.",
                f"{result.robots.url} returned HTTP {result.robots.status_code} without a sitemap reference.",
                f"Add `Sitemap: https://{domain}/sitemap.xml` or the canonical sitemap index URL to robots.txt.",
            ))

        for item in files:
            if item.status_code != 200:
                findings.append(self._finding(
                    "sitemap_http_error",
                    "high",
                    "fail",
                    f"Sitemap returned HTTP {item.status_code}.",
                    item.url,
                    "Make the sitemap publicly reachable and return HTTP 200 without authentication or redirects to an HTML page.",
                ))
            if item.url_count == 0:
                findings.append(self._finding(
                    "sitemap_empty",
                    "medium",
                    "warning",
                    "Sitemap contains no page URLs.",
                    item.url,
                    "Populate the sitemap with canonical, indexable page URLs or remove the empty sitemap reference.",
                ))
            if item.error:
                findings.append(self._finding(
                    "sitemap_parse_error",
                    "high",
                    "fail",
                    "Sitemap could not be parsed completely.",
                    f"{item.url}: {item.error}",
                    "Return valid XML using a sitemap or sitemap-index root element and repair malformed tags or encoding.",
                ))
            if "invalid_root" in item.issues:
                findings.append(self._finding(
                    "sitemap_invalid_root",
                    "high",
                    "fail",
                    "Sitemap XML has the wrong root element.",
                    f"{item.url}: expected {'sitemapindex' if item.is_index else 'urlset'}.",
                    "Use <urlset> for a URL sitemap or <sitemapindex> for an index file, with the standard sitemap namespace.",
                ))
            if item.content_length > 50 * 1024 * 1024:
                findings.append(self._finding(
                    "sitemap_oversized",
                    "medium",
                    "warning",
                    "Sitemap exceeds the 50 MB uncompressed limit.",
                    f"{item.url}: {item.content_length} bytes.",
                    "Split the sitemap into smaller files and reference them from a sitemap index.",
                ))
            if item.url_count > 50_000 and not item.is_index:
                findings.append(self._finding(
                    "sitemap_url_limit",
                    "high",
                    "fail",
                    "Sitemap contains more than 50,000 URLs.",
                    f"{item.url}: {item.url_count} URLs.",
                    "Split this file into multiple sitemap files and reference them through a sitemap index.",
                ))
            if item.invalid_url_count:
                findings.append(self._finding(
                    "sitemap_invalid_urls",
                    "high",
                    "fail",
                    "Sitemap contains invalid URL entries.",
                    f"{item.url}: {item.invalid_url_count} invalid URL(s).",
                    "Use absolute HTTP or HTTPS URLs in every <loc> element and remove malformed entries.",
                ))
            if item.cross_host_url_count:
                findings.append(self._finding(
                    "sitemap_cross_host_urls",
                    "high",
                    "fail",
                    "Sitemap contains URLs from another host.",
                    f"{item.url}: {item.cross_host_url_count} cross-host URL(s).",
                    "Keep sitemap URLs on the same host as the sitemap, or use an explicitly verified cross-site submission setup.",
                ))
            if item.duplicate_url_count:
                findings.append(self._finding(
                    "sitemap_duplicate_urls",
                    "low",
                    "warning",
                    "Sitemap contains duplicate URL entries.",
                    f"{item.url}: {item.duplicate_url_count} duplicate URL(s).",
                    "Deduplicate <loc> entries so each canonical URL appears only once.",
                ))

        if len(findings) == 1 and findings[0].status == "pass":
            findings.append(self._finding(
                "sitemap_healthy",
                "none",
                "pass",
                "Sitemap discovery and validation checks passed.",
                "All discovered sitemap files returned content and parsed successfully.",
                "Continue regenerating the sitemap when content changes and monitor it in Search Console.",
            ))
        return findings

    @staticmethod
    def _render_report(url: str, result: SiteDiscoveryResult, files: list[SitemapFileResult], findings: list[SitemapFinding]) -> str:
        lines = ["### Sitemap check", "", f"- Checked URL: {url}", f"- Sitemap files: {len(files)}", f"- Page URLs: {sum(item.url_count for item in files)}", "", "### Sitemap files", ""]
        if not files:
            lines.append("- No reachable sitemap files found")
        for item in files:
            lines.extend([
                f"#### {item.url}",
                f"- HTTP status: {item.status_code}",
                f"- Type: {'sitemap index' if item.is_index else 'URL set'}",
                f"- Page URLs: {item.url_count}",
                "",
                "```xml",
                item.raw_content or "",
                "```",
                "",
            ])
        lines.extend(["### Recommendations and evidence", ""])
        for finding in findings:
            lines.extend([
                f"#### `{finding.code}`",
                f"- Status: {finding.status}",
                f"- Finding: {finding.message}",
                f"- Evidence: {finding.evidence}",
                f"- Fix: {finding.recommendation}",
                "",
            ])
        return "\n".join(lines).rstrip()
