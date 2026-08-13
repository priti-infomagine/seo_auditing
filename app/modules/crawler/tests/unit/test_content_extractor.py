"""
Tests for content extractor DOM non-mutation guarantee.
"""
from bs4 import BeautifulSoup

from app.modules.crawler.extractors.content_extractor import extract_content


class TestContentExtractorDOMNonMutation:
    def test_deepcopy_prevents_mutation(self):
        html = "<html><body><p>Hello</p><a href='/link'>Link</a></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        original_links = len(soup.find_all("a"))

        extract_content(soup, html)

        assert len(soup.find_all("a")) == original_links

    def test_script_tags_removed_from_copy_only(self):
        html = "<html><body><script>var x=1;</script><p>Text</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        original_scripts = len(soup.find_all("script"))

        extract_content(soup, html)

        assert len(soup.find_all("script")) == original_scripts
