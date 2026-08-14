"""
Backward compatibility: SEOParser — standalone legacy utility.
Not integrated into ParserOrchestrator pipeline.
"""
from bs4 import BeautifulSoup


class SEOParser:
    """Legacy SEO element extractor."""

    @staticmethod
    def get_title(soup: BeautifulSoup) -> str:
        title_tag = soup.find("title")
        return title_tag.string.strip() if title_tag and title_tag.string else ""

    @staticmethod
    def get_title_length(soup: BeautifulSoup) -> int:
        return len(SEOParser.get_title(soup))

    @staticmethod
    def get_meta_description(soup: BeautifulSoup) -> str:
        tag = soup.find("meta", attrs={"name": "description"})
        return tag.get("content", "").strip() if tag else ""

    @staticmethod
    def get_meta_description_length(soup: BeautifulSoup) -> int:
        return len(SEOParser.get_meta_description(soup))

    @staticmethod
    def get_meta_keywords(soup: BeautifulSoup) -> list:
        tag = soup.find("meta", attrs={"name": "keywords"})
        if tag:
            content = tag.get("content", "")
            return [kw.strip() for kw in content.split(",") if kw.strip()]
        return []

    @staticmethod
    def get_author(soup: BeautifulSoup) -> str:
        tag = soup.find("meta", attrs={"name": "author"})
        return tag.get("content", "").strip() if tag else ""

    @staticmethod
    def get_canonical(soup: BeautifulSoup) -> str:
        tag = soup.find("link", attrs={"rel": "canonical"})
        return tag.get("href", "").strip() if tag else ""

    @staticmethod
    def get_robots_meta(soup: BeautifulSoup) -> str:
        tag = soup.find("meta", attrs={"name": "robots"})
        return tag.get("content", "").strip() if tag else ""

    @staticmethod
    def get_url_structure(url: str) -> dict:
        from urllib.parse import urlparse
        if not url:
            return {"valid": False, "issues": ["Empty URL"]}
        parsed = urlparse(url)
        issues = []
        if "://" not in url:
            issues.append("Missing protocol")
        if parsed.path and "//" in parsed.path:
            issues.append("Double slashes in path")
        if " " in url:
            issues.append("URL contains spaces")
        if len(url) > 200:
            issues.append("URL too long (>200 chars)")
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "scheme": parsed.scheme,
            "netloc": parsed.netloc,
            "path": parsed.path,
        }


__all__ = ["SEOParser"]
