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
    def get_social_links(soup: BeautifulSoup) -> list:
        ctx = type("C", (), {"soup": soup})()
        return [
            {"platform": link.platform, "url": link.url, "text": link.text}
            for link in SocialExtractor().extract(ctx).social_links
        ]

    @staticmethod
    def get_sharing_buttons(soup: BeautifulSoup) -> list:
        ctx = type("C", (), {"soup": soup})()
        return [
            {"platform": btn.platform, "selector": btn.selector, "url": btn.url, "text": btn.text}
            for btn in SocialExtractor().extract(ctx).sharing_buttons
        ]

    @staticmethod
    def has_social_tags(soup: BeautifulSoup) -> bool:
        og = SocialParser.get_open_graph(soup)
        tw = SocialParser.get_twitter_cards(soup)
        return bool(og or tw)

    @staticmethod
    def get_social_summary(soup: BeautifulSoup) -> dict:
        ctx = type("C", (), {"soup": soup})()
        extracted = SocialExtractor().extract(ctx)

        social_links = [
            {"platform": link.platform, "url": link.url, "text": link.text}
            for link in extracted.social_links
        ]
        platforms = list({link["platform"] for link in social_links})

        sharing_buttons = [
            {"platform": btn.platform, "selector": btn.selector, "url": btn.url, "text": btn.text}
            for btn in extracted.sharing_buttons
        ]
        share_platforms = list({btn["platform"] for btn in sharing_buttons})

        return {
            "open_graph": {
                "present": bool(extracted.open_graph.tags),
                "tags_count": len(extracted.open_graph.tags),
                "tags": extracted.open_graph.tags,
            },
            "twitter_cards": {
                "present": bool(extracted.twitter.tags),
                "tags_count": len(extracted.twitter.tags),
                "tags": extracted.twitter.tags,
            },
            "social_links": {
                "count": len(social_links),
                "platforms": platforms,
                "links": social_links,
            },
            "sharing_buttons": {
                "count": len(sharing_buttons),
                "platforms": share_platforms,
                "buttons": sharing_buttons,
            },
        }


__all__ = ["SocialParser"]