"""Unit tests for new parser module components."""
import pytest
from app.modules.parser.normalizers import (
    normalize_text,
    normalize_url,
    resolve_url,
    is_internal,
    normalize_rel,
    normalize_title,
    normalize_canonical,
)
from app.modules.parser.analyzers import (
    analyze_content,
    analyze_headings,
    analyze_links,
    analyze_images,
    analyze_schemas,
    analyze_hreflang,
    analyze_resources,
)
from app.modules.parser.models import (
    ParsedPage,
    PageIdentity,
    PageMetadata,
    ContentData,
    HeadingData,
    LinkData,
    ImageData,
    SchemaData,
    HreflangData,
    SocialData,
    ResourceData,
    TechnicalData,
    ParserMetadata,
)
from app.modules.parser.exceptions import (
    ParserError,
    HTMLParseError,
    ExtractionError,
    PartialParseError,
)


class TestTextNormalizer:
    def test_normalize_whitespace(self):
        assert normalize_text("  hello   world  ") == "hello world"

    def test_unescape_html(self):
        from app.modules.parser.normalizers.text_normalizer import unescape_html
        assert "&" in unescape_html("a &amp; b")

    def test_strip_zero_width(self):
        from app.modules.parser.normalizers.text_normalizer import strip_zero_width
        assert "\u200b" not in strip_zero_width("hello\u200bworld")


class TestURLNormalizer:
    def test_resolve_url_absolute(self):
        assert resolve_url("https://example.com", "https://other.com") == "https://other.com"

    def test_resolve_url_relative(self):
        assert resolve_url("https://example.com/dir/", "page.html") == "https://example.com/dir/page.html"

    def test_resolve_url_fragment(self):
        assert resolve_url("https://example.com", "#section") == ""

    def test_resolve_url_javascript(self):
        assert resolve_url("https://example.com", "javascript:void(0)") == ""

    def test_is_internal(self):
        assert is_internal("https://example.com", "https://example.com/page") is True
        assert is_internal("https://example.com", "https://other.com") is False

    def test_normalize_rel(self):
        assert normalize_rel("nofollow ugc") == ["nofollow", "ugc"]
        assert normalize_rel(["NoFollow", "UGC"]) == ["nofollow", "ugc"]
        assert normalize_rel(None) == []


class TestMetadataNormalizer:
    def test_normalize_title(self):
        assert normalize_title("  Hello World  ") == "Hello World"
        assert normalize_title("") == ""

    def test_normalize_canonical(self):
        assert normalize_canonical("  https://example.com  ") == "https://example.com"
        assert normalize_canonical("") == ""


class TestModels:
    def test_parsed_page_creation(self):
        page = ParsedPage(
            document=PageIdentity(url="https://example.com"),
            metadata=PageMetadata(title="Test"),
            content=ContentData(word_count=100),
        )
        assert page.document.url == "https://example.com"
        assert page.metadata.title == "Test"
        assert page.content.word_count == 100

    def test_parsed_page_backward_compat(self):
        page = ParsedPage(schemas=[SchemaData(format="json-ld")])
        assert len(page.structured_data) == 1
        assert page.structured_data[0].format == "json-ld"

    def test_heading_data(self):
        h = HeadingData(level=1, text="Title", position=0)
        assert h.level == 1
        assert h.text == "Title"

    def test_hreflang_data_x_default(self):
        h = HreflangData(href="https://example.com", hreflang="x-default")
        assert h.is_x_default is True


class TestExceptions:
    def test_parser_error_hierarchy(self):
        assert issubclass(HTMLParseError, ParserError)
        assert issubclass(ExtractionError, ParserError)
        assert issubclass(PartialParseError, ParserError)

    def test_extraction_error_with_element(self):
        err = ExtractionError("metadata", "tag not found", "title")
        assert "metadata" in str(err)
        assert "title" in str(err)

    def test_partial_parse_error(self):
        err = PartialParseError("partial failure", errors=["e1", "e2"])
        assert len(err.errors) == 2


class TestContentAnalyzer:
    def test_analyze_content_basic(self):
        content = ContentData(
            text="hello world hello",
            normalized_text="hello world hello",
            word_count=3,
            character_count=17,
            sentence_count=1,
            paragraph_count=1,
            text_html_ratio=0.5,
        )
        result = analyze_content(content)
        assert result["word_count"] == 3
        assert result["unique_word_count"] == 2
        assert result["sentence_count"] == 1

    def test_analyze_content_empty(self):
        content = ContentData()
        result = analyze_content(content)
        assert result["word_count"] == 0
        assert result["avg_sentence_length"] == 0.0


