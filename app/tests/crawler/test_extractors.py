"""Unit tests for crawler extractors."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from bs4 import BeautifulSoup

from app.modules.crawler.extractors.document_extractor import extract_document, DocumentFacts
from app.modules.crawler.extractors.metadata_extractor import extract_metadata, MetadataFacts
from app.modules.crawler.extractors.content_extractor import extract_content, ContentFacts
from app.modules.crawler.extractors.link_extractor import extract_links, LinkFacts
from app.modules.crawler.extractors.asset_extractor import extract_resources, ResourceFacts
from app.modules.crawler.extractors.technical_extractor import extract_technical, TechnicalFacts


class TestDocumentExtractor:
    def test_full_html_document(self):
        html = "<!DOCTYPE html><html lang=""en""><head><meta charset=""UTF-8""><title>T</title></head><body></body></html>"
        doc = extract_document(html, "https://example.com")
        assert doc.is_html is True
        assert doc.language == "en"
        assert doc.charset == "utf-8"
        assert doc.doctype == "html"
        assert doc.base_url == "https://example.com"
        assert isinstance(doc.soup, BeautifulSoup)

    def test_empty_html(self):
        doc = extract_document("", "https://example.com")
        assert doc.is_html is False
        assert doc.language == ""
        assert doc.charset == ""

    def test_html_without_lang(self):
        html = "<html><head><title>T</title></head><body></body></html>"
        doc = extract_document(html, "https://example.com")
        assert doc.language == ""

    def test_charset_from_charset_meta(self):
        html = '<html><head><meta charset="UTF-8"><title>T</title></head><body></body></html>'
        doc = extract_document(html, "https://example.com")
        assert doc.charset == "utf-8"

    def test_charset_from_http_equiv(self):
        html = '<html><head><meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1"><title>T</title></head><body></body></html>'
        doc = extract_document(html, "https://example.com")
        assert doc.charset == "iso-8859-1"

    def test_doctype_html5(self):
        html = "<!DOCTYPE html><html><head><title>T</title></head><body></body></html>"
        doc = extract_document(html, "https://example.com")
        assert doc.doctype == "html"

    def test_no_doctype(self):
        html = "<html><head><title>T</title></head><body></body></html>"
        doc = extract_document(html, "https://example.com")
        assert doc.doctype == ""

    def test_raw_html_preserved(self):
        html = "<html><body><p>Hello</p></body></html>"
        doc = extract_document(html, "https://example.com")
        assert doc.raw_html == html
class TestMetadataExtractor:
    def _soup(self, html):
        return BeautifulSoup(html, "html.parser")

    def test_title_extracted(self):
        html = "<html><head><title>My Page</title></head><body></body></html>"
        meta = extract_metadata(self._soup(html))
        assert meta.title == "My Page"
        assert meta.title_length == 7

    def test_title_stripped(self):
        html = "<html><head><title>  Hello World  </title></head><body></body></html>"
        meta = extract_metadata(self._soup(html))
        assert meta.title == "Hello World"

    def test_empty_title(self):
        html = "<html><head><title></title></head><body></body></html>"
        meta = extract_metadata(self._soup(html))
        assert meta.title == ""
        assert meta.title_length == 0

    def test_no_title_tag(self):
        html = "<html><head></head><body><p>Content</p></body></html>"
        meta = extract_metadata(self._soup(html))
        assert meta.title == ""

    def test_meta_description(self):
        html = '<html><head><meta name="description" content="Test desc"></head><body></body></html>'
        meta = extract_metadata(self._soup(html))
        assert meta.meta_description == "Test desc"
        assert meta.meta_description_length == 9

    def test_no_meta_description(self):
        html = "<html><head></head><body></body></html>"
        meta = extract_metadata(self._soup(html))
        assert meta.meta_description == ""

    def test_canonical(self):
        html = '<html><head><link rel="canonical" href="https://example.com/canonical"></head><body></body></html>'
        meta = extract_metadata(self._soup(html))
        assert meta.canonical == "https://example.com/canonical"

    def test_robots_meta(self):
        html = '<html><head><meta name="robots" content="noindex, nofollow"></head><body></body></html>'
        meta = extract_metadata(self._soup(html))
        assert meta.robots_meta == "noindex, nofollow"

    def test_googlebot_meta(self):
        html = '<html><head><meta name="googlebot" content="noindex"></head><body></body></html>'
        meta = extract_metadata(self._soup(html))
        assert meta.googlebot == "noindex"

    def test_viewport(self):
        html = '<html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body></body></html>'
        meta = extract_metadata(self._soup(html))
        assert meta.viewport == "width=device-width, initial-scale=1"

    def test_favicon_rel_icon(self):
        html = '<html><head><link rel="icon" href="/favicon.ico"></head><body></body></html>'
        meta = extract_metadata(self._soup(html))
        assert meta.favicon == "/favicon.ico"

    def test_favicon_rel_shortcut(self):
        html = '<html><head><link rel="shortcut icon" href="/fav.ico"></head><body></body></html>'
        meta = extract_metadata(self._soup(html))
        assert meta.favicon == "/fav.ico"

    def test_open_graph_tags(self):
        html = '<html><head><meta property="og:title" content="OG Title"><meta property="og:description" content="OG Desc"></head><body></body></html>'
        meta = extract_metadata(self._soup(html))
        assert meta.open_graph["title"] == "OG Title"
        assert meta.open_graph["description"] == "OG Desc"

    def test_twitter_cards(self):
        html = '<html><head><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="Twitter Title"></head><body></body></html>'
        meta = extract_metadata(self._soup(html))
        assert meta.twitter["card"] == "summary_large_image"
        assert meta.twitter["title"] == "Twitter Title"

    def test_hreflang(self):
        html = '<html><head><link rel="alternate" hreflang="en" href="https://example.com/en"><link rel="alternate" hreflang="fr" href="https://example.com/fr"></head><body></body></html>'
        meta = extract_metadata(self._soup(html), "https://example.com")
        assert len(meta.hreflang) == 2
        assert meta.hreflang[0]["hreflang"] == "en"
        assert meta.hreflang[0]["url"] == "https://example.com/en"

    def test_hreflang_relative_url_resolved(self):
        html = '<html><head><link rel="alternate" hreflang="en" href="/en"></head><body></body></html>'
        meta = extract_metadata(self._soup(html), "https://example.com")
        assert meta.hreflang[0]["url"] == "https://example.com/en"

    def test_language_from_html_tag(self):
        html = '<html lang="fr"><head><title>T</title></head><body></body></html>'
        meta = extract_metadata(self._soup(html))
        assert meta.language == "fr"

class TestContentExtractor:
    def test_basic_text_extraction(self):
        html = "<html><body><p>Hello world</p><p>Second paragraph</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        result = extract_content(soup, html)
        assert "Hello world" in result.text
        assert "Second paragraph" in result.text

    def test_word_count(self):
        html = "<html><body><p>one two three four five</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        result = extract_content(soup, html)
        assert result.word_count == 5

    def test_empty_content(self):
        html = "<html><body></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        result = extract_content(soup, html)
        assert result.word_count == 0
        assert result.text == ""

    def test_headings_extracted(self):
        html = "<html><body><h1>H1</h1><h2>H2</h2><h3>H3</h3></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        result = extract_content(soup, html)
        assert result.headings["h1"] == ["H1"]
        assert result.headings["h2"] == ["H2"]
        assert result.headings["h3"] == ["H3"]

    def test_multiple_headings_same_level(self):
        html = "<html><body><h1>A</h1><h1>B</h1></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        result = extract_content(soup, html)
        assert result.headings["h1"] == ["A", "B"]

    def test_content_hash_is_md5(self):
        html = "<html><body><p>Test content</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        result = extract_content(soup, html)
        assert len(result.content_hash) == 32

    def test_soup_not_mutated(self):
        html = "<html><head><script type=""application/ld+json"">{""@type"": ""Org""}</script></head><body><nav><a href=""/"">H</a></nav><header><h1>T</h1></header><main><p>C</p></main><footer><p>F</p></footer></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        orig_scripts = len(soup.find_all("script", type="application/ld+json"))
        orig_navs = len(soup.find_all("nav"))
        orig_headers = len(soup.find_all("header"))
        orig_footers = len(soup.find_all("footer"))
        extract_content(soup, html)
        assert len(soup.find_all("script", type="application/ld+json")) == orig_scripts
        assert len(soup.find_all("nav")) == orig_navs
        assert len(soup.find_all("header")) == orig_headers
        assert len(soup.find_all("footer")) == orig_footers

    def test_shared_dom_preserves_json_ld(self):
        html = '<html><head><script type="application/ld+json">{"@type": "Article", "name": "Test"}</script></head><body><p>Content</p></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        extract_content(soup, html)
        scripts = soup.find_all("script", type="application/ld+json")
        assert len(scripts) == 1
        assert "Article" in scripts[0].string

class TestLinkExtractor:
    def _extract(self, html, base_url="https://example.com"):
        return extract_links(BeautifulSoup(html, "html.parser"), base_url)

    def test_anchor_links_extracted(self):
        html = '<html><body><a href="/page1">L1</a><a href="/page2">L2</a></body></html>'
        result = self._extract(html)
        assert len(result.links) == 2

    def test_absolute_url_resolution(self):
        html = '<html><body><a href="/page">Page</a></body></html>'
        result = self._extract(html)
        assert result.links[0]["url"] == "https://example.com/page"

    def test_external_link(self):
        html = '<html><body><a href="https://external.com/page">External</a></body></html>'
        result = self._extract(html)
        assert result.links[0]["is_external"] is True
        assert result.external_count == 1

    def test_internal_link(self):
        html = '<html><body><a href="/page">Internal</a></body></html>'
        result = self._extract(html)
        assert result.links[0]["is_internal"] is True
        assert result.internal_count == 1

    def test_fragment_skipped(self):
        html = '<html><body><a href="#section">Fragment</a></body></html>'
        result = self._extract(html)
        assert len(result.links) == 0

    def test_javascript_skipped(self):
        html = '<html><body><a href="javascript:void(0)">JS</a></body></html>'
        result = self._extract(html)
        assert len(result.links) == 0

    def test_mailto_skipped(self):
        html = '<html><body><a href="mailto:test@example.com">Email</a></body></html>'
        result = self._extract(html)
        assert len(result.links) == 0

    def test_nofollow_detected(self):
        html = '<html><body><a href="/page" rel="nofollow">NF</a></body></html>'
        result = self._extract(html)
        assert result.links[0]["nofollow"] is True

    def test_sponsored_detected(self):
        html = '<html><body><a href="/page" rel="sponsored">Ad</a></body></html>'
        result = self._extract(html)
        assert result.links[0]["sponsored"] is True

    def test_ugc_detected(self):
        html = '<html><body><a href="/page" rel="ugc">User</a></body></html>'
        result = self._extract(html)
        assert result.links[0]["ugc"] is True

    def test_canonical_link(self):
        html = '<html><head><link rel="canonical" href="https://example.com/canonical"></head><body></body></html>'
        result = self._extract(html)
        canonicals = [l for l in result.links if l["link_type"] == "canonical"]
        assert len(canonicals) == 1
        assert canonicals[0]["url"] == "https://example.com/canonical"

    def test_hreflang_links(self):
        html = '<html><head><link rel="alternate" hreflang="en" href="https://example.com/en"></head><body></body></html>'
        result = self._extract(html)
        hreflangs = [l for l in result.links if l["link_type"] == "hreflang"]
        assert len(hreflangs) == 1

    def test_anchor_text(self):
        html = '<html><body><a href="/page">Click Here</a></body></html>'
        result = self._extract(html)
        assert result.links[0]["anchor_text"] == "Click Here"

    def test_nav_link_type(self):
        html = '<html><body><nav><a href="/">Home</a></nav></body></html>'
        result = self._extract(html)
        assert result.links[0]["link_type"] == "navigation"

    def test_empty_href_skipped(self):
        html = '<html><body><a href="">Empty</a></body></html>'
        result = self._extract(html)
        assert len(result.links) == 0

class TestAssetExtractor:
    def _extract(self, html, base_url="https://example.com"):
        return extract_resources(BeautifulSoup(html, "html.parser"), base_url)

    def test_images_extracted(self):
        html = '<html><body><img src="/img.jpg" alt="test"></body></html>'
        result = self._extract(html)
        images = [r for r in result.resources if r["type"] == "image"]
        assert len(images) == 1
        assert images[0]["url"] == "https://example.com/img.jpg"
        assert images[0]["alt"] == "test"

    def test_image_absolute_url(self):
        html = '<html><body><img src="https://cdn.example.com/img.jpg"></body></html>'
        result = self._extract(html)
        images = [r for r in result.resources if r["type"] == "image"]
        assert images[0]["url"] == "https://cdn.example.com/img.jpg"

    def test_image_dimensions(self):
        html = '<html><body><img src="/img.jpg" width="100" height="200"></body></html>'
        result = self._extract(html)
        images = [r for r in result.resources if r["type"] == "image"]
        assert images[0]["width"] == 100
        assert images[0]["height"] == 200

    def test_image_lazy_loading(self):
        html = '<html><body><img src="/img.jpg" loading="lazy"></body></html>'
        result = self._extract(html)
        images = [r for r in result.resources if r["type"] == "image"]
        assert images[0]["loading"] == "lazy"
        assert images[0]["is_lazy"] is True

    def test_image_srcset(self):
        html = '<html><body><img src="/img.jpg" srcset="/small.jpg 480w, /large.jpg 1024w" sizes="100vw"></body></html>'
        result = self._extract(html)
        images = [r for r in result.resources if r["type"] == "image"]
        assert "/small.jpg" in images[0]["srcset"]
        assert images[0]["sizes"] == "100vw"

    def test_image_empty_src_skipped(self):
        html = '<html><body><img src=""></body></html>'
        result = self._extract(html)
        images = [r for r in result.resources if r["type"] == "image"]
        assert len(images) == 0

    def test_css_extracted(self):
        html = '<html><head><link rel="stylesheet" href="/style.css"></head><body></body></html>'
        result = self._extract(html)
        css = [r for r in result.resources if r["type"] == "css"]
        assert len(css) == 1
        assert css[0]["url"] == "https://example.com/style.css"
        assert css[0]["mime_type"] == "text/css"

    def test_javascript_extracted(self):
        html = '<html><body><script src="/app.js" async defer></script></body></html>'
        result = self._extract(html)
        js = [r for r in result.resources if r["type"] == "javascript"]
        assert len(js) == 1
        assert js[0]["url"] == "https://example.com/app.js"
        assert js[0]["async"] is True
        assert js[0]["defer"] is True
        assert js[0]["mime_type"] == "application/javascript"

    def test_inline_script_skipped(self):
        html = '<html><body><script>var x = 1;</script></body></html>'
        result = self._extract(html)
        js = [r for r in result.resources if r["type"] == "javascript"]
        assert len(js) == 0

    def test_favicon_extracted(self):
        html = '<html><head><link rel="icon" href="/favicon.ico"></head><body></body></html>'
        result = self._extract(html)
        favicons = [r for r in result.resources if r["type"] == "favicon"]
        assert len(favicons) == 1
        assert favicons[0]["url"] == "https://example.com/favicon.ico"

    def test_iframe_extracted(self):
        html = '<html><body><iframe src="/embed.html"></iframe></body></html>'
        result = self._extract(html)
        iframes = [r for r in result.resources if r["type"] == "iframe"]
        assert len(iframes) == 1
        assert iframes[0]["url"] == "https://example.com/embed.html"

    def test_video_extracted(self):
        html = '<html><body><video src="/video.mp4" poster="/poster.jpg"></video></body></html>'
        result = self._extract(html)
        videos = [r for r in result.resources if r["type"] == "video"]
        assert len(videos) == 1

    def test_audio_extracted(self):
        html = '<html><body><audio src="/audio.mp3" controls></audio></body></html>'
        result = self._extract(html)
        audios = [r for r in result.resources if r["type"] == "audio"]
        assert len(audios) == 1

    def test_multiple_resource_types(self):
        html = '<html><body><img src="/hero.jpg" alt="hero"><link rel="stylesheet" href="/style.css"><script src="/app.js"></script></body></html>'
        result = self._extract(html)
        types = {r["type"] for r in result.resources}
        assert types == {"image", "css", "javascript"}

class TestTechnicalExtractor:
    def test_basic_extraction(self):
        html = "<html><body><p>Test</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        result = extract_technical(
            status_code=200,
            headers={"content-type": "text/html"},
            content_length=100,
            response_time_ms=150,
            soup=soup,
            raw_html=html,
        )
        assert result.status_code == 200
        assert result.content_type == "text/html"
        assert result.content_length == 100
        assert result.response_time_ms == 150

    def test_security_headers_extracted(self):
        headers = {
            "strict-transport-security": "max-age=31536000",
            "content-security-policy": "default-src 'self'",
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
            "referrer-policy": "strict-origin-when-cross-origin",
        }
        result = extract_technical(
            status_code=200,
            headers=headers,
            content_length=100,
            response_time_ms=50,
        )
        assert result.security["headers"]["strict_transport_security"] == "max-age=31536000"
        assert result.security["headers"]["content_security_policy"] == "default-src 'self'"
        assert result.security["headers"]["x_content_type_options"] == "nosniff"
        assert result.security["headers"]["x_frame_options"] == "DENY"

    def test_no_security_headers(self):
        result = extract_technical(
            status_code=200,
            headers={"content-type": "text/html"},
            content_length=100,
            response_time_ms=50,
        )
        assert result.security["headers"] == {}

    def test_performance_extraction(self):
        html = '<html><head><link rel="stylesheet" href="/style.css"><script src="/a.js"></script><script src="/b.js"></script></head><body></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        result = extract_technical(
            status_code=200,
            headers={"content-type": "text/html"},
            content_length=200,
            response_time_ms=100,
            soup=soup,
            raw_html=html,
        )
        assert result.performance["load_time_ms"] == 100
        assert result.performance["render_blocking_count"] == 1
        assert result.performance["script_count"] == 3  # 2 external + 1 inline if present

    def test_accessibility_images(self):
        html = '<html><body><img src="/a.jpg" alt="text"><img src="/b.jpg" alt=""><img src="/c.jpg"></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        result = extract_technical(
            status_code=200,
            headers={"content-type": "text/html"},
            content_length=100,
            response_time_ms=50,
            soup=soup,
        )
        assert result.accessibility["images"]["total"] == 3
        assert result.accessibility["images"]["with_alt"] == 1
        assert result.accessibility["images"]["without_alt"] == 2

    def test_accessibility_forms(self):
        html = '<html><body><form><input id="name"><input aria-label="email"></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        result = extract_technical(
            status_code=200,
            headers={"content-type": "text/html"},
            content_length=100,
            response_time_ms=50,
            soup=soup,
        )
        assert result.accessibility["forms"]["total"] == 1
        assert result.accessibility["forms"]["inputs"] == 2

    def test_accessibility_buttons(self):
        html = "<html><body><button>Click</button><button>Submit</button></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        result = extract_technical(
            status_code=200,
            headers={"content-type": "text/html"},
            content_length=100,
            response_time_ms=50,
            soup=soup,
        )
        assert result.accessibility["buttons"]["total"] == 2

    def test_json_ld_extraction(self):
        html = '<html><head><script type="application/ld+json">{"@context": "https://schema.org", "@type": "Organization", "name": "Test"}</script></head><body></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        result = extract_technical(
            status_code=200,
            headers={"content-type": "text/html"},
            content_length=100,
            response_time_ms=50,
            soup=soup,
        )
        assert len(result.json_ld) == 1
        assert result.json_ld[0]["type"] == "Organization"

    def test_json_ld_malformed_skipped(self):
        html = '<html><head><script type="application/ld+json">{invalid json}</script></head><body></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        result = extract_technical(
            status_code=200,
            headers={"content-type": "text/html"},
            content_length=100,
            response_time_ms=50,
            soup=soup,
        )
        assert len(result.json_ld) == 0

    def test_json_ld_multiple_blocks(self):
        html = '<html><head><script type="application/ld+json">{"@type": "Article"}</script><script type="application/ld+json">{"@type": "Organization"}</script></head><body></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        result = extract_technical(
            status_code=200,
            headers={"content-type": "text/html"},
            content_length=100,
            response_time_ms=50,
            soup=soup,
        )
        assert len(result.json_ld) == 2

    def test_no_soup_no_json_ld(self):
        result = extract_technical(
            status_code=200,
            headers={"content-type": "text/html"},
            content_length=100,
            response_time_ms=50,
            soup=None,
        )
        assert result.json_ld == []

    def test_redirects_preserved(self):
        redirects = [{"url": "http://example.com", "status_code": 301}]
        result = extract_technical(
            status_code=200,
            headers={"content-type": "text/html"},
            content_length=100,
            response_time_ms=50,
            redirects=redirects,
        )
        assert len(result.redirects) == 1
        assert result.redirects[0]["status_code"] == 301
