"""
Tests for the sitemap XML parser.
"""
import gzip

from app.modules.seprate_checks.sitemap_check.parser import (
    decompress_sitemap_content,
    parse_robots_sitemaps,
    parse_sitemap_xml,
)
from app.modules.seprate_checks.sitemap_check.tests.conftest import load_fixture


class TestParseSitemapXML:
    def test_urlset(self):
        xml = load_fixture("sitemap.xml")
        result = parse_sitemap_xml(xml)

        assert result.entry_count == 4
        assert len(result.loc_urls) == 4
        assert result.is_index is False
        assert result.child_sitemaps == []
        assert "https://example.com/" in result.loc_urls

    def test_sitemap_index(self):
        xml = load_fixture("sitemap_index.xml")
        result = parse_sitemap_xml(xml)

        assert result.is_index is True
        assert len(result.child_sitemaps) == 2
        assert result.entry_count == 2
        assert "https://example.com/sitemap-posts.xml" in result.child_sitemaps

    def test_empty_input(self):
        result = parse_sitemap_xml("")

        assert result.error is not None
        assert result.entry_count == 0
        assert result.is_index is False

    def test_whitespace_only(self):
        result = parse_sitemap_xml("   \n\n  ")

        assert result.error is not None
        assert result.entry_count == 0

    def test_malformed_xml(self):
        raw = "<urlset><url><loc>https://example.com</loc>"
        result = parse_sitemap_xml(raw)

        assert result.error is not None
        assert result.entry_count == 0

    def test_empty_urlset(self):
        xml = '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'
        result = parse_sitemap_xml(xml)

        assert result.entry_count == 0
        assert result.is_index is False
        assert result.error is None

    def test_empty_sitemap_index(self):
        xml = '<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></sitemapindex>'
        result = parse_sitemap_xml(xml)

        assert result.is_index is False
        assert result.entry_count == 0

    def test_unknown_namespace(self):
        xml = (
            '<?xml version="1.0"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<url><loc>https://example.com/</loc></url>'
            '</urlset>'
        )
        result = parse_sitemap_xml(xml)

        assert result.entry_count == 1
        assert result.loc_urls == ["https://example.com/"]


class TestDecompressSitemapContent:
    def test_plain_xml_not_gzipped(self):
        content = b"<?xml version='1.0'?><urlset></urlset>"
        result, was_gzipped = decompress_sitemap_content(content, "application/xml")

        assert was_gzipped is False
        assert result == content

    def test_gzip_content_type(self):
        original = b"<?xml version='1.0'?><urlset></urlset>"
        compressed = gzip.compress(original)
        result, was_gzipped = decompress_sitemap_content(
            compressed, "application/gzip"
        )

        assert was_gzipped is True
        assert result == original

    def test_gz_suffix(self):
        original = b"<?xml version='1.0'?><urlset></urlset>"
        compressed = gzip.compress(original)
        result, was_gzipped = decompress_sitemap_content(
            compressed, "", url="https://example.com/sitemap.xml.gz"
        )

        assert was_gzipped is True
        assert result == original

    def test_magic_bytes_detection(self):
        original = b"<?xml version='1.0'?><urlset></urlset>"
        compressed = gzip.compress(original)
        result, was_gzipped = decompress_sitemap_content(
            compressed, "application/octet-stream"
        )

        assert was_gzipped is True
        assert result == original


class TestParseRobotsSitemaps:
    def test_extract_sitemaps(self):
        robots = load_fixture("robots_with_sitemap.txt")
        sitemaps = parse_robots_sitemaps(robots)

        assert "https://example.com/sitemap.xml" in sitemaps
        assert len(sitemaps) == 1

    def test_no_sitemaps(self):
        robots = load_fixture("robots_no_sitemap.txt")
        sitemaps = parse_robots_sitemaps(robots)

        assert sitemaps == []

    def test_empty_text(self):
        assert parse_robots_sitemaps("") == []

    def test_regex_fallback(self):
        robots = "User-agent: *\nSitemap: https://example.com/sitemap.xml\n"
        sitemaps = parse_robots_sitemaps(robots)

        assert "https://example.com/sitemap.xml" in sitemaps
