"""Unit tests for crawler dataclasses and parser-backed extraction bridge."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from bs4 import BeautifulSoup

from app.modules.crawler.extractors.document_extractor import DocumentFacts, create_document_facts
from app.modules.crawler.extractors.content_extractor import ContentFacts
from app.modules.crawler.extractors.metadata_extractor import MetadataFacts
from app.modules.crawler.extractors.link_extractor import LinkFacts
from app.modules.crawler.extractors.asset_extractor import ResourceFacts
from app.modules.crawler.extractors.technical_extractor import TechnicalFacts
from app.modules.crawler.extractors.seo_fact_extractor import parsed_document_to_page_facts, PageFacts
from app.modules.parser.services.parser_orchestrator import ParserOrchestrator


class TestDocumentFacts:
    def test_create_document_facts_basic(self):
        html = "<html><body><p>Hello</p></body></html>"
        doc = create_document_facts(html, "https://example.com")
        assert doc.is_html is True
        assert doc.base_url == "https://example.com"
        assert doc.raw_html == html
        assert doc.soup is None

    def test_create_document_facts_empty_html(self):
        doc = create_document_facts("", "https://example.com")
        assert doc.is_html is False
        assert doc.raw_html == ""

    def test_create_document_facts_doctype(self):
        html = "<!DOCTYPE html><html><head><title>T</title></head><body></body></html>"
        doc = create_document_facts(html, "https://example.com")
        assert doc.is_html is True


class TestParserBackedBridge:
    def test_bridge_produces_page_facts(self):
        html = "<html><head><title>Test Page</title></head><body><p>Hello world</p></body></html>"
        parser = ParserOrchestrator()
        parsed = parser.parse(html=html, url="https://example.com")

        page_facts = parsed_document_to_page_facts(
            parsed,
            status_code=200,
            headers={"content-type": "text/html"},
            content_length=len(html),
            response_time_ms=100,
            redirects=[],
            raw_html=html,
        )

        assert isinstance(page_facts, PageFacts)
        assert isinstance(page_facts.document, DocumentFacts)
        assert isinstance(page_facts.content, ContentFacts)
        assert isinstance(page_facts.metadata, MetadataFacts)
        assert isinstance(page_facts.links, LinkFacts)
        assert isinstance(page_facts.resources, ResourceFacts)
        assert isinstance(page_facts.technical, TechnicalFacts)

    def test_bridge_passes_raw_html(self):
        html = "<html><body><p>Hello</p></body></html>"
        parser = ParserOrchestrator()
        parsed = parser.parse(html=html, url="https://example.com")

        page_facts = parsed_document_to_page_facts(
            parsed,
            raw_html=html,
        )

        assert page_facts.document.raw_html == html

    def test_bridge_sets_technical_fields(self):
        html = "<html><body></body></html>"
        parser = ParserOrchestrator()
        parsed = parser.parse(html=html, url="https://example.com")

        page_facts = parsed_document_to_page_facts(
            parsed,
            status_code=200,
            headers={"content-type": "text/html"},
            content_length=100,
            response_time_ms=50,
            redirects=[{"url": "http://example.com", "status_code": 301}],
        )

        assert page_facts.technical.status_code == 200
        assert page_facts.technical.content_type == "text/html"
        assert page_facts.technical.content_length == 100
        assert page_facts.technical.response_time_ms == 50
        assert len(page_facts.technical.redirects) == 1

    def test_bridge_enriches_content_fields(self):
        html = "<html><body><p>Hello world. How are you?</p></body></html>"
        parser = ParserOrchestrator()
        parsed = parser.parse(html=html, url="https://example.com")

        page_facts = parsed_document_to_page_facts(
            parsed,
            raw_html=html,
        )

        # Parser provides word_count; bridge sets content_hash/sentence_count
        # (CrawlOrchestrator enriches sentence_count and content_hash after bridge)
        assert page_facts.content.word_count > 0
        assert page_facts.content.text == "Hello world. How are you?"


class TestParserOrchestrator:
    def test_parse_basic_html(self):
        html = "<html><head><title>My Page</title></head><body><p>Hello world</p></body></html>"
        parser = ParserOrchestrator()
        parsed = parser.parse(html=html, url="https://example.com")

        assert parsed.document.url == "https://example.com"
        assert parsed.metadata.title == "My Page"
        assert parsed.content.text
        assert "Hello world" in parsed.content.text

    def test_parse_extracts_links(self):
        html = '<html><body><a href="/page1">Link 1</a><a href="https://external.com">External</a></body></html>'
        parser = ParserOrchestrator()
        parsed = parser.parse(html=html, url="https://example.com")

        assert len(parsed.links) >= 1

    def test_parse_extracts_resources(self):
        html = '<html><body><img src="/img.jpg" alt="test"><link rel="stylesheet" href="/style.css"></body></html>'
        parser = ParserOrchestrator()
        parsed = parser.parse(html=html, url="https://example.com")

        resource_types = {r.resource_type for r in (parsed.resources or [])}
        assert "image" in resource_types
        assert "stylesheet" in resource_types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
