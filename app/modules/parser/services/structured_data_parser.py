import json
from typing import Any

from bs4 import BeautifulSoup

from ..schemas.structured_data_schema import StructuredDataItem


class StructuredDataParser:
    """
    Extracts structured data from HTML.

    Supports JSON-LD, Microdata, and RDFa.
    Malformed entries are preserved with parse errors rather than discarded.
    """

    def parse(self, context) -> list[StructuredDataItem]:
        soup = context.soup
        results: list[StructuredDataItem] = []

        results.extend(self._json_ld(soup))
        results.extend(self._microdata(soup))
        results.extend(self._rdfa(soup))

        return results

    @staticmethod
    def _json_ld(soup: BeautifulSoup) -> list[StructuredDataItem]:
        import json

        results: list[StructuredDataItem] = []

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

                if isinstance(parsed, dict):
                    context_val = str(parsed.get("@context", "") or "")
                    raw_type = parsed.get("@type")

                    if raw_type:
                        types = (
                            [raw_type]
                            if isinstance(raw_type, str)
                            else list(raw_type)
                        )

                    if "@graph" in parsed and isinstance(parsed["@graph"], list):
                        for node in parsed["@graph"]:
                            if isinstance(node, dict):
                                node_type = node.get("@type")
                                if node_type:
                                    types.extend(
                                        [node_type]
                                        if isinstance(node_type, str)
                                        else list(node_type)
                                    )

                elif isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            item_type = item.get("@type")
                            if item_type:
                                types.extend(
                                    [item_type]
                                    if isinstance(item_type, str)
                                    else list(item_type)
                                )

            except (json.JSONDecodeError, TypeError) as exc:
                parse_error = str(exc)
                parsed = None

            results.append(
                StructuredDataItem(
                    format="json-ld",
                    raw=raw,
                    parsed=parsed,
                    types=types,
                    context=context_val,
                    attributes={"parse_error": parse_error}
                    if parse_error
                    else {},
                )
            )

        return results

    @staticmethod
    def _microdata(soup: BeautifulSoup) -> list[StructuredDataItem]:
        results: list[StructuredDataItem] = []

        for tag in soup.find_all(attrs={"itemscope": True}):
            itemtype = tag.get("itemtype", "")
            itemprop_values: list[dict] = []

            for prop_tag in tag.find_all(attrs={"itemprop": True}):
                prop_name = prop_tag.get("itemprop", "")

                if prop_tag.has_attr("itemscope"):
                    prop_value = StructuredDataParser._microdata(
                        prop_tag
                    )
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
                    StructuredDataItem(
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
    def _rdfa(soup: BeautifulSoup) -> list[StructuredDataItem]:
        results: list[StructuredDataItem] = []

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
                    StructuredDataItem(
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
