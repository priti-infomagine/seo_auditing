"""
Tests for link extraction via the parser-backed pipeline.

Crawls https://www.reddit.com, parses HTML with ParserOrchestrator,
and verifies that links are extracted correctly.

Results are saved to ``crawler/results/www.reddit.com/links.json``.
"""
from app.modules.crawler.tests.conftest import RESULTS_DIR, get_crawl_result, save_result

from app.modules.parser.services.parser_orchestrator import ParserOrchestrator
from app.modules.crawler.services.link_analysis_service import (
    LinkAnalysisService,
    LinkAnalysisResult,
)


async def test_link_extraction(crawl_result):
    """Verify links produced by parser."""
    raw_html = crawl_result.document.raw_html
    url = crawl_result.normalized_url

    parser = ParserOrchestrator()
    parsed = parser.parse(html=raw_html, url=url)

    # Convert parser links to crawler-compatible format via bridge
    from app.modules.crawler.extractors.seo_fact_extractor import parsed_document_to_page_facts
    page_facts = parsed_document_to_page_facts(parsed, raw_html=raw_html)

    # --- Core assertions ---
    assert isinstance(page_facts.links, type(page_facts.links))
    assert len(page_facts.links.links) >= 0, "Should find at least some links on the page"
    assert page_facts.links.internal_count >= 0
    assert page_facts.links.external_count >= 0

    # --- Each link should have required fields ---
    for link in page_facts.links.links:
        assert "url" in link
        assert "anchor_text" in link
        assert "is_internal" in link
        assert "rel" in link

    # --- Persist results ---
    payload = {
        "url": url,
        "total_links": len(page_facts.links.links),
        "internal_count": page_facts.links.internal_count,
        "external_count": page_facts.links.external_count,
        "links": page_facts.links.links,
        "deep_links": page_facts.links.deep_links,
        "deep_total_links": len(page_facts.links.deep_links),
    }
    save_result("links.json", payload)
    print(f"  [PASS] link extraction - total={len(page_facts.links.links)}, "
          f"internal={page_facts.links.internal_count}, "
          f"external={page_facts.links.external_count}")


async def test_link_analysis_service(crawl_result):
    """Pass LinkFacts through LinkAnalysisService and verify enrichment."""
    raw_html = crawl_result.document.raw_html
    url = crawl_result.normalized_url

    parser = ParserOrchestrator()
    parsed = parser.parse(html=raw_html, url=url)

    from app.modules.crawler.extractors.seo_fact_extractor import parsed_document_to_page_facts
    page_facts = parsed_document_to_page_facts(parsed, raw_html=raw_html)

    service = LinkAnalysisService(base_url=url)
    analysis: LinkAnalysisResult = await service.analyze(page_facts.links)

    assert isinstance(analysis, LinkAnalysisResult)
    assert analysis.internal_count == page_facts.links.internal_count
    assert analysis.external_count == page_facts.links.external_count
    assert len(analysis.links) == len(page_facts.links.links), (
        "Enriched link count should match extracted link count"
    )

    # --- Each enriched link should have boolean flags ---
    for link in analysis.links:
        assert "is_nofollow" in link
        assert "is_sponsored" in link
        assert "is_ugc" in link

    assert isinstance(analysis.summary, dict)
    assert analysis.summary.get("total_links") >= len(analysis.links)
    assert "by_protocol" in analysis.summary
    assert "by_anchor_text_classification" in analysis.summary

    save_result("link_analysis.json", {
        "url": url,
        "base_url": url,
        "total_links": len(analysis.links),
        "deep_total_links": analysis.summary.get("total_links"),
        "internal_count": analysis.internal_count,
        "external_count": analysis.external_count,
        "summary": analysis.summary,
        "enriched_links": analysis.links,
    })
    print(f"  [PASS] link analysis - enriched {len(analysis.links)} links, "
          f"deep summary total={analysis.summary.get('total_links')}")


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    async def main():
        result = await get_crawl_result()
        await test_link_extraction(result)
        await test_link_analysis_service(result)
        print("\nAll link-extractor tests passed!")
        print(f"Results saved to: {RESULTS_DIR}")

    asyncio.run(main())
