"""
Rule → response registries.

A single source of truth mapping rule_ids to:
  * affected_part        — what specific thing the rule inspects (spec §5)
  * response category    — id + display name (spec §6)
  * subcategory key      — the category_results sub-check it rolls up under (spec §14)
  * recommendation       — rule-level action text + effort (spec §16)
  * high-impact warnings — WARNING rules promoted to 'high' tier (decision #8)

If a rule_id is absent from RULE_AFFECTED_PART the converter emits
affected_part="unknown" and logs it for correction.
"""
from typing import Dict

# ---------------------------------------------------------------------------
# rule_id -> affected_part (the specific thing inspected on the page)
# ---------------------------------------------------------------------------
RULE_AFFECTED_PART: Dict[str, str] = {
    # on_page
    "on_page_001": "title",
    "on_page_002": "meta_description",
    "on_page_003": "h1",
    "on_page_004": "heading_hierarchy",
    "on_page_005": "meta_keywords",
    "on_page_006": "canonical",
    "on_page_007": "robots_meta",
    "on_page_008": "open_graph",
    "on_page_009": "twitter_cards",
    # content
    "content_001": "word_count",
    "content_002": "reading_time",
    "content_003": "paragraph_structure",
    "content_004": "text_html_ratio",
    "content_005": "keyword_density",
    "content_006": "duplicate_content",
    "content_007": "content_freshness",
    # security
    "security_001": "https",
    "security_002": "mixed_content",
    "security_003": "security_headers",
    "security_004": "ssl_certificate",
    "security_005": "hsts",
    "security_006": "xss_protection",
    # links
    "links_001": "internal_links",
    "links_002": "external_links",
    "links_003": "broken_links",
    "links_004": "anchor_text",
    "links_005": "nofollow_links",
    # schema
    "schema_001": "structured_data",
    "schema_002": "organization_schema",
    "schema_003": "breadcrumb_schema",
    "schema_004": "article_schema",
    "schema_005": "product_schema",
    "schema_006": "json_ld_format",
    # accessibility
    "a11y_001": "image_alt_text",
    "a11y_002": "language",
    "a11y_003": "heading_structure",
    "a11y_004": "link_text",
    "a11y_005": "color_contrast",
    "a11y_006": "keyboard_navigation",
    "a11y_007": "aria_labels",
    "a11y_008": "form_labels",
    # social
    "social_001": "open_graph",
    "social_002": "twitter_cards",
    "social_003": "social_media_links",
    "social_004": "facebook_domain",
    "social_005": "social_image",
    # images
    "images_001": "image_alt_text",
    "images_002": "image_file_size",
    "images_003": "lazy_loading",
    "images_004": "image_dimensions",
    "images_005": "responsive_images",
    "images_006": "image_formats",
    # performance
    "perf_001": "response_time",
    "perf_002": "html_document_size",
    "perf_003": "code_minification",
    "perf_004": "resource_count",
    "perf_005": "browser_caching",
    "perf_006": "compression",
    "perf_007": "total_page_size",
    "perf_008": "javascript_errors",
    # technical
    "technical_001": "ssl_certificate",
    "technical_002": "viewport",
    "technical_003": "language",
    "technical_004": "charset",
    "technical_005": "doctype",
    "technical_006": "html_lang",
    "technical_007": "security_headers",
    "technical_008": "robots_txt",
    "technical_009": "sitemap",
    "technical_010": "structured_data",
}

# WARNING rules whose failure is high-impact and therefore promoted to 'high'.
# (Spec forbids deriving severity from score_impact; this is the explicit override set.)
HIGH_IMPACT_WARNINGS: set = {
    "links_003",        # broken links
    "links_004",        # anchor text quality
    "content_001",      # word count (thin/short content)
    "content_006",      # duplicate content
    "on_page_006",      # missing canonical
    "on_page_007",      # nofollow / noindex directive
    "technical_007",    # missing security headers
    "technical_010",    # missing structured data
    "images_001",       # image alt text
    "images_004",       # image dimensions (CLS risk)
    "a11y_001",         # image alt text
    "security_003",     # security headers
    "security_004",     # ssl certificate issues
    "schema_001",       # missing schema markup
    "perf_001",         # slow response time / TTFB
    "perf_008",         # javascript errors
}

# ---------------------------------------------------------------------------
# internal category -> response category id + display name (spec §6)
# ---------------------------------------------------------------------------
CATEGORY_DISPLAY: Dict[str, Dict[str, str]] = {
    "on_page":        {"id": "on_page",            "name": "On-Page SEO"},
    "technical":      {"id": "technical_seo",      "name": "Technical SEO"},
    "content":        {"id": "content_quality",    "name": "Content Quality"},
    "links":          {"id": "internal_linking",   "name": "Internal Linking"},
    "images":         {"id": "images_media",       "name": "Images & Media"},
    "schema":         {"id": "structured_data",    "name": "Structured Data"},
    "social":         {"id": "social",             "name": "Social"},
    "security":       {"id": "security_trust",     "name": "Security & Trust"},
    "accessibility":  {"id": "accessibility",      "name": "Accessibility"},
    "performance":    {"id": "performance",        "name": "Performance"},
}

