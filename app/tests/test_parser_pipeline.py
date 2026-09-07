"""Integration tests for the parser pipeline: crawler → parser → extractor → SEO facts."""
import sys
sys.path.insert(0, ".")

from app.modules.parser.services.parser_service import ParserService
from app.modules.crawler.extractors.seo_fact_extractor import (
    extract_seo_facts,
    parsed_document_to_page_facts,
)

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Example SEO Tool - Best Platform for Audits</title>
    <meta name="description" content="The best SEO audit tool for website analysis and optimization.">
    <meta name="robots" content="index, follow">
    <meta name="googlebot" content="index, follow">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="canonical" href="https://example.com/page">
    <link rel="icon" href="/favicon.ico">
    <meta property="og:title" content="Example SEO Tool">
    <meta property="og:description" content="Best SEO audit tool">
    <meta property="og:image" content="/og.jpg">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Example SEO">
    <link rel="alternate" hreflang="en" href="https://example.com/en">
    <link rel="alternate" hreflang="fr" href="https://example.com/fr">
    <script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "Organization", "name": "Example"}
    </script>
</head>
<body>
    <header><h1>Welcome to Example SEO Tool</h1></header>
    <nav><a href="/">Home</a><a href="/about">About</a></nav>
    <main>
        <article>
            <h2>Features</h2>
            <p>This tool provides comprehensive SEO analysis.</p>
            <img src="/hero.jpg" alt="SEO dashboard">
            <a href="/page1">Internal Link</a>
            <a href="https://external.com">External</a>
        </article>
    </main>
    <footer><h3>Footer</h3></footer>
    <script src="/app.js" async defer></script>
    <link rel="stylesheet" href="/style.css">
