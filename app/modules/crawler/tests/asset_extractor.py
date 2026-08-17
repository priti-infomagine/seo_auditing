"""
Tests for resource extraction via the parser-backed pipeline.

Crawls https://www.reddit.com, parses HTML with ParserOrchestrator,
and verifies that resources are captured correctly.

Results are saved to ``crawler/results/www.reddit.com/assets.json``.
"""
from collections import Counter

from app.modules.crawler.tests.conftest import RESULTS_DIR, get_crawl_result, save_result

from app.modules.parser.services.parser_orchestrator import ParserOrchestrator
from app.modules.crawler.extractors.seo_fact_extractor import parsed_document_to_page_facts
from app.modules.crawler.extractors.asset_extractor import ResourceFacts


async def test_resource_extraction(crawl_result):
    """Verify ResourceFacts produced by parser-backed bridge."""
    raw_html = crawl_result.document.raw_html
    url = crawl_result.normalized_url

    parser = ParserOrchestrator()
    parsed = parser.parse(html=raw_html, url=url)
    page_facts = parsed_document_to_page_facts(parsed, raw_html=raw_html)
    resource_facts: ResourceFacts = page_facts.resources

    # --- Core assertions ---
    assert isinstance(resource_facts, ResourceFacts)
    assert isinstance(resource_facts.resources, list)

    # --- Categorise resources by type ---
    type_counts = Counter(r.get("type", "unknown") for r in resource_facts.resources)

    # --- Each resource should have required fields ---
    for resource in resource_facts.resources:
        assert "type" in resource
        assert "url" in resource
        assert "mime_type" in resource

    # --- Persist results ---
    payload = {
        "url": url,
        "total_resources": len(resource_facts.resources),
        "type_counts": dict(type_counts),
        "resources": resource_facts.resources,
    }
    save_result("assets.json", payload)
    print(f"  [PASS] resource extraction - total={len(resource_facts.resources)}, "
          f"types={dict(type_counts)}")


async def test_resource_categorisation(crawl_result):
    """Verify resources are correctly categorised by type."""
    raw_html = crawl_result.document.raw_html
    url = crawl_result.normalized_url

    parser = ParserOrchestrator()
    parsed = parser.parse(html=raw_html, url=url)
    page_facts = parsed_document_to_page_facts(parsed, raw_html=raw_html)
    resource_facts = page_facts.resources

    type_counts = Counter(r.get("type", "unknown") for r in resource_facts.resources)

    # Verify known types present
    known_types = {"image", "css", "javascript", "favicon", "iframe", "video", "audio"}
    found_types = set(type_counts.keys())
    assert found_types.issubset(known_types), (
        f"Unexpected resource types: {found_types - known_types}"
    )

    # Images should have alt / width / height fields
    images = [r for r in resource_facts.resources if r["type"] == "image"]
    for img in images:
        assert "alt" in img
        assert "width" in img
        assert "height" in img
        assert "loading" in img

    save_result("asset_categorisation.json", {
        "url": url,
        "total_resources": len(resource_facts.resources),
        "type_counts": dict(type_counts),
        "image_count": len(images),
    })
    print(f"  [PASS] resource categorisation - {len(images)} images, "
          f"types={sorted(found_types)}")
    print(f"results saved to: {RESULTS_DIR}/asset_categorisation.json and result is {url}")


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    async def main():
        result = await get_crawl_result()
        await test_resource_extraction(result)
        await test_resource_categorisation(result)
        print("\nAll asset-extractor tests passed!")
        print(f"Results saved to: {RESULTS_DIR}")
        print(f"result is : {result}")

    asyncio.run(main())
