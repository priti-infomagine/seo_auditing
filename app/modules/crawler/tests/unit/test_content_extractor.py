"""
Tests for parser-backed content extraction.
"""
from bs4 import BeautifulSoup

from app.modules.parser.services.parser_orchestrator import ParserOrchestrator


class TestParserContentExtraction:
    def test_parser_extracts_text_without_html_tags(self):
        html = "<html><body><p>Hello</p><a href='/link'>Link</a></body></html>"
        parser = ParserOrchestrator()
        parsed = parser.parse(html=html, url="https://example.com")

        assert "Hello" in parsed.content.text
        assert "<p>" not in parsed.content.text
        assert "<a>" not in parsed.content.text

    def test_parser_does_not_mutate_input(self):
        html = "<html><body><script>var x=1;</script><p>Text</p></body></html>"
        parser = ParserOrchestrator()
        parsed = parser.parse(html=html, url="https://example.com")

        # Parser creates fresh context; input HTML is not mutated
        assert html == "<html><body><script>var x=1;</script><p>Text</p></body></html>"
        assert parsed.content.text
        assert "Text" in parsed.content.text

    def test_parser_word_count(self):
        html = "<html><body><p>one two three four five</p></body></html>"
        parser = ParserOrchestrator()
        parsed = parser.parse(html=html, url="https://example.com")

        assert parsed.content.word_count == 5

    def test_parser_headings_extraction(self):
        html = "<html><body><h1>H1</h1><h2>H2</h2><h3>H3</h3></body></html>"
        parser = ParserOrchestrator()
        parsed = parser.parse(html=html, url="https://example.com")

        assert parsed.content.headings is not None
        heading_texts = [h.text for h in parsed.content.headings]
        assert "H1" in heading_texts
        assert "H2" in heading_texts
        assert "H3" in heading_texts
