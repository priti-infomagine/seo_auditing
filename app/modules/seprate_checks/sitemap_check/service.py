"""Sitemap discovery, evaluation, and recommendation service - New format."""
import asyncio
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from typing import List

from app.modules.crawler.services.site_discovery_service import (
    SiteDiscoveryResult,
    SiteDiscoveryService,
)

from .schema import (
    SitemapCheckResponse,
    SitemapCheckData,
    SitemapEntry,
    SitemapIssue,
    SitemapRecommendation,
)


class SitemapCheckService:
    """Run a complete sitemap check without crawling page HTML."""

    MAX_SITEMAP_FILES = 40
    MAX_URLS_PER_SITEMAP = 50_000
    MAX_TOTAL_PAGE_URLS = 50_000
    MAX_INDEX_DEPTH = 5
    FETCH_TIMEOUT_SECONDS = 10
    TOTAL_TIMEOUT_SECONDS = 90

    async def run_check(self, url: str) -> SitemapCheckResponse:
        start_time = time.perf_counter()
        
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

        sitemap_entries = [self._serialize_sitemap(item) for item in result.sitemaps]
        
        # Add domain-level issues (robots.txt, missing sitemap)
        domain_issues = generate_domain_issues(result, sitemap_entries)
        domain_recs = generate_domain_recommendations(domain_issues)
        
        # Attach domain issues to first sitemap or create virtual entry
        if sitemap_entries:
            sitemap_entries[0].issues = domain_issues + sitemap_entries[0].issues
            sitemap_entries[0].recommendations = domain_recs + sitemap_entries[0].recommendations
        else:
            # No sitemaps found - create a virtual entry for domain issues
            sitemap_entries.append(SitemapEntry(
                url=f"{url}/sitemap.xml",
                status=404,
                contentType="not_found",
                entries=0,
                isIndex=False,
                issues=domain_issues,
                recommendations=domain_recs,
            ))
        
        # Calculate cost (time in seconds)
        cost = round(time.perf_counter() - start_time, 3)

        return SitemapCheckResponse(
            data=SitemapCheckData(
                url=url,
                sitemaps=sitemap_entries,
            ),
            cost=cost,
        )

    def _serialize_sitemap(self, item) -> SitemapEntry:
        urls = list(item.urls)
        url_count = len(urls)
        
        # Detect issues
        issues = self._detect_issues(item, urls)
        
        # Generate recommendations from issues
        recommendations = self._generate_recommendations(issues, item)
        
        return SitemapEntry(
            url=item.url,
            status=item.status_code or 0,
            contentType=item.content_type or "unknown",
            entries=url_count if not item.is_index else 0,
            isIndex=item.is_index,
            issues=issues,
            recommendations=recommendations,
            urls=urls,
            raw_content=item.raw_content,
            content_length=item.content_length,
        )

    def _detect_issues(self, item, urls: List[str]) -> List[SitemapIssue]:
        issues = []
        
        # HTTP errors
        if item.status_code != 200:
            issues.append(SitemapIssue(
                code="http_error",
                severity="high" if item.status_code == 0 or item.status_code >= 500 else "medium",
                message=f"Sitemap returned HTTP {item.status_code or 'connection failed'}",
                evidence=f"{item.url}: HTTP {item.status_code or 'unreachable'} - {item.error or 'no response'}",
            ))
        
        # Parse errors
        if item.error:
            issues.append(SitemapIssue(
                code="parse_error",
                severity="high",
                message="Sitemap could not be parsed",
                evidence=f"{item.url}: {item.error}",
            ))
        
        # Invalid root element
        if item.raw_content:
            try:
                root = ET.fromstring(item.raw_content)
                root_name = root.tag.rsplit("}", 1)[-1].lower()
                expected_root = "sitemapindex" if item.is_index else "urlset"
                if root_name != expected_root:
                    issues.append(SitemapIssue(
                        code="invalid_root",
                        severity="high",
                        message=f"Wrong XML root element: expected <{expected_root}>, got <{root_name}>",
                        evidence=f"{item.url}: root element is {root_name}",
                    ))
            except ET.ParseError:
                pass  # Already caught above
        
        # Empty sitemap (only for urlset, not index)
        if not item.is_index and url_count == 0:
            issues.append(SitemapIssue(
                code="empty_sitemap",
                severity="medium",
                message="Sitemap contains no URLs",
                evidence=f"{item.url}: 0 URL entries",
            ))
        
        # URL validation
        parsed_urls = [urlparse(u) for u in urls]
        source_host = urlparse(item.url).hostname
        
        invalid_count = sum(
            1 for p in parsed_urls 
            if p.scheme not in {"http", "https"} or not p.netloc
        )
        if invalid_count:
            issues.append(SitemapIssue(
                code="invalid_urls",
                severity="high",
                message=f"Sitemap contains {invalid_count} invalid URL(s)",
                evidence=f"{item.url}: {invalid_count} URLs missing scheme or host",
            ))
        
        cross_host_count = sum(
            1 for p in parsed_urls 
            if p.netloc and p.hostname != source_host
        )
        if cross_host_count:
            issues.append(SitemapIssue(
                code="cross_host_urls",
                severity="high",
                message=f"Sitemap contains {cross_host_count} cross-host URL(s)",
                evidence=f"{item.url}: URLs point to different hostname",
            ))
        
        # Duplicates
        unique_urls = set(urls)
        duplicate_count = len(urls) - len(unique_urls)
        if duplicate_count:
            issues.append(SitemapIssue(
                code="duplicate_urls",
                severity="low",
                message=f"Sitemap contains {duplicate_count} duplicate URL(s)",
                evidence=f"{item.url}: {duplicate_count} duplicates found",
            ))
        
        # Size limits
        if item.content_length > 50 * 1024 * 1024:
            issues.append(SitemapIssue(
                code="file_size_limit",
                severity="medium",
                message="Sitemap exceeds 50 MB limit",
                evidence=f"{item.url}: {item.content_length} bytes",
            ))
        
        if url_count > 50_000 and not item.is_index:
            issues.append(SitemapIssue(
                code="url_count_limit",
                severity="high",
                message="Sitemap exceeds 50,000 URL limit",
                evidence=f"{item.url}: {url_count} URLs",
            ))
        
        return issues

    def _generate_recommendations(self, issues: List[SitemapIssue], item) -> List[SitemapRecommendation]:
        """Generate fix recommendations from issues."""
        recommendations = []
        
        fix_map = {
            "http_error": SitemapRecommendation(
                code="http_error",
                priority="high",
                title="Fix sitemap accessibility",
                message="The sitemap URL is not accessible or returns an error status.",
                fix="Ensure the sitemap URL returns HTTP 200 with valid XML. Check server config, authentication, and DNS.",
                where_to_fix="server_config",
            ),
            "parse_error": SitemapRecommendation(
                code="parse_error",
                priority="high",
                title="Fix XML syntax",
                message="The sitemap XML is malformed and cannot be parsed.",
                fix="Validate and fix the XML syntax. Ensure proper encoding, closing tags, and namespace declarations.",
                where_to_fix="sitemap_xml",
            ),
            "invalid_root": SitemapRecommendation(
                code="invalid_root",
                priority="high",
                title="Correct XML root element",
                message="The sitemap has an incorrect root element.",
                fix="Use <urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'> for URL sitemaps or <sitemapindex> for index files.",
                where_to_fix="sitemap_xml",
            ),
            "empty_sitemap": SitemapRecommendation(
                code="empty_sitemap",
                priority="medium",
                title="Populate sitemap with URLs",
                message="The sitemap file exists but contains no URLs.",
                fix="Add canonical, indexable page URLs to the sitemap, or remove the reference if the sitemap is not needed.",
                where_to_fix="cms",
            ),
            "invalid_urls": SitemapRecommendation(
                code="invalid_urls",
                priority="high",
                title="Fix invalid URLs in sitemap",
                message="Some URLs in the sitemap are malformed.",
                fix="Ensure all <loc> entries use absolute HTTP/HTTPS URLs with valid hostnames. Remove malformed entries.",
                where_to_fix="sitemap_xml",
            ),
            "cross_host_urls": SitemapRecommendation(
                code="cross_host_urls",
                priority="high",
                title="Remove cross-host URLs",
                message="Sitemap contains URLs from a different hostname.",
                fix="Keep all URLs in the sitemap on the same host, or use Google Search Console cross-site verification if intentional.",
                where_to_fix="sitemap_xml",
            ),
            "duplicate_urls": SitemapRecommendation(
                code="duplicate_urls",
                priority="low",
                title="Deduplicate URLs",
                message="The sitemap contains duplicate URL entries.",
                fix="Remove duplicate <loc> entries so each canonical URL appears only once.",
                where_to_fix="sitemap_xml",
            ),
            "file_size_limit": SitemapRecommendation(
                code="file_size_limit",
                priority="medium",
                title="Split oversized sitemap",
                message="Sitemap exceeds the 50 MB uncompressed size limit.",
                fix="Split into multiple sitemap files and reference them from a sitemap index file.",
                where_to_fix="cms",
            ),
            "url_count_limit": SitemapRecommendation(
                code="url_count_limit",
                priority="high",
                title="Split sitemap - too many URLs",
                message="Sitemap exceeds the 50,000 URL limit per file.",
                fix="Split into multiple sitemap files (max 50,000 URLs each) and create a sitemap index.",
                where_to_fix="cms",
            ),
        }
        
        for issue in issues:
            if issue.code in fix_map:
                recommendations.append(fix_map[issue.code])
        
        return recommendations


