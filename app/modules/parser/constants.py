"""
Constants used by the parser module.

Keep this module limited to parser/document-level configuration.
SEO thresholds and pass/fail rules belong to the rule engine.
"""

DEFAULT_PARSER = "html.parser"

SUPPORTED_DOCUMENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
}

META_DESCRIPTION_NAME = "description"
META_ROBOTS_NAME = "robots"
META_VIEWPORT_NAME = "viewport"

OPEN_GRAPH_PREFIX = "og:"
TWITTER_PREFIX = "twitter:"

HEADING_TAGS = (
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
)

LINK_REL_VALUES = {
    "canonical",
    "alternate",
    "prev",
    "next",
    "author",
    "bookmark",
    "external",
    "help",
    "license",
    "nofollow",
    "noopener",
    "noreferrer",
    "ugc",
    "sponsored",
    "tag",
}

RESOURCE_TAGS = {
    "img",
    "script",
    "link",
    "iframe",
    "video",
    "audio",
    "source",
    "track",
    "embed",
    "object",
}

SEMANTIC_TAGS = {
    "main",
    "article",
    "section",
    "nav",
    "header",
    "footer",
    "aside",
    "figure",
    "figcaption",
    "address",
    "time",
}

__all__ = [
    "DEFAULT_PARSER",
    "SUPPORTED_DOCUMENT_TYPES",
    "META_DESCRIPTION_NAME",
    "META_ROBOTS_NAME",
    "META_VIEWPORT_NAME",
    "OPEN_GRAPH_PREFIX",
    "TWITTER_PREFIX",
    "HEADING_TAGS",
    "LINK_REL_VALUES",
    "RESOURCE_TAGS",
    "SEMANTIC_TAGS",
]