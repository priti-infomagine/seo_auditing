from __future__ import annotations


def analyze_schemas(schemas: list) -> dict:
    json_ld_count = sum(1 for s in schemas if s.format == "json-ld")
    microdata_count = sum(1 for s in schemas if s.format == "microdata")
    rdfa_count = sum(1 for s in schemas if s.format == "rdfa")
    parse_errors = sum(1 for s in schemas if s.attributes.get("parse_error"))

    all_types: list[str] = []
    for s in schemas:
        all_types.extend(s.types or [])

    return {
        "total_schemas": len(schemas),
        "json_ld_count": json_ld_count,
        "microdata_count": microdata_count,
        "rdfa_count": rdfa_count,
        "parse_errors": parse_errors,
        "schema_types": list(set(all_types)),
    }