</body>
</html>
"""


def test_parser_service_produces_stable_parsed_document():
    service = ParserService()
    parsed = service.parse(html=HTML, url="https://example.com/page")

    # DocumentInfo fields
    assert parsed.document.url == "https://example.com/page"
    assert parsed.document.language == "en"
    assert parsed.document.doctype == "html"
    assert parsed.document.charset == "UTF-8"
    assert parsed.document.html_size == len(HTML.encode("utf-8"))

    # Metadata
    assert parsed.metadata.title == "Example SEO Tool - Best Platform for Audits"
    assert parsed.metadata.title_length == 43
    assert parsed.metadata.meta_description == "The best SEO audit tool for website analysis and optimization."
    assert parsed.metadata.meta_description_length == 62
    assert parsed.metadata.canonical == "https://example.com/page"
    # robots stored as list of MetaTag (not scalar)
    robot_names = [t.name for t in parsed.metadata.robots]
    assert "robots" in robot_names
    assert "googlebot" in robot_names
    assert parsed.metadata.viewport == "width=device-width, initial-scale=1"
    assert parsed.metadata.open_graph == {"og:title": ["Example SEO Tool"], "og:description": ["Best SEO audit tool"], "og:image": ["/og.jpg"]}
    assert parsed.metadata.twitter == {"twitter:card": ["summary_large_image"], "twitter:title": ["Example SEO"]}
    assert len(parsed.metadata.hreflang) == 2
    assert parsed.metadata.hreflang[0].href == "https://example.com/en"
    assert parsed.metadata.hreflang[0].hreflang == "en"
    assert parsed.metadata.favicon_urls == ["/favicon.ico"]

    # Check robots are in the list
    robot_names = [t.name for t in parsed.metadata.robots]
    assert "robots" in robot_names
    assert "googlebot" in robot_names

    # Structured data - DOM not destroyed by ContentParser
    assert len(parsed.structured_data) == 1
    assert parsed.structured_data[0].format == "json-ld"
    assert "Organization" in parsed.structured_data[0].types
    assert parsed.structured_data[0].context == "https://schema.org"

    # Content
    assert parsed.content.word_count > 0
    assert parsed.content.character_count > 0
    assert len(parsed.content.headings) == 3
    assert parsed.content.headings[0].level == 1
    assert parsed.content.headings[0].text == "Welcome to Example SEO Tool"
    assert parsed.content.has_main is True
    assert parsed.content.has_article is True
    assert parsed.content.has_nav is True
    assert parsed.content.has_header is True
    assert parsed.content.has_footer is True
    assert len(parsed.content.semantic_elements) == 5

    # Links
    assert len(parsed.links) == 4  # Home, About, Internal, External

    # Resources
    assert len(parsed.resources) == 3  # hero.jpg, app.js, style.css

    # No parser errors
    assert len(parsed.errors) == 0

    print("test_parser_service_produces_stable_parsed_document: PASS")


def test_seo_facts_rule_engine_format():
    service = ParserService()
    parsed = service.parse(html=HTML, url="https://example.com/page")
    facts = extract_seo_facts(parsed)

    # Basic section
    assert facts["basic"]["title"] == "Example SEO Tool - Best Platform for Audits"
    assert facts["basic"]["title_length"] == 43
    assert facts["basic"]["meta_description"] == "The best SEO audit tool for website analysis and optimization."
    assert facts["basic"]["meta_description_length"] == 62
    assert facts["basic"]["doctype"] == "html"
    assert facts["basic"]["language"] == "en"
    assert facts["basic"]["charset"] == "UTF-8"
    assert facts["basic"]["viewport"] == "width=device-width, initial-scale=1"
    assert facts["basic"]["html_size"] == len(HTML.encode("utf-8"))

    # Headings section
    assert "h1" in facts["headings"]
    assert "h2" in facts["headings"]
    assert "h3" in facts["headings"]
    assert facts["headings"]["h1"] == ["Welcome to Example SEO Tool"]
    assert facts["headings"]["heading_stats"]["total_headings"] == 3
    assert facts["headings"]["heading_stats"]["is_sequential"] is True

    # SEO section
    assert facts["seo"]["canonical_url"] == "https://example.com/page"
    assert facts["seo"]["robots_meta"] == "index, follow"
    assert len(facts["seo"]["hreflang"]) == 2
    assert facts["seo"]["favicon_urls"] == ["/favicon.ico"]

    # Social section
    assert "open_graph" in facts["social"]
    assert "twitter_cards" in facts["social"]
    # OG values are stored as lists to preserve duplicates
    assert facts["social"]["open_graph"]["tags"]["og:title"] == ["Example SEO Tool"]
    assert facts["social"]["twitter_cards"]["tags"]["twitter:card"] == ["summary_large_image"]

    # Content section
    assert facts["content"]["word_count"] > 0
    assert facts["content"]["has_main"] is True
    assert facts["content"]["has_article"] is True

    # Links section - parser stores raw href + absolute_url
    assert len(facts["links"]) == 4
    hrefs = [l["href"] for l in facts["links"]]
    assert "/" in hrefs  # Home link
    assert "/about" in hrefs  # About link
    assert "/page1" in hrefs  # Internal link
    assert "https://external.com" in hrefs  # External link

    # Images section - parser stores raw href, not absolute URL
    assert len(facts["images"]) == 1
    assert facts["images"][0]["alt"] == "SEO dashboard"
    assert facts["images"][0]["url"] == "/hero.jpg"

    # Scripts section - parser stores raw src
    assert len(facts["scripts"]) == 1
    assert facts["scripts"][0]["url"] == "/app.js"

    # Stylesheets section - parser stores raw href
    assert len(facts["stylesheets"]) == 1
    assert facts["stylesheets"][0]["url"] == "/style.css"

    # Structured data section
    assert len(facts["structured_data"]) == 1
    assert facts["structured_data"][0]["format"] == "json-ld"
    assert facts["structured_data"][0]["types"] == ["Organization"]
    assert facts["structured_data"][0]["parse_error"] is None

    print("test_seo_facts_rule_engine_format: PASS")


def test_parse_html_api_compatible():
    """Test the parse_html entry point used by score/analyze endpoints."""
    service = ParserService()

    # Without crawler_data
    result = service.parse_html(html=HTML, url="https://example.com/page")
    assert isinstance(result, dict)
    assert result["metadata"]["title"] == "Example SEO Tool - Best Platform for Audits"
    assert "content" in result
    assert "structured_data" in result
    assert result["crawl_context"]["final_url"] == "https://example.com/page"

    # With crawler_data
    crawler_data = {
        "status_code": 200,
        "content_type": "text/html",
        "response_time_ms": 150,
        "headers": {"content-type": "text/html"},
        "redirect_chain": [],
        "requested_url": "https://example.com/page",
        "final_url": "https://example.com/page",
    }
    result2 = service.parse_html(html=HTML, url="https://example.com/page", crawler_data=crawler_data)
    assert result2["crawler_data"]["status_code"] == 200
    assert result2["crawl_context"]["status_code"] == 200

    print("test_parse_html_api_compatible: PASS")


def test_page_facts_from_parsed_document():
    """Test converting ParsedDocument → PageFacts (crawler dataclasses)."""
    service = ParserService()
    parsed = service.parse(html=HTML, url="https://example.com/page")

    page_facts = parsed_document_to_page_facts(
        parsed,
        status_code=200,
        headers={"content-type": "text/html"},
        content_length=5000,
        response_time_ms=150,
        redirects=[],
    )

    assert page_facts.metadata.title == "Example SEO Tool - Best Platform for Audits"
    assert page_facts.metadata.title_length == 43
    assert page_facts.metadata.canonical == "https://example.com/page"
    assert page_facts.content.word_count > 0
    assert page_facts.technical.status_code == 200
    assert page_facts.technical.response_time_ms == 150

    print("test_page_facts_from_parsed_document: PASS")


def test_empty_html():
    """Test that empty/malformed HTML doesn't crash."""
    service = ParserService()

    # Empty HTML
    try:
        parsed = service.parse(html="", url="https://example.com")
    except ValueError:
        parsed = None
    assert parsed is None or len(parsed.errors) > 0

    # Minimal HTML
    parsed = service.parse(html="<html><head><title>T</title></head><body><p>Hi</p></body></html>", url="https://example.com")
    assert parsed.document.url == "https://example.com"
    assert parsed.metadata.title == "T"
    assert parsed.content.word_count > 0

    print("test_empty_html: PASS")


