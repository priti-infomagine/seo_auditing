from __future__ import annotations


def analyze_headings(content_data) -> dict:
    headings = content_data.headings or []
    counts = {f"h{i}": 0 for i in range(1, 7)}
    for h in headings:
        level = h.level
        if 1 <= level <= 6:
            counts[f"h{level}"] += 1

    total = len(headings)
    levels = [h.level for h in headings]
    is_sequential = _is_sequential(levels)

    has_h1 = counts["h1"] > 0

    return {
        **counts,
        "total_headings": total,
        "is_sequential": is_sequential,
        "has_h1": has_h1,
    }


def _is_sequential(levels: list[int]) -> bool:
    if not levels:
        return True
    for i in range(1, len(levels)):
        if levels[i] > levels[i - 1] + 1:
            return False
    return True
