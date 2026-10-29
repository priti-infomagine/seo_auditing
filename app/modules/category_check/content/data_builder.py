"""
Data enrichment builder for content rules.

Provides build_content_rule_data() — a standalone function that builds
the enriched data dict consumed by content rules, leveraging
ContentPageParser's extended analysis methods.

This mirrors the approach of PageParser.build_rule_data() but adds
content-specific enrichment: pixel widths, reading grade, keyword
density, heading lengths, HTML structure validation, and meta-in-body
detection.
"""
from __future__ import annotations

from typing import Any

from app.modules.category_check.core_seo.models import ParsedPage
from .page_parser import ContentPageParser


def build_content_rule_data(
    parsed: ParsedPage,
    crawl_result: Any = None,
    config: Any = None,
) -> dict[str, Any]:
    """Build the enriched data dict for content rule evaluation.

    Args:
        parsed: ParsedPage from the content parser.
        crawl_result: CrawlResult with HTML and status.
        config: Optional ContentConfig (currently unused, reserved for future
            threshold overrides).

    Returns:
        dict with all base rule_data fields PLUS content-specific fields:
            - text_to_html_ratio
            - title_pixel_width
            - meta_description_pixel_width
            - reading_grade
            - keyword_density
            - heading_lengths
            - html_structure_errors
            - meta_tags_in_body
            - content_type
    """
    parser = ContentPageParser()
    return parser.build_content_rule_data(parsed, crawl_result, config)


__all__ = ["build_content_rule_data"]
