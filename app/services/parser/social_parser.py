"""Social Parser - Extracts social media tags and links."""
from typing import Dict, Any, List
from bs4 import BeautifulSoup
import re


class SocialParser:
    """Extracts social media metadata and links."""
    
    # Common social media domains
    SOCIAL_DOMAINS = {
        'facebook': ['facebook.com', 'fb.com'],
        'twitter': ['twitter.com', 'x.com'],
        'linkedin': ['linkedin.com'],
        'instagram': ['instagram.com'],
        'youtube': ['youtube.com', 'youtu.be'],
        'pinterest': ['pinterest.com', 'pin.it'],
        'tiktok': ['tiktok.com'],
        'snapchat': ['snapchat.com'],
        'whatsapp': ['whatsapp.com', 'wa.me'],
        'telegram': ['t.me', 'telegram.me'],
        'reddit': ['reddit.com'],
        'tumblr': ['tumblr.com'],
        'github': ['github.com'],
        'medium': ['medium.com']
    }
    
    @staticmethod
    def get_open_graph(soup: BeautifulSoup) -> Dict[str, str]:
        """
        Extract Open Graph meta tags.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Dictionary of OG tags
        """
        og_tags = {}
        
        # Find all OG meta tags
        og_meta_tags = soup.find_all('meta', attrs={'property': re.compile('^og:', re.IGNORECASE)})
        for tag in og_meta_tags:
            property_name = tag.get('property', '')
            content = tag.get('content', '')
            if property_name and content:
                # Remove 'og:' prefix and convert to lowercase
                key = property_name.replace('og:', '').lower()
                og_tags[key] = content
        
        return og_tags
    
    @staticmethod
    def get_twitter_cards(soup: BeautifulSoup) -> Dict[str, str]:
        """
        Extract Twitter Card meta tags.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Dictionary of Twitter Card tags
        """
        twitter_tags = {}
        
        # Find all Twitter meta tags
        twitter_meta_tags = soup.find_all('meta', attrs={'name': re.compile('^twitter:', re.IGNORECASE)})
        for tag in twitter_meta_tags:
            name = tag.get('name', '')
            content = tag.get('content', '')
            if name and content:
                # Remove 'twitter:' prefix and convert to lowercase
                key = name.replace('twitter:', '').lower()
                twitter_tags[key] = content
        
        return twitter_tags
    
    @staticmethod
    def extract_social_links(soup: BeautifulSoup, base_url: str = "") -> List[Dict[str, str]]:
        """
        Extract social media links from page.
        
        Args:
            soup: BeautifulSoup object
            base_url: Base URL of the page
            
        Returns:
            List of social media links found
        """
        social_links = []
        found_domains = set()
        
        # Check all anchor tags
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '').strip()
            
            if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue
            
            # Check if link contains social media domain
            for platform, domains in SocialParser.SOCIAL_DOMAINS.items():
                if any(domain in href.lower() for domain in domains):
                    if platform not in found_domains:
                        social_links.append({
                            "platform": platform,
                            "url": href,
                            "text": a_tag.get_text(strip=True)
                        })
                        found_domains.add(platform)
                        break
        
        return social_links
    
    @staticmethod
    def has_social_tags(soup: BeautifulSoup) -> bool:
        """
        Check if page has social media tags.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            True if social tags found
        """
        og_tags = SocialParser.get_open_graph(soup)
        twitter_tags = SocialParser.get_twitter_cards(soup)
        social_links = SocialParser.extract_social_links(soup)
        
        return bool(og_tags or twitter_tags or social_links)
    
    @staticmethod
    def get_social_summary(soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Get comprehensive social media analysis.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Social media summary
        """
        og_tags = SocialParser.get_open_graph(soup)
        twitter_tags = SocialParser.get_twitter_cards(soup)
        social_links = SocialParser.extract_social_links(soup)
        
        return {
            "open_graph": {
                "present": bool(og_tags),
                "tags_count": len(og_tags),
                "tags": og_tags
            },
            "twitter_cards": {
                "present": bool(twitter_tags),
                "tags_count": len(twitter_tags),
                "tags": twitter_tags
            },
            "social_links": {
                "count": len(social_links),
                "platforms": [link['platform'] for link in social_links],
                "links": social_links
            }
        }