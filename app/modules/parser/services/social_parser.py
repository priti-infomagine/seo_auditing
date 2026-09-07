"""
Backward compatibility: SocialParser → SocialExtractor (with legacy methods)
"""
from app.modules.parser.extractors.social_extractor import SocialExtractor
from bs4 import BeautifulSoup


class SocialParser:
    """Legacy compatibility wrapper."""

    SOCIAL_DOMAINS = SocialExtractor.SOCIAL_DOMAINS

    @staticmethod
    def get_open_graph(soup: BeautifulSoup) -> dict:
        ctx = type("C", (), {"soup": soup})()
        return SocialExtractor().extract(ctx).open_graph.tags

    @staticmethod
    def get_twitter_cards(soup: BeautifulSoup) -> dict:
        ctx = type("C", (), {"soup": soup})()
        return SocialExtractor().extract(ctx).twitter.tags

    @staticmethod
    def has_social_tags(soup: BeautifulSoup) -> bool:
        og = SocialParser.get_open_graph(soup)
        tw = SocialParser.get_twitter_cards(soup)
        return bool(og or tw)

    @staticmethod
    def get_social_summary(soup: BeautifulSoup) -> dict:
        return {
            "open_graph": {
                "present": bool(SocialParser.get_open_graph(soup)),
                "tags_count": len(SocialParser.get_open_graph(soup)),
                "tags": SocialParser.get_open_graph(soup),
            },
            "twitter_cards": {
                "present": bool(SocialParser.get_twitter_cards(soup)),
                "tags_count": len(SocialParser.get_twitter_cards(soup)),
                "tags": SocialParser.get_twitter_cards(soup),
            },
            "social_links": {"count": 0, "platforms": [], "links": []},
        }


__all__ = ["SocialParser"]