class TestHeadingAnalyzer:
    def test_analyze_headings(self):
        content = ContentData(
            headings=[
                HeadingData(level=1, text="H1", position=0),
                HeadingData(level=2, text="H2", position=1),
                HeadingData(level=3, text="H3", position=2),
            ]
        )
        result = analyze_headings(content)
        assert result["h1"] == 1
        assert result["h2"] == 1
        assert result["h3"] == 1
        assert result["total_headings"] == 3
        assert result["is_sequential"] is True
        assert result["has_h1"] is True

    def test_analyze_headings_non_sequential(self):
        content = ContentData(
            headings=[
                HeadingData(level=1, text="H1", position=0),
                HeadingData(level=4, text="H4", position=1),
            ]
        )
        result = analyze_headings(content)
        assert result["is_sequential"] is False


class TestLinkAnalyzer:
    def test_analyze_links(self):
        links = [
            LinkData(href="https://example.com/page1", absolute_url="https://example.com/page1"),
            LinkData(href="https://other.com/page", absolute_url="https://other.com/page"),
        ]
        result = analyze_links(links, "https://example.com")
        assert result["total_links"] == 2
        assert result["internal_count"] == 1
        assert result["external_count"] == 1


class TestImageAnalyzer:
    def test_analyze_images(self):
        images = [
            ImageData(url="/img1.jpg", alt="alt text"),
            ImageData(url="/img2.jpg", alt=""),
            ImageData(url="/img3.jpg"),
        ]
        result = analyze_images(images)
        assert result["total_images"] == 3
        assert result["with_alt"] == 1
        assert result["without_alt"] == 2
        assert result["alt_coverage_percent"] == pytest.approx(33.3, 0.1)

    def test_analyze_images_empty(self):
        result = analyze_images([])
        assert result["total_images"] == 0
        assert result["alt_coverage_percent"] == 0.0

    def test_analyze_images_lazy(self):
        images = [ImageData(url="/img.jpg", alt="x", loading="lazy")]
        result = analyze_images(images)
        assert result["has_lazy_loading"] is True


class TestSchemaAnalyzer:
    def test_analyze_schemas(self):
        schemas = [
            SchemaData(format="json-ld", types=["Article"]),
            SchemaData(format="microdata", types=["Product"]),
            SchemaData(format="json-ld", types=["Organization"], attributes={"parse_error": "err"}),
        ]
        result = analyze_schemas(schemas)
        assert result["total_schemas"] == 3
        assert result["json_ld_count"] == 2
        assert result["microdata_count"] == 1
        assert result["parse_errors"] == 1
        assert "Article" in result["schema_types"]

    def test_analyze_schemas_empty(self):
        result = analyze_schemas([])
        assert result["total_schemas"] == 0


class TestHreflangAnalyzer:
    def test_analyze_hreflang(self):
        entries = [
            HreflangData(href="https://example.com/en", hreflang="en"),
            HreflangData(href="https://example.com/fr", hreflang="fr"),
            HreflangData(href="https://example.com/x", hreflang="x-default", is_x_default=True),
        ]
        result = analyze_hreflang(entries)
        assert result["total_hreflang"] == 3
        assert result["language_count"] == 2
        assert result["has_x_default"] is True

    def test_analyze_hreflang_empty(self):
        result = analyze_hreflang([])
        assert result["total_hreflang"] == 0
        assert result["has_x_default"] is False


class TestResourceAnalyzer:
    def test_analyze_resources(self):
        resources = [
            ResourceData(resource_type="script", url="/app.js"),
            ResourceData(resource_type="stylesheet", url="/style.css"),
            ResourceData(resource_type="image", url="/img.jpg"),
            ResourceData(resource_type="script", url="/other.js"),
        ]
        result = analyze_resources(resources)
        assert result["total_resources"] == 4
        assert result["by_type"]["script"] == 2
        assert result["by_type"]["stylesheet"] == 1
        assert result["by_type"]["image"] == 1

    def test_analyze_resources_empty(self):
        result = analyze_resources([])
        assert result["total_resources"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
