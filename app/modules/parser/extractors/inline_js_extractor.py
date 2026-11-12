from __future__ import annotations

from bs4 import BeautifulSoup

from app.modules.parser.models.inline_js_data import InlineJSData
from app.modules.parser.services.document_parser_service import DocumentContext


class InlineJSExtractor:
    """Extracts inline JavaScript blocks and analyzes minification."""

    def extract(self, context: DocumentContext) -> list[InlineJSData]:
        soup = context.soup
        results = []

        for script in soup.find_all("script"):
            if script.get("src"):  # Skip external scripts
                continue
            content = script.string or ""
            whitespace = sum(1 for c in content if c.isspace())
            total = len(content)
            whitespace_pct = (whitespace / total * 100) if total > 0 else 0
            size_kb = len(content.encode("utf-8")) / 1024
            attrs = {str(k): str(v) for k, v in script.attrs.items()}

            results.append(InlineJSData(
                content=content[:500],
                size_kb=size_kb,
                whitespace_percentage=round(whitespace_pct, 1),
                is_minified=whitespace_pct < 10,
                attributes=attrs,
            ))

        return results