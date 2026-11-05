def _extract_types_recursive(obj: dict | list) -> list[str]:
    """Recursively extract @type from dict or list, handling nested @graph."""
    types: list[str] = []
    
    if isinstance(obj, dict):
        # Check for @type at current level
        raw_type = obj.get("@type")
        if raw_type:
            types.extend([raw_type] if isinstance(raw_type, str) else list(raw_type))
        
        # Recursively check @graph
        if "@graph" in obj and isinstance(obj["@graph"], list):
            for node in obj["@graph"]:
                types.extend(_extract_types_recursive(node))
        
        # Also check nested dicts for @type (e.g., in properties)
        for key, value in obj.items():
            if key != "@type" and key != "@graph" and isinstance(value, (dict, list)):
                types.extend(_extract_types_recursive(value))
    
    elif isinstance(obj, list):
        for item in obj:
            types.extend(_extract_types_recursive(item))
    
    return types


def normalize_json_ld_types(parsed: dict | list | None) -> list[str]:
    """Extract all @type values from JSON-LD, including nested @graph and arrays."""
    if parsed is None:
        return []
    return _extract_types_recursive(parsed)


def normalize_schema_context(parsed: dict | None) -> str:
    """Extract @context from JSON-LD, checking nested @graph as well."""
    if not isinstance(parsed, dict):
        return ""
    
    # Check top-level @context
    context = parsed.get("@context")
    if context:
        return str(context)
    
    # Check @graph for @context
    if "@graph" in parsed and isinstance(parsed["@graph"], list):
        for node in parsed["@graph"]:
            if isinstance(node, dict):
                node_context = node.get("@context")
                if node_context:
                    return str(node_context)
    
    return ""
