"""
Backward compatibility: HeadingParser → HeadingExtractor (with legacy methods)
"""
from app.modules.parser.extractors.heading_extractor import HeadingExtractor
from bs4 import BeautifulSoup


class HeadingParser:
    """Legacy compatibility wrapper."""

    @staticmethod
    def get_headings(soup: BeautifulSoup) -> dict:
        ctx = type("C", (), {"soup": soup})()
        items = HeadingExtractor().extract(ctx)
        result = {}
        for h in items:
            result.setdefault(f"h{h.level}", []).append(h.text)
        return result

    @staticmethod
    def get_heading_stats(soup: BeautifulSoup) -> dict:
        headings = HeadingParser.get_headings(soup)
        stats = {}
        for level in range(1, 7):
            stats[f"h{level}_count"] = len(headings.get(f"h{level}", []))
        stats["total_headings"] = sum(len(v) for v in headings.values())
        stats["has_h1"] = stats.get("h1_count", 0) > 0
        stats["multiple_h1"] = stats.get("h1_count", 0) > 1
        return stats

    @staticmethod
    def validate_heading_structure(soup: BeautifulSoup) -> dict:
        headings = HeadingParser.get_headings(soup)
        issues = []
        if not headings:
            issues.append("No headings found")
            return {"valid": False, "issues": issues}
        h1_count = len(headings.get("h1", []))
        if h1_count == 0:
            issues.append("Missing H1 tag")
        elif h1_count > 1:
            issues.append(f"Multiple H1 tags found ({h1_count})")
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "heading_count": sum(len(v) for v in headings.values()),
            "h1_count": h1_count,
        }


__all__ = ["HeadingParser"]
