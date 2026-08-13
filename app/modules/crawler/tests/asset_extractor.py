"""
Tests for the asset / resource extractor.

Crawls https://www.reddit.com, runs :func:`extract_resources`, and verifies
that the resulting :class:`ResourceFacts` dataclass captures images,
CSS, JavaScript, favicons, and other resource tags.

Results are saved to ``crawler/results/www.reddit.com/assets.json``.
"""
from collections import Counter

from app.modules.crawler.tests.conftest import RESULTS_DIR, get_crawl_result, save_result

from app.modules.crawler.extractors.asset_extractor import (
    ResourceFacts,
    extract_resources,
)


async def test_resource_extraction(crawl_result):
    """Verify ResourceFacts produced by extract_resources()."""
    document = crawl_result.document
    soup = document.soup
    base_url = document.base_url

    resource_facts: ResourceFacts = extract_resources(soup, base_url)

    # --- Core assertions ---
    assert isinstance(resource_facts, ResourceFacts)
    assert isinstance(resource_facts.resources, list)

    # --- Categorise resources by type ---
    type_counts = Counter(r.get("type", "unknown") for r in resource_facts.resources)

    # Most real websites have at least images or scripts.
    assert len(resource_facts.resources) > 0, (
        "Should find at least some resources (images, scripts, etc.)"
    )

    # --- Each resource should have required fields ---
    for resource in resource_facts.resources:
        assert "type" in resource
        assert "url" in resource
        assert "mime_type" in resource

    # --- Persist results ---
    payload = {
        "url": crawl_result.normalized_url,
        "total_resources": len(resource_facts.resources),
        "type_counts": dict(type_counts),
        "resources": resource_facts.resources,
    }
    save_result("assets.json", payload)
    print(f"  [PASS] asset extraction - total={len(resource_facts.resources)}, "
          f"types={dict(type_counts)}")


async def test_resource_categorisation(crawl_result):
    """Verify resources are correctly categorised by type."""
    document = crawl_result.document
    soup = document.soup
    base_url = document.base_url

    resource_facts = extract_resources(soup, base_url)
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
        "url": crawl_result.normalized_url,
        "total_resources": len(resource_facts.resources),
        "type_counts": dict(type_counts),
        "image_count": len(images),
    })
    print(f"  [PASS] resource categorisation - {len(images)} images, "
          f"types={sorted(found_types)}")
    print(f"results saved to: {RESULTS_DIR}/asset_categorisation.json and result is {crawl_result.normalized_url}")

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

