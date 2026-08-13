"""
Tests for the technical extractor and technical-analysis service.

Crawls https://www.reddit.com, runs :func:`extract_technical` to build a
:class:`TechnicalFacts` dataclass, then passes it through
:class:`TechnicalAnalysisService` to verify checksum generation, HTTPS
detection, and security-header classification.

Results are saved to ``crawler/results/www.reddit.com/technical.json``.
"""
from app.modules.crawler.tests.conftest import RESULTS_DIR, get_crawl_result, save_result
from app.modules.crawler.extractors.technical_extractor import (
    TechnicalFacts,
    extract_technical,
)
from app.modules.crawler.services.technical_analysis_service import (
    TechnicalAnalysisService,
    TechnicalAnalysisResult,
)
from app.shared.utils.checksum import generate_checksum


def _redirects_to_dicts(chain):
    """Convert RedirectInfo dataclasses (or dicts) to plain dicts."""
    result = []
    for r in chain:
        if hasattr(r, "__dict__"):
            result.append(r.__dict__)
        elif hasattr(r, "_asdict"):
            result.append(r._asdict())
        else:
            result.append(r)
    return result


async def test_technical_extraction(crawl_result):
    """Verify TechnicalFacts produced by extract_technical()."""
    document = crawl_result.document
    fetch = crawl_result.fetch_result

    technical: TechnicalFacts = extract_technical(
        status_code=fetch.status_code,
        headers=fetch.headers,
        content_length=fetch.content_length,
        response_time_ms=fetch.response_time_ms,
        redirects=_redirects_to_dicts(fetch.redirect_chain),
        soup=document.soup,
        raw_html=document.raw_html,
    )

    # --- Core assertions ---
    assert isinstance(technical, TechnicalFacts)
    assert technical.status_code == fetch.status_code
    assert technical.content_type, "Content-Type should be detected"
    assert technical.content_length > 0, "Content length should be positive"
    assert technical.response_time_ms >= 0
    assert isinstance(technical.headers, dict)
    assert isinstance(technical.security, dict)
    assert isinstance(technical.performance, dict)
    assert isinstance(technical.accessibility, dict)
    assert isinstance(technical.json_ld, list)

    # --- Performance metrics ---
    assert "load_time_ms" in technical.performance
    assert "script_count" in technical.performance

    # --- Accessibility metrics ---
    assert "images" in technical.accessibility
    assert "total" in technical.accessibility["images"]

    # --- Persist results ---
    payload = {
        "url": crawl_result.normalized_url,
        "status_code": technical.status_code,
        "content_type": technical.content_type,
        "content_length": technical.content_length,
        "response_time_ms": technical.response_time_ms,
        "headers": technical.headers,
        "redirects": technical.redirects,
        "security": technical.security,
        "performance": technical.performance,
        "accessibility": technical.accessibility,
        "json_ld": technical.json_ld,
    }
    save_result("technical.json", payload)
    print(f"  [PASS] technical extraction - status={technical.status_code}, "
          f"type={technical.content_type}, "
          f"scripts={technical.performance.get('script_count', 'N/A')}, "
          f"json_ld={len(technical.json_ld)}")


async def test_technical_analysis_service(crawl_result):
    """Pass TechnicalFacts through TechnicalAnalysisService.analyze()."""
    document = crawl_result.document
    fetch = crawl_result.fetch_result

    technical = extract_technical(
        status_code=fetch.status_code,
        headers=fetch.headers,
        content_length=fetch.content_length,
        response_time_ms=fetch.response_time_ms,
        redirects=_redirects_to_dicts(fetch.redirect_chain),
        soup=document.soup,
        raw_html=document.raw_html,
    )

    service = TechnicalAnalysisService()
    analysis: TechnicalAnalysisResult = await service.analyze(
        technical=technical,
        content_bytes=fetch.content,
        url=crawl_result.normalized_url,
    )

    # --- Assertions ---
    assert isinstance(analysis, TechnicalAnalysisResult)
    assert analysis.status_code == fetch.status_code
    assert analysis.checksum is not None, "Checksum should be generated from content"
    assert analysis.is_https is True, "URL should be HTTPS"

    # Verify checksum is correct
    expected_checksum = generate_checksum(fetch.content)
    assert analysis.checksum == expected_checksum, "Checksum mismatch"

    # Security should include is_https flag
    assert "is_https" in analysis.security
    assert analysis.security["is_https"] is True

    save_result("technical_analysis.json", {
        "url": crawl_result.normalized_url,
        "status_code": analysis.status_code,
        "content_type": analysis.content_type,
        "content_length": analysis.content_length,
        "response_time_ms": analysis.response_time_ms,
        "is_https": analysis.is_https,
        "checksum": analysis.checksum,
        "security": analysis.security,
        "performance": analysis.performance,
        "accessibility": analysis.accessibility,
        "json_ld_count": len(analysis.json_ld),
    })
    print(f"  [PASS] technical analysis - checksum={analysis.checksum[:16]}..., "
          f"https={analysis.is_https}")


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    async def main():
        result = await get_crawl_result()
        await test_technical_extraction(result)
        await test_technical_analysis_service(result)
        print("\nAll technical tests passed!")
        print(f"Results saved to: {RESULTS_DIR}")

    asyncio.run(main())

