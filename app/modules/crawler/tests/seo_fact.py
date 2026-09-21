"""
Tests for the SEO-fact extractor bridge.

Crawls https://www.reddit.com, parses the raw HTML through
:class:`ParserService` to obtain a ``ParsedDocument``, then verifies:

* :func:`extract_seo_facts` - produces a flat rule-engine-compatible dict.
* :func:`parsed_document_to_page_facts` - produces a crawler
  :class:`PageFacts` dataclass from the parsed document.

Results are saved to ``crawler/results/www.reddit.com/seo_fact.json``.
"""
from app.modules.crawler.tests.conftest import RESULTS_DIR, get_crawl_result, save_result

from app.modules.parser.services.parser_orchestrator import ParserOrchestrator
from app.modules.crawler.extractors.seo_fact_extractor import (
    extract_seo_facts,
    parsed_document_to_page_facts,
)
from app.modules.crawler.services.page_extraction_service import PageFacts


def _redirects_to_dicts(chain):
    """Convert RedirectInfo dataclasses (or dicts) to plain dicts."""
    result = []
    for r in chain:
        if hasattr(r, "__dict__"):
            result.append(r.__dict__)
        elif hasattr(r, "_asdict"):
            result.append(r._asdict())
        else:
            result.append(r)
    return result


async def test_seo_facts_extraction(crawl_result):
    """Verify extract_seo_facts() produces a valid rule-engine dict."""
    html = crawl_result.document.raw_html
    url = crawl_result.normalized_url

    parser = ParserOrchestrator()
    parsed = parser.parse(html=html, url=url)

    facts = extract_seo_facts(parsed)

    # --- Core assertions ---
    assert isinstance(facts, dict)
    assert "basic" in facts, "Should have 'basic' section"
    assert "headings" in facts, "Should have 'headings' section"
    assert "seo" in facts, "Should have 'seo' section"
    assert "social" in facts, "Should have 'social' section"
    assert "content" in facts, "Should have 'content' section"
    assert "links" in facts, "Should have 'links' section"
    assert "images" in facts, "Should have 'images' section"
    assert "structured_data" in facts, "Should have 'structured_data' section"

    # Basic section should have url and title
    assert facts["basic"]["url"] == url
    assert isinstance(facts["basic"]["title"], str)

    # Social section should have open_graph and twitter_cards
    assert "open_graph" in facts["social"]
    assert "twitter_cards" in facts["social"]

    # --- Persist results ---
    save_result("seo_fact.json", facts)
    print(f"  [PASS] SEO facts extraction - keys={list(facts.keys())}, "
          f"title='{facts['basic']['title'][:40]}...', "
          f"og_tags={len(facts['social']['open_graph']['tags'])}, "
          f"links={len(facts['links'])}, "
          f"images={len(facts['images'])}")


async def test_page_facts_from_parsed_document(crawl_result):
    """Verify parsed_document_to_page_facts() produces PageFacts."""
    html = crawl_result.document.raw_html
    url = crawl_result.normalized_url
    fetch = crawl_result.fetch_result

    parser = ParserOrchestrator()
    parsed = parser.parse(html=html, url=url)

    page_facts: PageFacts = parsed_document_to_page_facts(
        parsed,
        status_code=fetch.status_code,
        headers=fetch.headers,
        content_length=fetch.content_length,
        response_time_ms=fetch.response_time_ms,
        redirects=_redirects_to_dicts(fetch.redirect_chain),
    )

    # --- Assertions ---
    assert page_facts is not None
    assert hasattr(page_facts, "document")
    assert hasattr(page_facts, "content")
    assert hasattr(page_facts, "metadata")
    assert hasattr(page_facts, "links")
    assert hasattr(page_facts, "resources")
    assert hasattr(page_facts, "technical")

    # Technical facts should carry over from fetch context
    assert page_facts.technical.status_code == fetch.status_code
    assert page_facts.technical.content_length == fetch.content_length

    # Document facts
    # assert page_facts.document.doctype == "html"

    save_result("page_facts_from_parsed.json", {
        "url": url,
        "doctype": page_facts.document.doctype,
        "language": page_facts.document.language,
        "charset": page_facts.document.charset,
        "content_word_count": page_facts.content.word_count,
        "metadata_title": page_facts.metadata.title,
        "link_count": len(page_facts.links.links),
        "resource_count": len(page_facts.resources.resources),
        "technical_status_code": page_facts.technical.status_code,
        "technical_content_length": page_facts.technical.content_length,
        "technical_response_time_ms": page_facts.technical.response_time_ms,
        "json_ld_count": len(page_facts.technical.json_ld),
    })
    print(f"  [PASS] page facts from parsed - words={page_facts.content.word_count}, "
          f"links={len(page_facts.links.links)}, "
          f"resources={len(page_facts.resources.resources)}, "
          f"json_ld={len(page_facts.technical.json_ld)}")


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    async def main():
        result = await get_crawl_result()
        await test_seo_facts_extraction(result)
        await test_page_facts_from_parsed_document(result)
        print("\nAll SEO-fact tests passed!")
        print(f"Results saved to: {RESULTS_DIR}")

    asyncio.run(main())

