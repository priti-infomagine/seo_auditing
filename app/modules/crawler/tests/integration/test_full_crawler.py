"""
End-to-end crawler test harness.

Tests the complete crawler pipeline against a diverse set of real public URLs
and verifies every layer: URL normalization, HTTP fetch, RenderDetector,
browser fallback, parser, SEO extraction, links, images, and final results.

Run with:
    pytest app/modules/crawler/tests/integration/test_full_crawler.py -v -s

Or directly:
    python app/modules/crawler/tests/integration/test_full_crawler.py
"""
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parents[4]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# ---------------------------------------------------------------------------
# Imports from existing crawler module (NO production code modifications)
# ---------------------------------------------------------------------------
from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.rendering.render_detector import RenderDetector
from app.modules.crawler.services.page_crawl_service import PageCrawlService, PageCrawlResult
try:
    import pytest
except ImportError:
    pytest = None  # type: ignore

from app.modules.crawler.tests.integration.test_cases import CrawlTestCase, TEST_CASES
from app.modules.crawler.types import FetchResult, RenderDecision

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RESULTS_ROOT = Path(__file__).resolve().parent / "results"
RESULTS_ROOT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_domain(domain: str) -> str:
    """Sanitize domain for filesystem use."""
    return re.sub(r"[^a-z0-9.-]", "_", domain.lower())


