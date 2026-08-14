def normalize_json_ld_types(parsed: dict | list | None) -> list[str]:
    if parsed is None:
        return []

    if isinstance(parsed, dict):
        raw_type = parsed.get("@type")
        if raw_type:
            return [raw_type] if isinstance(raw_type, str) else list(raw_type)
        if "@graph" in parsed and isinstance(parsed["@graph"], list):
            types: list[str] = []
            for node in parsed["@graph"]:
                if isinstance(node, dict):
                    node_type = node.get("@type")
                    if node_type:
                        types.extend([node_type] if isinstance(node_type, str) else list(node_type))
            return types

    if isinstance(parsed, list):
        types: list[str] = []
        for item in parsed:
            if isinstance(item, dict):
                item_type = item.get("@type")
                if item_type:
                    types.extend([item_type] if isinstance(item_type, str) else list(item_type))
        return types

    return []


def normalize_schema_context(parsed: dict | None) -> str:
    if not isinstance(parsed, dict):
        return ""
    return str(parsed.get("@context", "") or "")