def test_no_title():
    """Test HTML without title tag."""
    service = ParserService()
    html = "<html><head></head><body><p>No title here.</p></body></html>"
    parsed = service.parse(html=html, url="https://example.com")
    assert parsed.metadata.title == ""
    assert parsed.metadata.title_length == 0

    facts = extract_seo_facts(parsed)
    assert facts["basic"]["title"] == ""
    assert facts["basic"]["title_length"] == 0

    print("test_no_title: PASS")


def test_duplicate_meta_tags():
    """Test that duplicate meta tags are preserved."""
    service = ParserService()
    html = """<html><head>
    <meta name="description" content="First">
    <meta name="description" content="Second">
    <meta property="og:title" content="OG1">
    <meta property="og:title" content="OG2">
    </head><body><p>Content</p></body></html>"""
    parsed = service.parse(html=html, url="https://example.com")
    # Parser keeps first occurrence for scalar fields
    assert parsed.metadata.meta_description == "First"
    # OG uses list storage
    assert "og:title" in parsed.metadata.open_graph
    assert len(parsed.metadata.open_graph["og:title"]) == 2

    print("test_duplicate_meta_tags: PASS")


def test_multiple_canonicals():
    """Test multiple canonical tags."""
    service = ParserService()
    html = """<html><head>
    <link rel="canonical" href="https://example.com/first">
    <link rel="canonical" href="https://example.com/second">
    </head><body><p>Content</p></body></html>"""
    parsed = service.parse(html=html, url="https://example.com")
    # Parser keeps first canonical
    assert parsed.metadata.canonical == "https://example.com/first"

    print("test_multiple_canonicals: PASS")


def test_relative_links():
    """Test relative link resolution."""
    service = ParserService()
    html = """<html><body>
    <a href="/page1">Relative</a>
    <a href="page2">Relative no slash</a>
    <a href="#section">Fragment</a>
    <a href="javascript:void(0)">JS</a>
    <a href="mailto:test@example.com">Email</a>
    <a href="https://external.com">External</a>
    </body></html>"""
    parsed = service.parse(html=html, url="https://example.com/dir/page.html")
    # Fragment, javascript, mailto are excluded by parser
    assert len(parsed.links) >= 3
    hrefs = [l.absolute_url for l in parsed.links]
    assert "https://example.com/page1" in hrefs
    assert "https://example.com/dir/page2" in hrefs
    assert "https://external.com" in hrefs

    print("test_relative_links: PASS")


def test_images_with_alt():
    """Test image extraction."""
    service = ParserService()
    html = """<html><body>
    <img src="/img1.jpg" alt="Alt text">
    <img src="/img2.jpg" alt="">
    <img src="/img3.jpg">
    <img src="/img4.jpg" alt="Hero" width="100" height="200" loading="lazy" decoding="async">
    </body></html>"""
    parsed = service.parse(html=html, url="https://example.com")
    assert len(parsed.resources) == 4
    img_resources = [r for r in parsed.resources if r.resource_type == "image"]
    assert len(img_resources) == 4
    assert img_resources[0].alt == "Alt text"
    assert img_resources[1].alt == ""
    assert img_resources[2].alt == ""
    assert img_resources[3].alt == "Hero"
    assert img_resources[3].loading == "lazy"

    facts = extract_seo_facts(parsed)
    assert len(facts["images"]) == 4

    print("test_images_with_alt: PASS")


def test_malformed_json_ld():
    """Test that malformed JSON-LD is preserved with parse error."""
    service = ParserService()
    html = """<html><head>
    <script type="application/ld+json">
    {invalid json here
    </script>
    <script type="application/ld+json">
    {"@type": "Article", "valid": true}
    </script>
    </head><body><p>Content</p></body></html>"""
    parsed = service.parse(html=html, url="https://example.com")
    # One malformed, one valid
    assert len(parsed.structured_data) == 2
    malformed = [s for s in parsed.structured_data if s.attributes.get("parse_error")]
    valid = [s for s in parsed.structured_data if not s.attributes.get("parse_error")]
    assert len(malformed) == 1
    assert len(valid) == 1
    assert valid[0].types == ["Article"]

    facts = extract_seo_facts(parsed)
    assert len(facts["structured_data"]) == 2

    print("test_malformed_json_ld: PASS")


def test_no_circular_imports():
    """Verify no circular import between parser and crawler."""
    # Both of these should succeed
    from app.modules.parser.services.parser_service import ParserService
    from app.modules.crawler.extractors.seo_fact_extractor import (
        extract_seo_facts,
        parsed_document_to_page_facts,
    )
    from app.modules.crawler.services.page_extraction_service import PageExtractionService

    print("test_no_circular_imports: PASS")


if __name__ == "__main__":
    test_parser_service_produces_stable_parsed_document()
    test_seo_facts_rule_engine_format()
    test_parse_html_api_compatible()
    test_page_facts_from_parsed_document()
    test_empty_html()
    test_no_title()
    test_duplicate_meta_tags()
    test_multiple_canonicals()
    test_relative_links()
    test_images_with_alt()
    test_malformed_json_ld()
    test_no_circular_imports()
    print("\nAll tests passed!")
