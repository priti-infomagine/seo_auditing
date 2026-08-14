from .url_normalizer import (
    resolve_url,
    normalize_url,
    is_internal,
    normalize_rel,
)
from .text_normalizer import (
    normalize_text,
    normalize_whitespace,
    unescape_html,
    strip_zero_width,
)
from .attribute_normalizer import (
    normalize_rel_attribute,
    normalize_lang,
    normalize_boolean_attribute,
    normalize_loading,
    normalize_charset,
    normalize_attributes,
    normalize_link_data,
)
from .heading_normalizer import normalize_headings
from .link_normalizer import normalize_link, normalize_link_list
from .schema_normalizer import normalize_json_ld_types, normalize_schema_context
from .metadata_normalizer import (
    normalize_meta_tag_content,
    normalize_title,
    normalize_description,
    normalize_canonical,
)

__all__ = [
    "resolve_url",
    "normalize_url",
    "is_internal",
    "normalize_rel",
    "normalize_text",
    "normalize_whitespace",
    "unescape_html",
    "strip_zero_width",
    "normalize_rel_attribute",
    "normalize_lang",
    "normalize_boolean_attribute",
    "normalize_loading",
    "normalize_charset",
    "normalize_attributes",
    "normalize_link_data",
    "normalize_headings",
    "normalize_link",
    "normalize_link_list",
    "normalize_json_ld_types",
    "normalize_schema_context",
    "normalize_meta_tag_content",
    "normalize_title",
    "normalize_description",
    "normalize_canonical",
]
