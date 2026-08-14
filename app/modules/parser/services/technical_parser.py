"""
Backward compatibility: TechnicalParser → TechnicalExtractor (with legacy methods)
"""
from app.modules.parser.extractors.technical_extractor import TechnicalExtractor
from bs4 import BeautifulSoup


class TechnicalParser:
    """Legacy compatibility wrapper."""

    @staticmethod
    def get_viewport(soup: BeautifulSoup) -> str:
        ctx = type("C", (), {"soup": soup})()
        return TechnicalExtractor().extract(ctx).viewport

    @staticmethod
    def get_charset(soup: BeautifulSoup) -> str:
        ctx = type("C", (), {"soup": soup})()
        return TechnicalExtractor().extract(ctx).charset

    @staticmethod
    def get_doctype(html: str) -> str:
        return TechnicalExtractor().extract(
            type("C", (), {"soup": BeautifulSoup(html, "html.parser"), "doctype": "", "language": "", "charset": "", "warnings": [], "errors": []})()
        ).doctype

    @staticmethod
    def get_robots_meta(soup: BeautifulSoup) -> str:
        tag = soup.find("meta", attrs={"name": "robots"})
        return tag.get("content", "").strip() if tag else ""

    @staticmethod
    def get_html_language(soup: BeautifulSoup) -> str:
        html_tag = soup.find("html")
        return html_tag.get("lang", "").strip() if html_tag else ""

    @staticmethod
    def parse_http_headers(headers: dict) -> dict:
        if not headers:
            return {}
        return {
            "content_type": headers.get("content-type", ""),
            "content_encoding": headers.get("content-encoding", ""),
            "cache_control": headers.get("cache-control", ""),
            "x_robots_tag": headers.get("X-Robots-Tag", ""),
        }

    @staticmethod
    def check_mobile_friendly(soup: BeautifulSoup) -> dict:
        viewport = TechnicalParser.get_viewport(soup)
        return {
            "has_viewport": bool(viewport),
            "viewport_content": viewport,
            "is_mobile_friendly": bool(viewport),
        }

    @staticmethod
    def analyze_performance_indicators(soup: BeautifulSoup, html: str) -> dict:
        return {
            "html_size_bytes": len(html.encode("utf-8")) if html else 0,
            "script_count": len(soup.find_all("script")),
            "style_count": len(soup.find_all("style")),
        }


__all__ = ["TechnicalParser"]
