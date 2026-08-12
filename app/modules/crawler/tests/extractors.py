"""
Integration test for the full extractor pipeline via PageExtractionService.

Crawls https://cyfuture.com, runs PageExtractionService.extract_all which
orchestrates every individual extractor (document, content, metadata, links,
resources, technical) and returns a single PageFacts dataclass.

Results are saved to crawler/results/cyfuture.com/extractors.json.
"""
from conftest import RESULTS_DIR, get_crawl_result, save_result

from app.modules.crawler.services.page_extraction_service import (
    PageExtractionService,
    PageFacts,
)
from app.modules.crawler.extractors.document_extractor import DocumentFacts
from app.modules.crawler.extractors.content_extractor import ContentFacts
from app.modules.crawler.extractors.metadata_extractor import MetadataFacts
from app.modules.crawler.extractors.link_extractor import LinkFacts
from app.modules.crawler.extractors.asset_extractor import ResourceFacts
from app.modules.crawler.extractors.technical_extractor import TechnicalFacts


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


async def test_all_extractors_integration(crawl_result):
    """Run the full extractor pipeline and verify every section is populated."""
    document = crawl_result.document
    fetch = crawl_result.fetch_result

    service = PageExtractionService()
    page_facts: PageFacts = await service.extract_all(
        document=document,
        status_code=fetch.status_code,
        headers=fetch.headers,
        content_length=fetch.content_length,
        response_time_ms=fetch.response_time_ms,
        redirects=_redirects_to_dicts(fetch.redirect_chain),
    )

    # --- Verify every section is populated ---
    assert page_facts is not None, "PageFacts should not be None"
    assert page_facts.document is not None, "DocumentFacts section missing"
    assert page_facts.content is not None, "ContentFacts section missing"
    assert page_facts.metadata is not None, "MetadataFacts section missing"
    assert page_facts.links is not None, "LinkFacts section missing"
    assert page_facts.resources is not None, "ResourceFacts section missing"
    assert page_facts.technical is not None, "TechnicalFacts section missing"

    # --- Document ---
    assert page_facts.document.is_html is True
    assert page_facts.document.doctype

    # --- Content ---
    assert page_facts.content.word_count > 0
    assert page_facts.content.content_hash

    # --- Metadata ---
    assert page_facts.metadata.title

    # --- Links ---
    assert len(page_facts.links.links) > 0

    # --- Resources ---
    assert len(page_facts.resources.resources) > 0

    # --- Technical ---
    assert page_facts.technical.status_code == fetch.status_code
    assert page_facts.technical.content_type

    # --- Persist results ---
    payload = {
        "url": crawl_result.normalized_url,
        "status_code": page_facts.technical.status_code,
        "content_type": page_facts.technical.content_type,
        "document": {
            "doctype": page_facts.document.doctype,
            "is_html": page_facts.document.is_html,
            "language": page_facts.document.language,
            "charset": page_facts.document.charset,
            "base_url": page_facts.document.base_url,
            "raw_html_length": len(page_facts.document.raw_html),
        },
        "content": {
            "word_count": page_facts.content.word_count,
            "sentence_count": page_facts.content.sentence_count,
            "paragraph_count": page_facts.content.paragraph_count,
            "headings": page_facts.content.headings,
            "content_hash": page_facts.content.content_hash,
            "text_html_ratio": page_facts.content.text_html_ratio,
        },
        "metadata": {
            "title": page_facts.metadata.title,
            "title_length": page_facts.metadata.title_length,
            "meta_description": page_facts.metadata.meta_description,
            "canonical": page_facts.metadata.canonical,
            "robots_meta": page_facts.metadata.robots_meta,
            "googlebot": page_facts.metadata.googlebot,
            "viewport": page_facts.metadata.viewport,
            "charset": page_facts.metadata.charset,
            "favicon": page_facts.metadata.favicon,
            "open_graph": page_facts.metadata.open_graph,
            "twitter": page_facts.metadata.twitter,
            "hreflang": page_facts.metadata.hreflang,
        },
        "links": {
            "total": len(page_facts.links.links),
            "internal_count": page_facts.links.internal_count,
            "external_count": page_facts.links.external_count,
        },
        "resources": {"total": len(page_facts.resources.resources)},
        "technical": {
            "status_code": page_facts.technical.status_code,
            "content_type": page_facts.technical.content_type,
            "content_length": page_facts.technical.content_length,
            "response_time_ms": page_facts.technical.response_time_ms,
            "security": page_facts.technical.security,
            "performance": page_facts.technical.performance,
            "accessibility": page_facts.technical.accessibility,
            "json_ld": page_facts.technical.json_ld,
        },
    }
    save_result("extractors.json", payload)
    print(f"  [PASS] all extractors integration - "
          f"words={page_facts.content.word_count}, "
          f"links={len(page_facts.links.links)}, "
          f"resources={len(page_facts.resources.resources)}, "
          f"json_ld={len(page_facts.technical.json_ld)}")   


async def test_page_facts_completeness(crawl_result):
    """Verify that every expected sub-field exists with correct types."""
    document = crawl_result.document
    fetch = crawl_result.fetch_result

    service = PageExtractionService()
    page_facts = await service.extract_all(
        document=document,
        status_code=fetch.status_code,
        headers=fetch.headers,
        content_length=fetch.content_length,
        response_time_ms=fetch.response_time_ms,
        redirects=[],
    )

    # Type checks for every section
    assert isinstance(page_facts.document, DocumentFacts)
    assert isinstance(page_facts.content, ContentFacts)
    assert isinstance(page_facts.metadata, MetadataFacts)
    assert isinstance(page_facts.links, LinkFacts)
    assert isinstance(page_facts.resources, ResourceFacts)
    assert isinstance(page_facts.technical, TechnicalFacts)

    save_result("page_facts_completeness.json", {
        "url": crawl_result.normalized_url,
        "all_sections_present": True,
        "types": {
            "document": type(page_facts.document).__name__,
            "content": type(page_facts.content).__name__,
            "metadata": type(page_facts.metadata).__name__,
            "links": type(page_facts.links).__name__,
            "resources": type(page_facts.resources).__name__,
            "technical": type(page_facts.technical).__name__,
        },
    })
    print(f"  [PASS] page facts completeness - all section types verified")


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    async def main():
        result = await get_crawl_result()
        await test_all_extractors_integration(result)
        await test_page_facts_completeness(result)
        print("\nAll extractors tests passed!")
        print(f"Results saved to: {RESULTS_DIR}")

    asyncio.run(main())

