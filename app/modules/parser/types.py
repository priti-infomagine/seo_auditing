from typing import Literal

ExtractorName = Literal[
    "metadata",
    "content",
    "heading",
    "link",
    "image",
    "schema",
    "hreflang",
    "social",
    "resource",
    "technical",
]

ParserVersion = str
