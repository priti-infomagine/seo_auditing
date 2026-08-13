"""
Tests for SitemapDiscoverer XML and .gz parsing.
"""
import gzip

import pytest

from app.modules.crawler.utils.sitemap_discoverer import SitemapDiscoverer


SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/page1</loc>
  </url>
  <url>
    <loc>https://example.com/page2</loc>
  </url>
</urlset>
"""


class TestSitemapDiscoverer:
    def test_parse_xml_urls(self):
        discoverer = SitemapDiscoverer()
        urls = discoverer._parse_xml(SITEMAP_XML)
        assert len(urls) == 2
        assert "https://example.com/page1" in urls
        assert "https://example.com/page2" in urls

    def test_gzip_decompress(self):
        compressed = gzip.compress(SITEMAP_XML.encode("utf-8"))
        discoverer = SitemapDiscoverer()
        urls = discoverer._parse_xml(gzip.decompress(compressed).decode("utf-8"))
        assert len(urls) == 2
