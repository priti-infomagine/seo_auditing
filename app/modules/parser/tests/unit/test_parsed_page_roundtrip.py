"""
Tests that ParsedPage survives a JSON round-trip:
    ParsedPage.model_dump(mode="json")  ->  ParsedPage.model_validate(...)

This validates the cache path added in T1-6 where DBParserService
reconstructs a ParsedPage from the ``parsed_data`` JSONB column stored
on PageSnapshot alongside the HTML snapshot.
"""
import pytest
from app.modules.parser.services.parser_orchestrator import ParserOrchestrator
from app.modules.parser.models.parsed_page import ParsedPage


SAMPLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Full SEO Test - Best Platform 2024</title>
    <meta name="description" content="Complete SEO testing page with all meta tags.">
    <meta name="robots" content="index, follow, max-image-preview:large">
    <meta name="googlebot" content="index, follow">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="canonical" href="https://example.com/seo-test">
    <link rel="icon" type="image/x-icon" href="/favicon.ico">
    <meta property="og:title" content="Full SEO Test">
    <meta property="og:description" content="Complete SEO testing page">
    <meta property="og:image" content="/og-image.jpg">
    <meta property="og:url" content="https://example.com/seo-test">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Full SEO Test Twitter">
    <link rel="alternate" hreflang="en" href="https://example.com/en">
    <link rel="alternate" hreflang="fr" href="https://example.com/fr">
    <link rel="alternate" hreflang="x-default" href="https://example.com/">
    <script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "Article", "headline": "SEO Test"}
    </script>
</head>
<body>
    <header><h1>Main Title</h1></header>
    <nav>
        <a href="/">Home</a>
        <a href="/about">About</a>
        <a href="https://external.com">External</a>
    </nav>
    <main>
        <article>
            <h2>Section One</h2>
            <p>Paragraph one with SEO content.</p>
            <h3>Subsection</h3>
            <p>Paragraph two with more content.</p>
            <img src="/hero.jpg" alt="Hero image" width="800" height="600" loading="lazy">
            <img src="/missing-alt.jpg">
        </article>
    </main>
    <footer>
        <h3>Footer</h3>
        <a href="/privacy">Privacy</a>
    </footer>
    <script src="/main.js" async defer></script>
    <link rel="stylesheet" href="/main.css">
</body>
</html>"""


class TestParsedPageRoundTrip:
    def test_round_trip_preserves_all_top_level_fields(self):
        parsed = ParserOrchestrator().parse(html=SAMPLE_HTML, url="https://example.com/seo-test")
        dumped = parsed.model_dump(mode="json")
        restored = ParsedPage.model_validate(dumped)

        assert restored.document.url == parsed.document.url
        assert restored.document.doctype == parsed.document.doctype
        assert restored.document.html_size == parsed.document.html_size

        assert restored.metadata.title == parsed.metadata.title
        assert restored.metadata.title_length == parsed.metadata.title_length
        assert restored.metadata.meta_description == parsed.metadata.meta_description
        assert restored.metadata.canonical == parsed.metadata.canonical
        assert restored.metadata.open_graph == parsed.metadata.open_graph
        assert restored.metadata.twitter == parsed.metadata.twitter
        assert restored.metadata.hreflang == parsed.metadata.hreflang

        assert restored.content.text == parsed.content.text
        assert restored.content.word_count == parsed.content.word_count
        assert restored.content.paragraph_count == parsed.content.paragraph_count
        assert restored.content.headings == parsed.content.headings

        assert restored.links == parsed.links
        assert restored.images == parsed.images
        assert restored.resources == parsed.resources
        assert restored.schemas == parsed.schemas
        assert restored.hreflang == parsed.hreflang
        assert restored.social == parsed.social
        assert restored.technical == parsed.technical

        assert restored.parser_metadata.warnings == parsed.parser_metadata.warnings
        assert restored.parser_metadata.errors == parsed.parser_metadata.errors

    def test_round_trip_preserves_documents_deep_equality(self):
        parsed = ParserOrchestrator().parse(html=SAMPLE_HTML, url="https://example.com/seo-test")
        dumped = parsed.model_dump(mode="json")
        restored = ParsedPage.model_validate(dumped)

        # Deep-equality via model_dump on both sides
        assert restored.model_dump() == parsed.model_dump()

    def test_structured_data_property_works_after_round_trip(self):
        parsed = ParserOrchestrator().parse(html=SAMPLE_HTML, url="https://example.com/seo-test")
        dumped = parsed.model_dump(mode="json")
        restored = ParsedPage.model_validate(dumped)

        assert len(restored.structured_data) == len(parsed.structured_data)
        assert restored.structured_data[0].types == parsed.structured_data[0].types

    def test_warnings_and_errors_properties_work_after_round_trip(self):
        parsed = ParserOrchestrator().parse(html=SAMPLE_HTML, url="https://example.com/seo-test")
        dumped = parsed.model_dump(mode="json")
        restored = ParsedPage.model_validate(dumped)

        assert restored.warnings == parsed.warnings
        assert restored.errors == parsed.errors

    def test_round_trip_with_minimal_html(self):
        html = "<html><head><title>Minimal</title></head><body><p>Hi</p></body></html>"
        parsed = ParserOrchestrator().parse(html=html, url="https://example.com/min")
        dumped = parsed.model_dump(mode="json")
        restored = ParsedPage.model_validate(dumped)

        assert restored.document.url == "https://example.com/min"
        assert restored.metadata.title == "Minimal"
        assert "Hi" in restored.content.text

    def test_round_trip_with_empty_html(self):
        parsed = ParserOrchestrator().parse(html="", url="https://example.com/empty")
        dumped = parsed.model_dump(mode="json")
        restored = ParsedPage.model_validate(dumped)

        assert restored.document.url == "https://example.com/empty"
        assert restored.content.text == ""