# ---------------------------------------------------------------------------
# rule_id -> category_results sub-check key (spec §14)
# Multiple rule_ids may share a sub-check key and roll up together.
# ---------------------------------------------------------------------------
SUBCATEGORY_OF: Dict[str, str] = {
    "on_page_001": "titles",
    "on_page_002": "meta_descriptions",
    "on_page_003": "h1",
    "on_page_004": "headings",
    "on_page_006": "canonical",
    "on_page_007": "robots",
    "on_page_008": "open_graph",
    "on_page_009": "twitter_cards",
    "technical_001": "https",
    "technical_002": "viewport",
    "technical_004": "charset",
    "technical_005": "doctype",
    "technical_006": "html_lang",
    "technical_007": "security_headers",
    "technical_008": "robots_txt",
    "technical_009": "sitemap",
    "technical_010": "structured_data",
    "security_001": "https",
    "security_002": "mixed_content",
    "security_003": "security_headers",
    "security_004": "ssl_certificate",
    "security_005": "hsts",
    "security_006": "xss_protection",
    "content_001": "word_count",
    "content_002": "reading_time",
    "content_006": "duplicate_content",
    "links_001": "internal_links",
    "links_002": "external_links",
    "links_003": "broken_links",
    "links_004": "anchor_text",
    "images_001": "image_alt",
    "images_002": "image_file_size",
    "images_003": "lazy_loading",
    "images_004": "image_dimensions",
    "images_005": "responsive_images",
    "images_006": "image_formats",
    "schema_001": "structured_data",
    "perf_001": "response_time",
    "perf_006": "compression",
    "perf_007": "total_page_size",
    "social_001": "open_graph",
    "social_002": "twitter_cards",
    "a11y_001": "alt_text",
    "a11y_003": "heading_structure",
    "a11y_004": "link_text",
}

# Sub-checks that have no rule backing them (rendered as not_available).
SUBCATEGORY_NOT_AVAILABLE: set = {
    "redirects",             # requires redirect-chain rule
    "canonical_conflicts",   # requires site-wide check
    "duplicate_titles",      # requires site-wide check
    "orphan_pages",
    "near_duplicate_pages",
    "duplicate_descriptions",
}

# ---------------------------------------------------------------------------
# rule_id -> recommendation (spec §16)
# ---------------------------------------------------------------------------
RECOMMENDATIONS: Dict[str, Dict[str, str]] = {
    "on_page_001": {"action": "Add a descriptive <title> (30-70 chars).", "effort": "low"},
    "on_page_002": {"action": "Add a unique, relevant meta description (150-160 chars).", "effort": "low"},
    "on_page_003": {"action": "Add a single <h1> containing your primary keyword.", "effort": "low"},
    "on_page_004": {"action": "Organize headings in a logical H1→H2→H3 hierarchy.", "effort": "low"},
    "on_page_006": {"action": "Add <link rel='canonical'> to the preferred URL.", "effort": "low"},
    "on_page_007": {"action": "Review robots meta / X-Robots-Tag directives.", "effort": "low"},
    "on_page_008": {"action": "Add required Open Graph tags (og:title, og:description, og:image, og:url).", "effort": "low"},
    "on_page_009": {"action": "Add Twitter Card meta tags.", "effort": "low"},
    "content_001": {"action": "Expand thin pages to at least 300 words of useful content.", "effort": "medium"},
    "content_006": {"action": "Rewrite or canonicalize duplicate content.", "effort": "medium"},
    "technical_001": {"action": "Enable HTTPS and redirect all traffic to HTTPS.", "effort": "medium"},
    "technical_002": {"action": "Add <meta name='viewport' content='width=device-width, initial-scale=1.0'>.", "effort": "low"},
    "technical_005": {"action": "Add <!DOCTYPE html> at the start of every HTML document.", "effort": "low"},
    "technical_007": {"action": "Set HSTS, X-Content-Type-Options, X-Frame-Options, Content-Security-Policy headers.", "effort": "medium"},
    "technical_010": {"action": "Add Schema.org JSON-LD markup to enable rich results.", "effort": "medium"},
    "links_003": {"action": "Fix or remove broken internal links.", "effort": "medium"},
    "links_004": {"action": "Replace generic anchor text (e.g. 'click here') with descriptive text.", "effort": "medium"},
    "images_001": {"action": "Add descriptive alt text to images missing it.", "effort": "medium"},
    "images_004": {"action": "Specify width/height attributes to prevent Cumulative Layout Shift.", "effort": "low"},
    "schema_001": {"action": "Add JSON-LD structured data for key page types.", "effort": "medium"},
    "perf_001": {"action": "Reduce server response time (optimize queries, use caching, CDN).", "effort": "medium"},
    "perf_008": {"action": "Fix client-side JavaScript errors shown in the browser console.", "effort": "medium"},
    "social_001": {"action": "Add required Open Graph meta tags for social sharing.", "effort": "low"},
    "security_002": {"action": "Serve all resources over HTTPS; fix mixed-content warnings.", "effort": "medium"},
}

# Human-readable title fallback per rule_id (for recommendations/priorities display).
RULE_TITLES: Dict[str, str] = {
    "on_page_001": "Missing or poor page title",
    "on_page_002": "Missing or poorly sized meta description",
    "on_page_003": "Missing or multiple H1 tags",
    "on_page_004": "Illogical heading hierarchy",
    "on_page_006": "Missing canonical URL",
    "on_page_007": "Indexability restricted by robots meta",
    "content_001": "Thin or overly long content",
    "content_006": "Duplicate content detected",
    "technical_001": "Not using HTTPS",
    "technical_005": "Missing DOCTYPE declaration",
    "technical_007": "Missing or incomplete security headers",
    "technical_010": "Missing structured data / schema markup",
    "links_003": "Broken links detected",
    "links_004": "Generic or non-descriptive anchor text",
    "images_001": "Images missing alt text",
    "images_004": "Images missing width/height dimensions",
    "schema_001": "Missing schema markup",
    "perf_001": "Slow server response time (TTFB)",
    "perf_008": "JavaScript errors detected",
    "social_001": "Missing Open Graph tags",
    "security_002": "Mixed content detected",
    "security_004": "SSL certificate issue",
}
