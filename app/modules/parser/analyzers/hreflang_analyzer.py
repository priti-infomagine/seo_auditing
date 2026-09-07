from __future__ import annotations


def analyze_hreflang(hreflang_entries: list) -> dict:
    total = len(hreflang_entries)
    languages = list({
        entry.hreflang for entry in hreflang_entries
        if entry.hreflang and entry.hreflang.lower() != "x-default"
    })
    has_x_default = any(getattr(entry, "is_x_default", False) for entry in hreflang_entries)

    return {
        "total_hreflang": total,
        "language_count": len(languages),
        "languages": sorted(languages),
        "has_x_default": has_x_default,
    }
