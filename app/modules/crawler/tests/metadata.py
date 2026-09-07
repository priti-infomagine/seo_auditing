"""
Tests for metadata extraction via the parser-backed pipeline.

Crawls https://www.reddit.com, parses HTML with ParserOrchestrator,
and verifies that metadata is captured correctly.

Results are saved to ``crawler/results/www.reddit.com/metadata.json``.
"""
from app.modules.crawler.tests.conftest import RESULTS_DIR, get_crawl_result, save_result

from app.modules.parser.services.parser_orchestrator import ParserOrchestrator


async def test_metadata_extraction(crawl_result):
    """Verify metadata produced by parser."""
    raw_html = crawl_result.document.raw_html
    url = crawl_result.normalized_url

    parser = ParserOrchestrator()
    parsed = parser.parse(html=raw_html, url=url)
    metadata = parsed.metadata

    # --- Title ---
    assert metadata.title, "Page should have a <title> tag"
    assert metadata.title_length == len(metadata.title), (
        "title_length should match len(title)"
    )

    # --- Meta description ---
    if metadata.meta_description:
        assert metadata.meta_description_length == len(metadata.meta_description), (
            "meta_description_length should match len(meta_description)"
        )

    # --- Types ---
    assert isinstance(metadata.open_graph, dict)
    assert isinstance(metadata.twitter, dict)
    assert isinstance(metadata.hreflang, list)

    # --- Persist results ---
    payload = {
        "url": url,
        "title": metadata.title,
        "title_length": metadata.title_length,
        "meta_description": metadata.meta_description,
        "meta_description_length": metadata.meta_description_length,
        "canonical": metadata.canonical,
        "robots_meta": next((t.content for t in (metadata.robots or []) if t.name == "robots"), ""),
        "googlebot": next((t.content for t in (metadata.robots or []) if t.name == "googlebot"), ""),
        "viewport": metadata.viewport,
        "charset": metadata.charset,
        "favicon": metadata.favicon_urls[0] if metadata.favicon_urls else "",
        "open_graph": dict(metadata.open_graph or {}),
        "twitter": dict(metadata.twitter or {}),
        "hreflang": [
            {"url": h.href, "hreflang": h.hreflang}
            for h in (metadata.hreflang or [])
        ],
    }
    save_result("metadata.json", payload)
    print(f"  [PASS] metadata extraction - title='{metadata.title[:50]}...', "
          f"og_tags={len(metadata.open_graph or {})}, "
          f"twitter_tags={len(metadata.twitter or {})}, "
          f"hreflang={len(metadata.hreflang or [])}")


async def test_metadata_types(crawl_result):
    """Verify the types and structure of metadata attributes."""
    raw_html = crawl_result.document.raw_html
    url = crawl_result.normalized_url

    parser = ParserOrchestrator()
    parsed = parser.parse(html=raw_html, url=url)
    metadata = parsed.metadata

    assert isinstance(metadata.title, str)
    assert isinstance(metadata.open_graph, dict)
    assert isinstance(metadata.twitter, dict)
    assert isinstance(metadata.hreflang, list)

    # hreflang entries should have url + hreflang keys
    for entry in (metadata.hreflang or []):
        assert hasattr(entry, "href"), "hreflang entry should have href"
        assert hasattr(entry, "hreflang"), "hreflang entry should have hreflang"

    save_result("metadata_types.json", {
        "url": url,
        "open_graph_count": len(metadata.open_graph or {}),
        "twitter_count": len(metadata.twitter or {}),
        "hreflang_count": len(metadata.hreflang or []),
        "hreflang_sample": [
            {"url": h.href, "hreflang": h.hreflang}
            for h in (metadata.hreflang or [])[:3]
        ],
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
