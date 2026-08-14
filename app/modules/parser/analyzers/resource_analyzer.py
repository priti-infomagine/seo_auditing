from __future__ import annotations


def analyze_resources(resources: list) -> dict:
    by_type: dict[str, int] = {}
    for r in resources:
        by_type[r.resource_type] = by_type.get(r.resource_type, 0) + 1

    return {
        "total_resources": len(resources),
        "by_type": by_type,
    }
