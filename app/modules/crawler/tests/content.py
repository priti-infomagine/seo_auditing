"""
Tests for the content extractor.

Crawls https://cyfuture.com, runs :func:`extract_content`, and verifies
that the resulting :class:`ContentFacts` dataclass captures meaningful
page-content metrics (text, word count, headings, etc.).

Results are saved to ``crawler/results/cyfuture.com/content.json``.
"""
from conftest import RESULTS_DIR, get_crawl_result, save_result

from app.modules.crawler.extractors.content_extractor import (
    ContentFacts,
    extract_content,
)


async def test_content_extraction(crawl_result):
    """Verify ContentFacts produced by extract_content()."""
    document = crawl_result.document
    raw_html = document.raw_html
    soup = document.soup

    content: ContentFacts = extract_content(soup, raw_html)

    # --- Core assertions ---
    assert content.word_count > 0, "Word count should be positive for a real page"
    assert len(content.text) > 0, "Extracted text should be non-empty"
    assert content.sentence_count > 0, "Sentence count should be positive"
    assert content.paragraph_count > 0, "Should have at least one <p> tag"
    assert content.content_hash, "Content hash should be generated"
    assert content.text_html_ratio > 0.0, "Text-to-HTML ratio should be positive"

    # --- Headings ---
    assert isinstance(content.headings, dict)
    total_headings = sum(len(v) for v in content.headings.values())
    assert total_headings > 0, "Should have at least one heading"

    # --- Forms & buttons ---
    assert content.forms >= 0
    assert content.buttons >= 0

    # --- Persist results ---
    payload = {
        "url": crawl_result.normalized_url,
        "text_length": len(content.text),
        "word_count": content.word_count,
        "sentence_count": content.sentence_count,
        "paragraph_count": content.paragraph_count,
        "headings": content.headings,
        "forms": content.forms,
        "buttons": content.buttons,
        "content_hash": content.content_hash,
        "text_html_ratio": content.text_html_ratio,
        "total_headings": total_headings,
    }
    save_result("content.json", payload)
    print(f"  [PASS] content extraction - words={content.word_count}, "
          f"paragraphs={content.paragraph_count}, ratio={content.text_html_ratio}")


async def test_content_hash_is_deterministic(crawl_result):
    """Running extract_content twice on the same HTML yields the same hash."""
    soup = crawl_result.document.soup
    raw_html = crawl_result.document.raw_html

    first = extract_content(soup, raw_html)
    second = extract_content(soup, raw_html)

    assert first.content_hash == second.content_hash, (
        "Content hash should be deterministic"
    )

    payload = {
        "url": crawl_result.normalized_url,
        "content_hash": first.content_hash,
        "is_deterministic": first.content_hash == second.content_hash,
    }
    save_result("content_hash.json", payload)
    print(f"  [PASS] content hash deterministic - {first.content_hash}")


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

