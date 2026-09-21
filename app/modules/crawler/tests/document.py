"""
Tests for document facts via the parser-backed pipeline.

Crawls https://www.reddit.com, creates DocumentFacts via create_document_facts(),
then verifies the resulting DocumentFacts dataclass contains valid metadata.

Results are saved to ``crawler/results/www.reddit.com/document.json``.
"""
from app.modules.crawler.tests.conftest import RESULTS_DIR, get_crawl_result, save_result

from app.modules.crawler.extractors.document_extractor import (
    DocumentFacts,
    create_document_facts,
)
from app.modules.parser.services.parser_orchestrator import ParserOrchestrator


async def test_document_facts_via_parser(crawl_result):
    """Verify DocumentFacts produced by create_document_facts + parser."""
    document: DocumentFacts = crawl_result.document

    # --- Core assertions ---
    assert document.is_html is True, "Page should be parsed as valid HTML"
    assert document.base_url == crawl_result.normalized_url, "Base URL mismatch"
    assert document.raw_html, "Raw HTML should be non-empty"
    assert document.soup is None, "soup should be None (parser module handles DOM)"

    # --- Parser should produce metadata from the same raw_html ---
    parser = ParserOrchestrator()
    parsed = parser.parse(html=document.raw_html, url=crawl_result.normalized_url)
    assert parsed.document.url == crawl_result.normalized_url
    assert parsed.content.text

    # --- Persist results ---
    payload = {
        "test_url": crawl_result.normalized_url,
        "final_url": crawl_result.fetch_result.final_url,
        "status_code": crawl_result.fetch_result.status_code,
        "is_html": document.is_html,
        "base_url": document.base_url,
        "raw_html_length": len(document.raw_html),
        "parser_title": parsed.metadata.title,
        "parser_word_count": parsed.content.word_count,
    }
    save_result("document.json", payload)
    print(f"  [PASS] document facts - is_html={document.is_html}, "
          f"raw_html_length={len(document.raw_html)}")


async def test_create_document_facts_directly(crawl_result):
    """Call create_document_facts() directly with the fetched HTML."""
    html = crawl_result.document.raw_html
    url = crawl_result.normalized_url

    doc = create_document_facts(html, url)

    assert doc.is_html is True
    assert doc.base_url == url
    assert doc.raw_html == html
    assert doc.soup is None

    payload = {
        "url": url,
        "is_html": doc.is_html,
        "base_url": doc.base_url,
        "raw_html_length": len(doc.raw_html),
    }
    save_result("document_direct.json", payload)
    print(f"  [PASS] create_document_facts() direct - is_html={doc.is_html}")


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    async def main():
        result = await get_crawl_result()
        await test_document_facts_via_parser(result)
        await test_create_document_facts_directly(result)
        print("\nAll document tests passed!")
        print(f"Results saved to: {RESULTS_DIR}")

    asyncio.run(main())