# Domain-level issues (robots.txt, missing sitemap entirely)
def generate_domain_issues(result: SiteDiscoveryResult, entries: List[SitemapEntry]) -> List[SitemapIssue]:
    """Generate domain-level issues (not tied to a specific sitemap file)."""
    issues = []
    domain = urlparse(result.robots.url).hostname or "unknown"
    
    if not entries:
        issues.append(SitemapIssue(
            code="sitemap_missing",
            severity="high",
            message="No sitemap files discovered",
            evidence=f"Checked robots.txt and common paths for {domain}; no valid sitemap found",
        ))
    else:
        issues.append(SitemapIssue(
            code="sitemap_present",
            severity="none",
            message=f"Found {len(entries)} sitemap file(s) with {sum(e.entries for e in entries)} total URLs",
            evidence=f"Discovered {len(entries)} sitemap(s)",
        ))
    
    # Check robots.txt for sitemap declaration
    if result.robots.exists and not result.robots.sitemap_references:
        issues.append(SitemapIssue(
            code="sitemap_not_in_robots",
            severity="medium",
            message="robots.txt does not declare a Sitemap directive",
            evidence=f"{result.robots.url} returned HTTP {result.robots.status_code} without Sitemap: directive",
        ))
    
    return issues


def generate_domain_recommendations(issues: List[SitemapIssue]) -> List[SitemapRecommendation]:
    """Generate domain-level recommendations."""
    recommendations = []
    
    fix_map = {
        "sitemap_missing": SitemapRecommendation(
            code="sitemap_missing",
            priority="high",
            title="Create and publish a sitemap",
            message="No sitemap was found for this domain.",
            fix="Create an XML sitemap at /sitemap.xml or /sitemap_index.xml and reference it in robots.txt.",
            where_to_fix="cms",
        ),
        "sitemap_not_in_robots": SitemapRecommendation(
            code="sitemap_not_in_robots",
            priority="medium",
            title="Add Sitemap directive to robots.txt",
            message="robots.txt exists but doesn't reference any sitemap.",
            fix="Add 'Sitemap: https://yourdomain.com/sitemap.xml' (or your sitemap index URL) to robots.txt.",
            where_to_fix="robots_txt",
        ),
    }
    
    for issue in issues:
        if issue.code in fix_map:
            recommendations.append(fix_map[issue.code])
    
    return recommendations
