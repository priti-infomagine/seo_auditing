from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup

from app.modules.parser.models.schema_data import SchemaData
from app.modules.parser.services.document_parser_service import DocumentContext
from app.modules.parser.normalizers.schema_normalizer import (
    normalize_json_ld_types,
    normalize_schema_context,
)


class SchemaExtractor:
    """
    Extracts structured data (JSON-LD, Microdata, RDFa).

    Malformed blocks are preserved with parse_error attributes
    rather than discarded.
    """

    def extract(self, context: DocumentContext) -> list[SchemaData]:
        soup = context.soup
        results = []
        results.extend(self._json_ld(soup))
        results.extend(self._microdata(soup))
        results.extend(self._rdfa(soup))
        return results

    @staticmethod
    def _json_ld(soup: BeautifulSoup) -> list[SchemaData]:
        results: list[SchemaData] = []

        for script in soup.find_all("script", type="application/ld+json"):
            raw = (script.string or script.get_text() or "").strip()
            if not raw:
                continue

            parsed: Any = None
            parse_error: str | None = None
            types: list[str] = []
            context_val = ""

            try:
                parsed = json.loads(raw)
                types = normalize_json_ld_types(parsed)
                context_val = normalize_schema_context(parsed) if isinstance(parsed, dict) else ""
            except (json.JSONDecodeError, TypeError) as exc:
                parse_error = str(exc)
                parsed = None

            attributes = {}
            if parse_error:
                attributes["parse_error"] = parse_error

            results.append(
                SchemaData(
                    format="json-ld",
                    raw=raw,
                    parsed=parsed,
                    types=types,
                    context=context_val,
                    attributes=attributes,
                )
            )

        return results

    @staticmethod
    def _microdata(soup: BeautifulSoup) -> list[SchemaData]:
        results: list[SchemaData] = []

        for tag in soup.find_all(attrs={"itemscope": True}):
            itemtype = tag.get("itemtype", "")
            itemprop_values: list[dict] = []

            for prop_tag in tag.find_all(attrs={"itemprop": True}):
                prop_name = prop_tag.get("itemprop", "")

                if prop_tag.has_attr("itemscope"):
                    prop_value = SchemaExtractor._microdata(prop_tag)
                elif prop_tag.name == "meta":
                    prop_value = prop_tag.get("content", "")
                elif prop_tag.name == "a":
                    prop_value = prop_tag.get("href", "")
                elif prop_tag.name == "time":
                    prop_value = prop_tag.get("datetime", "")
                else:
                    prop_value = prop_tag.get_text(strip=True)

                itemprop_values.append(
                    {"property": prop_name, "value": prop_value}
                )

            if itemtype:
                results.append(
                    SchemaData(
                        format="microdata",
                        raw=itemtype,
                        types=[itemtype],
                        attributes={
                            "itemid": tag.get("itemid", ""),
                            "itemref": tag.get("itemref", ""),
                            "properties": itemprop_values,
                        },
                    )
                )

        return results

    @staticmethod
    def _rdfa(soup: BeautifulSoup) -> list[SchemaData]:
        results: list[SchemaData] = []

        for tag in soup.find_all(attrs={"typeof": True}):
            typeof_val = tag.get("typeof", "")
            property_values: list[dict] = []

            for child in tag.find_all():
                prop = child.get("property", "")
                resource = child.get("resource", "")

                if prop:
                    text_val = child.get_text(strip=True)
                    property_values.append(
                        {
                            "property": prop,
                            "resource": resource,
                            "value": text_val,
                        }
                    )

            if typeof_val:
                results.append(
                    SchemaData(
                        format="rdfa",
                        raw=typeof_val,
                        types=[typeof_val],
                        attributes={
                            "about": tag.get("about", ""),
                            "vocab": tag.get("vocab", ""),
                            "prefix": tag.get("prefix", ""),
                            "properties": property_values,
                        },
                    )
                )

        return results
