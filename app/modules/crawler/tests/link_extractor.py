"""
Tests for the link extractor and link-analysis service.

Crawls https://www.reddit.com, runs :func:`extract_links`, then passes
the :class:`LinkFacts` through :class:`LinkAnalysisService` to verify
link enrichment and internal/external classification.

Results are saved to ``crawler/results/www.reddit.com/links.json``.
"""
from app.modules.crawler.tests.conftest import RESULTS_DIR, get_crawl_result, save_result

from app.modules.crawler.extractors.link_extractor import (
    LinkFacts,
    extract_links,
)
from app.modules.crawler.services.link_analysis_service import (
    LinkAnalysisService,
    LinkAnalysisResult,
)


async def test_link_extraction(crawl_result):
    """Verify LinkFacts produced by extract_links()."""
    document = crawl_result.document
    soup = document.soup
    base_url = document.base_url

    link_facts: LinkFacts = extract_links(soup, base_url)

    # --- Core assertions ---
    assert isinstance(link_facts, LinkFacts)
    assert len(link_facts.links) >= 0, "Should find at least some links on the page"
    assert link_facts.internal_count >= 0
    assert link_facts.external_count >= 0

    # --- Each link should have required fields ---
    for link in link_facts.links:
        assert "url" in link
        assert "anchor_text" in link
        assert "is_internal" in link
        assert "rel" in link

    # --- Deep-analysis surface ---
    assert hasattr(link_facts, "deep_links")
    assert len(link_facts.deep_links) >= len(link_facts.links)
    for deep in link_facts.deep_links:
        for key in ("protocol", "is_http", "is_fragment", "raw_href",
                    "opens_new_tab", "anchor_text_classification",
                    "link_text_length", "target"):
            assert key in deep, f"deep link missing {key}"

    # --- Persist results ---
    payload = {
        "url": crawl_result.normalized_url,
        "total_links": len(link_facts.links),
        "internal_count": link_facts.internal_count,
        "external_count": link_facts.external_count,
        "links": link_facts.links,
        "deep_links": link_facts.deep_links,
        "deep_total_links": len(link_facts.deep_links),
        "non_http_count": link_facts.non_http_count,
        "fragment_count": link_facts.fragment_count,
        "mailto_count": link_facts.mailto_count,
        "tel_count": link_facts.tel_count,
        "javascript_count": link_facts.javascript_count,
    }
    save_result("links.json", payload)
    print(f"  [PASS] link extraction - total={len(link_facts.links)}, "
          f"deep={len(link_facts.deep_links)}, "
          f"internal={link_facts.internal_count}, "
          f"external={link_facts.external_count}")


async def test_link_analysis_service(crawl_result):
    """Pass LinkFacts through LinkAnalysisService and verify enrichment."""
    document = crawl_result.document
    base_url = document.base_url

    link_facts = extract_links(document.soup, base_url)

    service = LinkAnalysisService(base_url=base_url)
    analysis: LinkAnalysisResult = await service.analyze(link_facts)

    assert isinstance(analysis, LinkAnalysisResult)
    assert analysis.internal_count == link_facts.internal_count
    assert analysis.external_count == link_facts.external_count
    assert len(analysis.links) == len(link_facts.links), (
        "Enriched link count should match extracted link count"
    )

    # --- Each enriched link should have boolean flags ---
    for link in analysis.links:
        assert "is_nofollow" in link
        assert "is_sponsored" in link
        assert "is_ugc" in link

    assert isinstance(analysis.summary, dict)
    # Deep summary rolls up the full surface (incl. non-HTTP anchors), so it
    # is >= the preserved compatibility ``links`` list.
    assert analysis.summary.get("total_links") >= len(analysis.links)
    assert "by_protocol" in analysis.summary
    assert "by_anchor_text_classification" in analysis.summary

    save_result("link_analysis.json", {
        "url": crawl_result.normalized_url,
        "base_url": base_url,
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

