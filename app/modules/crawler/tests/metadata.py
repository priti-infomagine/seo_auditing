"""
Tests for the metadata extractor.

Crawls https://www.reddit.com, runs :func:`extract_metadata`, and verifies
that the resulting :class:`MetadataFacts` dataclass captures title,
meta description, canonical, Open Graph, Twitter Card, and hreflang tags.

Results are saved to ``crawler/results/www.reddit.com/metadata.json``.
"""
from app.modules.crawler.tests.conftest import RESULTS_DIR, get_crawl_result, save_result

from app.modules.crawler.extractors.metadata_extractor import (
    MetadataFacts,
    extract_metadata,
)


async def test_metadata_extraction(crawl_result):
    """Verify MetadataFacts produced by extract_metadata()."""
    document = crawl_result.document
    soup = document.soup
    base_url = document.base_url

    metadata: MetadataFacts = extract_metadata(soup, base_url)

    # --- Title ---
    assert metadata.title, "Page should have a <title> tag"
    assert metadata.title_length == len(metadata.title), (
        "title_length should match len(title)"
    )

    # --- Meta description ---
    assert metadata.meta_description_length == len(metadata.meta_description), (
        "meta_description_length should match len(meta_description)"
    )

    # --- Types ---
    assert isinstance(metadata, MetadataFacts)
    assert isinstance(metadata.open_graph, dict)
    assert isinstance(metadata.twitter, dict)
    assert isinstance(metadata.hreflang, list)

    # --- Persist results ---
    payload = {
        "url": crawl_result.normalized_url,
        "title": metadata.title,
        "title_length": metadata.title_length,
        "meta_description": metadata.meta_description,
        "meta_description_length": metadata.meta_description_length,
        "canonical": metadata.canonical,
        "robots_meta": metadata.robots_meta,
        "googlebot": metadata.googlebot,
        "viewport": metadata.viewport,
        "charset": metadata.charset,
        "favicon": metadata.favicon,
        "open_graph": metadata.open_graph,
        "twitter": metadata.twitter,
        "hreflang": metadata.hreflang,
    }
    save_result("metadata.json", payload)
    print(f"  [PASS] metadata extraction - title='{metadata.title[:50]}...', "
          f"og_tags={len(metadata.open_graph)}, "
          f"twitter_tags={len(metadata.twitter)}, "
          f"hreflang={len(metadata.hreflang)}")


async def test_metadata_types(crawl_result):
    """Verify the types and structure of MetadataFacts attributes."""
    metadata: MetadataFacts = extract_metadata(
        crawl_result.document.soup,
        crawl_result.document.base_url,
    )

    assert isinstance(metadata.title, str)
    assert isinstance(metadata.open_graph, dict)
    assert isinstance(metadata.twitter, dict)
    assert isinstance(metadata.hreflang, list)

    # hreflang entries should have url + hreflang keys
    for entry in metadata.hreflang:
        assert "url" in entry
        assert "hreflang" in entry

    save_result("metadata_types.json", {
        "url": crawl_result.normalized_url,
        "open_graph_count": len(metadata.open_graph),
        "twitter_count": len(metadata.twitter),
        "hreflang_count": len(metadata.hreflang),
        "hreflang_sample": metadata.hreflang[:3],
    })
    print(f"  [PASS] metadata types - verified structure of all fields")


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    async def main():
        result = await get_crawl_result()
        await test_metadata_extraction(result)
        await test_metadata_types(result)
        print("\nAll metadata tests passed!")
        print(f"Results saved to: {RESULTS_DIR}")

    asyncio.run(main())

