"""
Tests for the document extractor.

Crawls https://www.reddit.com, runs :func:`extract_document` (via
``PageCrawlService.crawl_page``), and verifies that the resulting
:class:`DocumentFacts` dataclass contains valid HTML parsing metadata.

Results are saved to ``crawler/results/www.reddit.com/document.json``.
"""
from app.modules.crawler.tests.conftest import RESULTS_DIR, get_crawl_result, save_result

from app.modules.crawler.extractors.document_extractor import (
    DocumentFacts,
    extract_document,
)


async def test_document_extraction(crawl_result):
    """Verify DocumentFacts produced by the page-crawl pipeline."""
    document: DocumentFacts = crawl_result.document

    # --- Core assertions ---
    assert document.is_html is True, "Page should be parsed as valid HTML"
    assert document.doctype, "Doctype should be present"
    assert document.base_url == crawl_result.normalized_url, "Base URL mismatch"
    assert document.raw_html, "Raw HTML should be non-empty"

    # --- BeautifulSoup soup sanity checks ---
    assert document.soup is not None, "BeautifulSoup soup should be populated"
    html_tag = document.soup.find("html")
    assert html_tag is not None, "Should find <html> tag in soup"

    # --- Persist results ---
    payload = {
        "test_url": crawl_result.normalized_url,
        "final_url": crawl_result.fetch_result.final_url,
        "status_code": crawl_result.fetch_result.status_code,
        "doctype": document.doctype,
        "is_html": document.is_html,
        "language": document.language,
        "charset": document.charset,
        "base_url": document.base_url,
        "raw_html_length": len(document.raw_html),
        "html_tag_found": html_tag is not None,
    }
    save_result("document.json", payload)
    print(f"  [PASS] document extraction - doctype={document.doctype}, "
          f"is_html={document.is_html}, charset={document.charset}")


async def test_extract_document_directly(crawl_result):
    """Call extract_document() directly with the fetched HTML."""
    html = crawl_result.document.raw_html
    url = crawl_result.normalized_url

    doc = extract_document(html, url)

    assert doc.is_html is True
    # assert doc.doctype == "html"
    assert doc.base_url == url
    assert doc.raw_html == html
    assert doc.soup is not None

    payload = {
        "url": url,
        "doctype": doc.doctype,
        "is_html": doc.is_html,
        "language": doc.language,
        "charset": doc.charset,
    }
    save_result("document_direct.json", payload)
    print(f"  [PASS] extract_document() direct - doctype={doc.doctype}")


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    async def main():
        result = await get_crawl_result()
        await test_document_extraction(result)
        await test_extract_document_directly(result)
        print("\nAll document tests passed!")
        print(f"Results saved to: {RESULTS_DIR}")

    asyncio.run(main())