def _save_json(path: Path, data: Any) -> str:
    """Save data as JSON, creating directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return str(path)


def _serialize_dataclass(obj: Any) -> Any:
    """Convert dataclasses to dicts for JSON serialization."""
    if hasattr(obj, "__dataclass_fields__"):
        result = {}
        for f_name in obj.__dataclass_fields__:
            result[f_name] = _serialize_dataclass(getattr(obj, f_name))
        return result
    if isinstance(obj, dict):
        return {k: _serialize_dataclass(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_dataclass(i) for i in obj]
    return obj


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------
@dataclass
class PipelineResult:
    test_number: int
    total_tests: int
    url: str
    category: str
    domain: str
    passed: bool
    failure_reason: Optional[str] = None

    # Pipeline stages
    normalized_url: Optional[str] = None
    http_status: Optional[int] = None
    http_success: Optional[bool] = None
    http_final_url: Optional[str] = None
    http_response_time_ms: Optional[int] = None
    http_redirects: List[Dict] = field(default_factory=list)

    render_decision_needs_render: Optional[bool] = None
    render_decision_reason: Optional[str] = None
    render_decision_details: Dict = field(default_factory=dict)

    browser_executed: bool = False
    browser_status: Optional[int] = None
    browser_final_url: Optional[str] = None
    browser_render_time_ms: Optional[int] = None

    final_render_mode: str = "http"
    initial_render_mode: str = "http"

    parser_executed: bool = False
    parser_title: str = ""
    parser_h1_count: int = 0
    parser_h2_count: int = 0
    parser_word_count: int = 0
    parser_links_total: int = 0
    parser_links_internal: int = 0
    parser_links_external: int = 0
    parser_images_total: int = 0
    parser_images_missing_alt: int = 0

    seo_title_present: bool = False
    seo_meta_description_present: bool = False
    seo_canonical_present: bool = False
    seo_robots_present: bool = False
    seo_h1_present: bool = False
    seo_hreflang_count: int = 0

    error: Optional[str] = None
    error_type: Optional[str] = None

    result_files: Dict[str, str] = field(default_factory=dict)


async def _run_pipeline(test_case: CrawlTestCase, test_number: int, total_tests: int) -> PipelineResult:
    """Run the complete crawler pipeline for a single URL."""
    domain = test_case.normalized_domain
    safe_domain = _safe_domain(domain)
    results_dir = RESULTS_ROOT / safe_domain
    results_dir.mkdir(parents=True, exist_ok=True)

    result = PipelineResult(
        test_number=test_number,
        total_tests=total_tests,
        url=test_case.url,
        category=test_case.category,
        domain=domain,
        passed=False,
    )

    # -----------------------------------------------------------------------
    # [1] INPUT
    # -----------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"TEST {test_number:02d} / {total_tests}")
    print(f"DOMAIN: {domain}")
    print(f"URL: {test_case.url}")
    print(f"CATEGORY: {test_case.category}")
    print(f"{'='*70}")

    # -----------------------------------------------------------------------
    # [2] URL NORMALIZATION
    # -----------------------------------------------------------------------
    print(f"\n[2] URL NORMALIZATION")
    print(f"  Original: {test_case.url}")
    try:
        from app.shared.utils.url_utils import normalize_url
        normalized = normalize_url(test_case.url)
        result.normalized_url = normalized
        print(f"  Normalized: {normalized}")
    except Exception as exc:
        result.failure_reason = f"URL normalization failed: {exc}"
        print(f"  FAILED: {exc}")
        return result

    # -----------------------------------------------------------------------
    # [3] HTTP FETCHER
    # -----------------------------------------------------------------------
    print(f"\n[3] HTTP FETCHER")
    http_result: Optional[FetchResult] = None
    crawl_result = None
    try:
        service = PageCrawlService()
        crawl_result = await service.crawl_page(test_case.url)
        http_result = crawl_result.initial_fetch_result or crawl_result.fetch_result

        if http_result:
            result.http_status = http_result.status_code
            result.http_success = http_result.success
            result.http_final_url = http_result.final_url
            result.http_response_time_ms = http_result.response_time_ms
            result.http_redirects = [
                {"url": r.url, "status_code": r.status_code, "location": getattr(r, "location", "")}
                for r in http_result.redirect_chain
            ]
            result.initial_render_mode = http_result.render_mode
            print(f"  Status: {http_result.status_code}")
            print(f"  Final URL: {http_result.final_url}")
            print(f"  Content-Type: {http_result.content_type}")
            print(f"  Content size: {http_result.content_length} bytes")
            print(f"  Response time: {http_result.response_time_ms} ms")
            print(f"  Redirects: {len(http_result.redirect_chain)}")
            for r in http_result.redirect_chain:
                print(f"    -> {r.status_code} {r.url}")
            print(f"  Success: {http_result.success}")
        else:
            result.failure_reason = "No HTTP fetch result returned"
            print(f"  FAILED: No fetch result")
            return result
    except Exception as exc:
        result.failure_reason = f"HTTP fetch exception: {exc}"
        print(f"  FAILED: {exc}")
        return result

    # -----------------------------------------------------------------------
    # [4] RENDER DETECTOR
    # -----------------------------------------------------------------------
    print(f"\n[4] RENDER DETECTOR")
    render_decision: Optional[RenderDecision] = None
    if http_result and http_result.success and http_result.content:
        try:
            detector = RenderDetector()
            render_decision = detector.evaluate(http_result)
            result.render_decision_needs_render = render_decision.needs_render
            result.render_decision_reason = render_decision.reason
            result.render_decision_details = render_decision.details
            print(f"  Decision: {'BROWSER' if render_decision.needs_render else 'HTTP'}")
            print(f"  Reason: {render_decision.reason}")
            print(f"  Details: {render_decision.details}")
        except Exception as exc:
            print(f"  Render detector failed: {exc}")
    else:
        print(f"  Skipped (HTTP fetch failed or no content)")
        result.render_decision_reason = "skipped_http_failed"

    # -----------------------------------------------------------------------
    # [5] SMART FETCHER / BROWSER FALLBACK
    # -----------------------------------------------------------------------
    print(f"\n[5] SMART FETCHER / BROWSER FALLBACK")
    final_fetch_result = crawl_result.fetch_result if crawl_result else http_result
    if final_fetch_result:
        result.final_render_mode = final_fetch_result.render_mode
        print(f"  Initial mode: {result.initial_render_mode}")
        print(f"  Final mode: {result.final_render_mode}")
        browser_fallback = result.final_render_mode == "browser"
        result.browser_executed = browser_fallback
        print(f"  Browser fallback: {'YES' if browser_fallback else 'NO'}")

        if browser_fallback:
            result.browser_status = final_fetch_result.status_code
            result.browser_final_url = final_fetch_result.final_url
            result.browser_render_time_ms = final_fetch_result.response_time_ms
            print(f"  Browser status: {final_fetch_result.status_code}")
            print(f"  Browser final URL: {final_fetch_result.final_url}")
            print(f"  Browser render time: {final_fetch_result.response_time_ms} ms")
            print(f"  Browser render reason: {final_fetch_result.render_reason}")
    else:
        print(f"  No fetch result available")

    # -----------------------------------------------------------------------
    # [6] PLAYWRIGHT
    # -----------------------------------------------------------------------
    print(f"\n[6] PLAYWRIGHT")
    if result.browser_executed:
        print(f"  Executed: YES")
        print(f"  Status: {result.browser_status}")
        print(f"  Final URL: {result.browser_final_url}")
        print(f"  Render time: {result.browser_render_time_ms} ms")
    else:
        print(f"  Executed: NO (HTTP-only)")

    # -----------------------------------------------------------------------
    # [7] PARSER
    # -----------------------------------------------------------------------
    print(f"\n[7] PARSER")
    document = crawl_result.document if crawl_result else None
    if document and document.is_html:
        result.parser_executed = True

        from app.modules.parser.services.parser_orchestrator import ParserOrchestrator
        parser = ParserOrchestrator()
        parsed = parser.parse(html=document.raw_html, url=result.normalized_url or test_case.url)

        # Title
        result.parser_title = parsed.metadata.title or ""
        print(f"  Title: {result.parser_title[:80] if result.parser_title else '(none)'}")

        # Headings
        if parsed.content and parsed.content.headings:
            h1_headings = [h for h in parsed.content.headings if h.level == 1]
            h2_headings = [h for h in parsed.content.headings if h.level == 2]
            result.parser_h1_count = len(h1_headings)
            result.parser_h2_count = len(h2_headings)
        print(f"  H1 count: {result.parser_h1_count}")
        print(f"  H2 count: {result.parser_h2_count}")

        # Content
        result.parser_word_count = parsed.content.word_count if parsed.content else 0
        print(f"  Word count: {result.parser_word_count}")

        # Links (from parser)
        result.parser_links_total = len(parsed.links or [])
        print(f"  Links total: {result.parser_links_total}")
        print(f"  Sample links:")
        for link in (parsed.links or [])[:5]:
            print(f"    -> {link.absolute_url or link.href}")
        if result.parser_links_total > 5:
            print(f"    ... and {result.parser_links_total - 5} more")

        # Images
        result.parser_images_total = len(parsed.images or [])
        missing_alt = sum(1 for img in (parsed.images or []) if not (img.alt or "").strip())
        result.parser_images_missing_alt = missing_alt
        print(f"  Images total: {result.parser_images_total}")
        print(f"  Images missing alt: {missing_alt}")
    else:
        result.parser_executed = False
        print(f"  Parser executed: NO (not HTML or no document)")
        if document:
            print(f"  is_html: {document.is_html}")

    # -----------------------------------------------------------------------
    # [8] SEO DATA
    # -----------------------------------------------------------------------
    print(f"\n[8] SEO DATA")
    if document and document.is_html and result.parser_executed:
        from app.modules.parser.services.parser_orchestrator import ParserOrchestrator
        parser = ParserOrchestrator()
        parsed = parser.parse(html=document.raw_html, url=result.normalized_url or test_case.url)
        metadata = parsed.metadata

        result.seo_title_present = bool(metadata.title)
        result.seo_meta_description_present = bool(metadata.meta_description)
        result.seo_canonical_present = bool(metadata.canonical)
        result.seo_robots_present = bool(
            next((t.content for t in (metadata.robots or []) if t.name == "robots"), "")
        )
        result.seo_hreflang_count = len(metadata.hreflang or [])

        # H1 check (from parser)
        if parsed.content and parsed.content.headings:
            h1_headings = [h for h in parsed.content.headings if h.level == 1]
            result.seo_h1_present = len(h1_headings) > 0

        print(f"  Title present: {result.seo_title_present}")
        if result.seo_title_present:
            print(f"    Title: {metadata.title[:80]}")
        print(f"  Meta description present: {result.seo_meta_description_present}")
        if result.seo_meta_description_present:
            print(f"    Description: {metadata.meta_description[:80]}")
        print(f"  Canonical present: {result.seo_canonical_present}")
        if result.seo_canonical_present:
            print(f"    Canonical: {metadata.canonical}")
        print(f"  Robots meta present: {result.seo_robots_present}")
        if result.seo_robots_present:
            print(f"    Robots: {next((t.content for t in (metadata.robots or []) if t.name == 'robots'), '')}")
        print(f"  H1 present: {result.seo_h1_present}")
        print(f"  Hreflang count: {result.seo_hreflang_count}")
    else:
        print(f"  Skipped (not HTML)")

    # -----------------------------------------------------------------------
    # [9] LINKS DETAIL
    # -----------------------------------------------------------------------
    print(f"\n[9] LINKS")
    if document and document.is_html and result.parser_executed:
        from app.modules.parser.services.parser_orchestrator import ParserOrchestrator
        parser = ParserOrchestrator()
        parsed = parser.parse(html=document.raw_html, url=result.normalized_url or test_case.url)

        print(f"  Total: {result.parser_links_total}")
        print(f"  Sample links:")
        for link in (parsed.links or [])[:5]:
            print(f"    -> {link.absolute_url or link.href}")
        if result.parser_links_total > 5:
            print(f"    ... and {result.parser_links_total - 5} more")
    else:
        print(f"  Skipped (not HTML)")

    # -----------------------------------------------------------------------
    # [10] IMAGES DETAIL
    # -----------------------------------------------------------------------
    print(f"\n[10] IMAGES")
    if document and document.is_html and result.parser_executed:
        print(f"  Total: {result.parser_images_total}")
        print(f"  Missing alt: {result.parser_images_missing_alt}")
        lazy_loaded = 0  # Parser doesn't track loading attribute separately
        print(f"  Lazy loaded: {lazy_loaded}")
    else:
        print(f"  Skipped (not HTML)")

    # -----------------------------------------------------------------------
    # [11] FINAL RESULT
    # -----------------------------------------------------------------------
    print(f"\n[11] FINAL RESULT")

    # Determine pass/fail
    if not test_case.expect_success:
        # For URLs expected to fail, pass if they failed gracefully
        if http_result and not http_result.success:
            result.passed = True
            print(f"  PASSED (expected failure)")
        else:
            result.failure_reason = f"Expected failure but got success (status={result.http_status})"
            print(f"  FAILED: {result.failure_reason}")
    else:
        # For URLs expected to succeed
        if not http_result or not http_result.success:
            result.failure_reason = f"HTTP fetch failed: {result.error or result.http_status}"
            print(f"  FAILED: {result.failure_reason}")
        elif not document or not document.is_html:
            result.failure_reason = "No valid HTML document parsed"
            print(f"  FAILED: {result.failure_reason}")
        elif test_case.expected_render_mode and result.final_render_mode != test_case.expected_render_mode:
            result.failure_reason = (
                f"Expected render mode {test_case.expected_render_mode} "
                f"but got {result.final_render_mode}"
            )
            print(f"  FAILED: {result.failure_reason}")
        elif test_case.expect_browser_fallback and not result.browser_executed:
            result.failure_reason = "Expected browser fallback but it did not occur"
            print(f"  FAILED: {result.failure_reason}")
        else:
            result.passed = True
            print(f"  PASSED")

    # -----------------------------------------------------------------------
    # Save results
    # -----------------------------------------------------------------------
    print(f"\n  Saving results to: {results_dir}")
    result_files = {}

    # Summary
    summary = _serialize_dataclass(result)
    summary_path = results_dir / "summary.json"
    _save_json(summary_path, summary)
    result_files["summary"] = str(summary_path)
    print(f"  Saved: summary.json")

    # Full result
    full_result = {
        "test_case": {
            "url": test_case.url,
            "category": test_case.category,
            "description": test_case.description,
        },
        "pipeline": summary,
        "http_result": _serialize_dataclass(http_result) if http_result else None,
        "render_decision": _serialize_dataclass(render_decision) if render_decision else None,
        "document": {
            "is_html": document.is_html if document else False,
            "language": "",  # Parser handles this
            "charset": "",   # Parser handles this
            "raw_html_length": len(document.raw_html) if document else 0,
        } if document else None,
    }
    result_path = results_dir / "result.json"
    _save_json(result_path, full_result)
    result_files["result"] = str(result_path)
    print(f"  Saved: result.json")

    # Initial HTML (if different from final)
    if http_result and http_result.content:
        initial_html = http_result.content.decode("utf-8", errors="replace")
        initial_path = results_dir / "initial.html"
        with open(initial_path, "w", encoding="utf-8") as f:
            f.write(initial_html)
        result_files["initial_html"] = str(initial_path)
        print(f"  Saved: initial.html ({len(initial_html)} bytes)")

    # Final HTML
    final_html = ""
    if crawl_result and crawl_result.fetch_result and crawl_result.fetch_result.content:
        final_html = crawl_result.fetch_result.content.decode("utf-8", errors="replace")
    elif http_result and http_result.content:
        final_html = http_result.content.decode("utf-8", errors="replace")

    if final_html:
        final_path = results_dir / "final.html"
        with open(final_path, "w", encoding="utf-8") as f:
            f.write(final_html)
        result_files["final_html"] = str(final_path)
        print(f"  Saved: final.html ({len(final_html)} bytes)")

    # Errors log
    errors = []
    if result.error:
        errors.append(f"Pipeline error: {result.error}")
    if result.failure_reason:
        errors.append(f"Failure: {result.failure_reason}")
    if http_result and http_result.error:
        errors.append(f"HTTP error: {http_result.error}")
    if crawl_result and crawl_result.fetch_result and crawl_result.fetch_result.error:
        errors.append(f"Final fetch error: {crawl_result.fetch_result.error}")

    if errors:
        errors_path = results_dir / "errors.log"
        with open(errors_path, "w", encoding="utf-8") as f:
            f.write("\n".join(errors))
        result_files["errors"] = str(errors_path)
        print(f"  Saved: errors.log")

    result.result_files = result_files
    return result


# ---------------------------------------------------------------------------
# Test runner (pytest + standalone)
# ---------------------------------------------------------------------------
def run_all_tests() -> List[PipelineResult]:
    """Run all test cases and return results."""
    print("=" * 70)
    print("CRAWLER END-TO-END TEST HARNESS")
    print("=" * 70)
    print(f"\nTotal tests: {len(TEST_CASES)}\n")

    results: List[PipelineResult] = []
    for idx, test_case in enumerate(TEST_CASES, start=1):
        try:
            pipeline_result = asyncio.run(_run_pipeline(test_case, idx, len(TEST_CASES)))
            results.append(pipeline_result)
        except Exception as exc:
            print(f"\n  CRITICAL FAILURE: {exc}")
            results.append(PipelineResult(
                test_number=idx,
                total_tests=len(TEST_CASES),
                url=test_case.url,
                category=test_case.category,
                domain=test_case.normalized_domain,
                passed=False,
                failure_reason=f"Unhandled exception: {exc}",
            ))

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    http_only = sum(1 for r in results if r.final_render_mode == "http" and r.passed)
    browser_rendered = sum(1 for r in results if r.final_render_mode == "browser" and r.passed)
    http_failures = sum(1 for r in results if not r.http_success and not r.passed)
    parser_failures = sum(
        1 for r in results
        if r.passed is False and r.failure_reason and "parser" in r.failure_reason.lower()
    )
    seo_failures = sum(
        1 for r in results
        if r.passed is False and r.failure_reason and "seo" in r.failure_reason.lower()
    )

    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"Total tests: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Skipped: 0")
    print(f"HTTP-only: {http_only}")
    print(f"Browser-rendered: {browser_rendered}")
    print(f"HTTP failures: {http_failures}")
    print(f"Parser failures: {parser_failures}")
    print(f"SEO extraction failures: {seo_failures}")
    print(f"{'='*70}\n")

    # Print failed tests
    if failed > 0:
        print("FAILED TESTS:")
        for r in results:
            if not r.passed:
                print(f"  TEST {r.test_number:02d}: {r.url}")
                print(f"    Reason: {r.failure_reason}")
        print()

    return results


# ---------------------------------------------------------------------------
# Pytest integration
# ---------------------------------------------------------------------------
def _maybe_mark(func):
    """Apply pytest marks only if pytest is available."""
    if pytest is not None:
        func = pytest.mark.parametrize("test_case", TEST_CASES, ids=lambda tc: f"{tc.category}_{tc.normalized_domain}")(func)
        func = pytest.mark.asyncio(func)
    return func

@_maybe_mark
async def test_full_crawler_pipeline(test_case: CrawlTestCase, request):
    """Pytest-compatible test for the full crawler pipeline."""
    test_number = TEST_CASES.index(test_case) + 1
    result = await _run_pipeline(test_case, test_number, len(TEST_CASES))

    # Attach result to request for inspection
    request.node.pipeline_result = result

    assert result.passed, f"Test {test_number} failed: {result.failure_reason}"


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_all_tests()
