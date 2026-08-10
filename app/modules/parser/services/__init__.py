"""
Parser Module
=============
Modular SEO parser components for analyzing crawled website data.

Architecture:
  HTMLParser   - Creates reusable DOM parsing context
  MetadataParser - Extracts title, meta, canonical, OG, Twitter, hreflang, favicon
  ContentParser  - Extracts text, headings, paragraphs, lists, tables, semantic HTML
  LinkParser     - Extracts all <a> elements
  ResourceParser - Extracts images, scripts, stylesheets, iframes, video, audio
  StructuredDataParser - Extracts JSON-LD, Microdata, RDFa
  ParserService  - Orchestrates all sub-parsers → ParsedDocument
  ParseService   - Pipeline adapter: crawl storage → ParserService → parsed storage
"""

from .html_parser import HTMLParser
from .metadata_parser import MetadataParser
from .content_parser import ContentParser
from .link_parser import LinkParser
from .resource_parser import ResourceParser
from .structured_data_parser import StructuredDataParser
from .parser_service import ParserService
from .parse_service import ParseService

__all__ = [
    "HTMLParser",
    "MetadataParser",
    "ContentParser",
    "LinkParser",
    "ResourceParser",
    "StructuredDataParser",
    "ParserService",
    "ParseService",
]
