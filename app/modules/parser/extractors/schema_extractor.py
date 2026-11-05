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
from app.modules.parser.services.schema_validator import SchemaValidator


class SchemaExtractor:
    """
    Extracts structured data (JSON-LD, Microdata, RDFa).

    Malformed blocks are preserved with parse_error attributes
    rather than discarded.
    """

    def __init__(self):
        self.validator = SchemaValidator()

    def extract(self, context: DocumentContext) -> list[SchemaData]:
        soup = context.soup
        results = []
        results.extend(self._json_ld(soup))
        results.extend(self._microdata(soup))
        results.extend(self._rdfa(soup))
        # Validate all extracted schemas
        results = self.validator.validate_all(results)
        return results

    def _json_ld(self, soup: BeautifulSoup) -> list[SchemaData]:
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

    def _microdata(self, soup: BeautifulSoup) -> list[SchemaData]:
        results: list[SchemaData] = []

        for tag in soup.find_all(attrs={"itemscope": True}):
            itemtype = tag.get("itemtype", "")
            itemprop_values: list[dict] = []

            for prop_tag in tag.find_all(attrs={"itemprop": True}):
                prop_name = prop_tag.get("itemprop", "")

                # Handle nested itemscope - extract its properties
                if prop_tag.has_attr("itemscope"):
                    nested_data = self._extract_microdata_item(prop_tag)
                    prop_value = nested_data
                elif prop_tag.name == "meta":
                    prop_value = prop_tag.get("content", "")
                elif prop_tag.name in ("a", "link"):
                    prop_value = prop_tag.get("href", "")
                elif prop_tag.name == "time":
                    prop_value = prop_tag.get("datetime", "")
                elif prop_tag.name in ("img", "image"):
                    prop_value = prop_tag.get("src", "")
                elif prop_tag.name in ("video", "audio"):
                    prop_value = prop_tag.get("src", "")
                elif prop_tag.name == "object":
                    prop_value = prop_tag.get("data", "")
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

    def _extract_microdata_item(self, tag) -> dict:
        """Recursively extract properties from a nested itemscope element."""
        itemtype = tag.get("itemtype", "")
        itemid = tag.get("itemid", "")
        itemref = tag.get("itemref", "")
        properties: list[dict] = []

        for prop_tag in tag.find_all(attrs={"itemprop": True}):
            prop_name = prop_tag.get("itemprop", "")

            if prop_tag.has_attr("itemscope"):
                # Recursively extract nested item
                nested_data = self._extract_microdata_item(prop_tag)
                prop_value = nested_data
            elif prop_tag.name == "meta":
                prop_value = prop_tag.get("content", "")
            elif prop_tag.name in ("a", "link"):
                prop_value = prop_tag.get("href", "")
            elif prop_tag.name == "time":
                prop_value = prop_tag.get("datetime", "")
            elif prop_tag.name in ("img", "image"):
                prop_value = prop_tag.get("src", "")
            elif prop_tag.name in ("video", "audio"):
                prop_value = prop_tag.get("src", "")
            elif prop_tag.name == "object":
                prop_value = prop_tag.get("data", "")
            else:
                prop_value = prop_tag.get_text(strip=True)

            properties.append({"property": prop_name, "value": prop_value})

        result = {
            "@type": itemtype,
            "properties": properties,
        }
        if itemid:
            result["@id"] = itemid
        if itemref:
            result["itemref"] = itemref
        return result

    def _rdfa(self, soup: BeautifulSoup) -> list[SchemaData]:
        results: list[SchemaData] = []

        for tag in soup.find_all(attrs={"typeof": True}):
            typeof_val = tag.get("typeof", "")
            property_values: list[dict] = []

            for child in tag.find_all():
                prop = child.get("property", "")
                resource = child.get("resource", "")

                if prop:
                    # Extract value based on element type and attributes
                    value = self._extract_rdfa_value(child)
                    property_values.append(
                        {
                            "property": prop,
                            "resource": resource,
                            "value": value,
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

    def _extract_rdfa_value(self, element) -> Any:
        """Extract RDFa value from element based on its type and attributes."""
        tag_name = element.name
        
        # Check for explicit content attribute (highest priority)
        if element.has_attr("content"):
            return element.get("content", "")
        
        # Check for href/src/resource attributes
        if tag_name in ("a", "link") and element.has_attr("href"):
            return element.get("href", "")
        if tag_name in ("img", "image") and element.has_attr("src"):
            return element.get("src", "")
        if tag_name in ("video", "audio") and element.has_attr("src"):
            return element.get("src", "")
        if tag_name == "object" and element.has_attr("data"):
            return element.get("data", "")
        if tag_name == "time" and element.has_attr("datetime"):
            return element.get("datetime", "")
        if element.has_attr("resource"):
            return element.get("resource", "")
        
        # Fallback to text content
        return element.get_text(strip=True)
