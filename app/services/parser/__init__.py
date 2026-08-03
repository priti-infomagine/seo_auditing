"""
Parser Module
=============
Modular SEO parser components for analyzing crawled website data.

This module provides a collection of specialized parsers for extracting
SEO-relevant information from HTML pages. Each parser focuses on a specific
aspect of SEO analysis:

- HTMLParser: Basic HTML structure and metadata
- SEOParser: Core SEO elements (title, meta tags, keywords)
- ContentParser: Page content analysis
- HeadingParser: Heading structure (H1-H6)
- LinkParser: Internal and external link analysis
- ImageParser: Image optimization checks
- SchemaParser: Structured data and schema.org markup
- SocialParser: Social media tags and links
- TechnicalParser: Technical SEO and HTTP information
- GeoParser: Local SEO and geographic information
- ParserService: Orchestrates all parsers for comprehensive analysis
"""

from .html_parser import HTMLParser
from .seo_parser import SEOParser
from .content_parser import ContentParser
from .heading_parser import HeadingParser
from .link_parser import LinkParser
from .image_parser import ImageParser
from .schema_parser import SchemaParser
from .social_parser import SocialParser
from .technical_parser import TechnicalParser
from .geo_parser import GeoParser
from .parser_service import ParserService
from .parse_service import ParseService

__all__ = [
    'HTMLParser',
    'SEOParser',
    'ContentParser',
    'HeadingParser',
    'LinkParser',
    'ImageParser',
    'SchemaParser',
    'SocialParser',
    'TechnicalParser',
    'GeoParser',
    'ParserService',
    'ParseService'
]
