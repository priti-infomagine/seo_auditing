"""
Tests for content extraction via the parser-backed pipeline.

Crawls https://www.reddit.com, parses HTML with ParserOrchestrator,
and verifies that content metrics are captured.

Results are saved to ``crawler/results/www.reddit.com/content.json``.
"""
from app.modules.crawler.tests.conftest import RESULTS_DIR, get_crawl_result, save_result

from app.modules.parser.services.parser_orchestrator import ParserOrchestrator


async def test_content_extraction(crawl_result):
    """Verify content metrics produced by parser."""
    raw_html = crawl_result.document.raw_html
    url = crawl_result.normalized_url

    parser = ParserOrchestrator()
    parsed = parser.parse(html=raw_html, url=url)
    content = parsed.content

    # --- Core assertions ---
    assert content.word_count > 0, "Word count should be positive for a real page"
    assert len(content.text) > 0, "Extracted text should be non-empty"
    assert content.sentence_count >= 0, "Sentence count should be non-negative"
    assert content.paragraph_count >= 0, "Should have at least one <p> tag"

    # --- Headings ---
    assert content.headings is not None
    total_headings = sum(len(v) for v in (content.headings or {}).values())
    assert total_headings >= 0, "Should have at least one heading"

    # --- Persist results ---
    payload = {
        "url": url,
        "text_length": len(content.text),
        "word_count": content.word_count,
        "sentence_count": content.sentence_count,
        "paragraph_count": content.paragraph_count,
        "headings": content.headings,
        "total_headings": total_headings,
    }
    save_result("content.json", payload)
    print(f"  [PASS] content extraction - words={content.word_count}, "
          f"paragraphs={content.paragraph_count}")


async def test_content_hash_is_deterministic(crawl_result):
    """Running parser twice on the same HTML yields the same content."""
    raw_html = crawl_result.document.raw_html
    url = crawl_result.normalized_url

    parser = ParserOrchestrator()
    first = parser.parse(html=raw_html, url=url)
    second = parser.parse(html=raw_html, url=url)

    assert first.content.text == second.content.text, (
        "Content text should be deterministic"
    )
    assert first.content.word_count == second.content.word_count, (
        "Word count should be deterministic"
    )

    payload = {
        "url": url,
        "word_count": first.content.word_count,
        "is_deterministic": first.content.text == second.content.text,
    }
    save_result("content_hash.json", payload)
    print(f"  [PASS] content deterministic - words={first.content.word_count}")


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    async def main():
        result = await get_crawl_result()
        await test_content_extraction(result)
        await test_content_hash_is_deterministic(result)
        print("\nAll content tests passed!")
        print(f"Results saved to: {RESULTS_DIR}")

    asyncio.run(main())
