"""SEO Parser - Extracts core SEO elements like title, meta tags, and keywords."""
from typing import Dict, Any, List
from bs4 import BeautifulSoup


class SEOParser:
    """Extracts core SEO elements from HTML."""
    
    @staticmethod
    def get_title(soup: BeautifulSoup) -> str:
        """
        Extract page title.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Page title string
        """
        title_tag = soup.find('title')
        return title_tag.string.strip() if title_tag and title_tag.string else ""
    
    @staticmethod
    def get_title_length(soup: BeautifulSoup) -> int:
        """
        Get title character count.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Title length in characters
        """
        return len(SEOParser.get_title(soup))
    
    @staticmethod
    def get_meta_description(soup: BeautifulSoup) -> str:
        """
        Extract meta description.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Meta description content
        """
        meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
        return meta_desc_tag.get('content', '').strip() if meta_desc_tag else ""
    
    @staticmethod
    def get_meta_description_length(soup: BeautifulSoup) -> int:
        """
        Get meta description character count.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Meta description length
        """
        return len(SEOParser.get_meta_description(soup))
    
    @staticmethod
    def get_meta_keywords(soup: BeautifulSoup) -> List[str]:
        """
        Extract meta keywords.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            List of keywords
        """
        meta_keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
        if meta_keywords_tag:
            content = meta_keywords_tag.get('content', '')
            return [kw.strip() for kw in content.split(',') if kw.strip()]
        return []
    
    @staticmethod
    def get_author(soup: BeautifulSoup) -> str:
        """
        Extract author meta tag.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Author name
        """
        author_tag = soup.find('meta', attrs={'name': 'author'})
        return author_tag.get('content', '').strip() if author_tag else ""
    
    @staticmethod
    def get_canonical(soup: BeautifulSoup) -> str:
        """
        Extract canonical URL.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Canonical URL
        """
        canonical_tag = soup.find('link', attrs={'rel': 'canonical'})
        return canonical_tag.get('href', '').strip() if canonical_tag else ""
    
    @staticmethod
    def get_robots_meta(soup: BeautifulSoup) -> str:
        """
        Extract robots meta directive.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Robots meta content
        """
        robots_tag = soup.find('meta', attrs={'name': 'robots'})
        return robots_tag.get('content', '').strip() if robots_tag else ""
    
    @staticmethod
    def get_url_structure(url: str) -> Dict[str, Any]:
        """
        Analyze URL structure.
        
        Args:
            url: URL to analyze
            
        Returns:
            URL structure analysis
        """
        from urllib.parse import urlparse
        
        if not url:
            return {"valid": False, "issues": ["Empty URL"]}
        
        parsed = urlparse(url)
        issues = []
        
        # Check for common issues
        if '://' not in url:
            issues.append("Missing protocol")
        
        if parsed.path and '//' in parsed.path:
            issues.append("Double slashes in path")
        
        if ' ' in url:
            issues.append("URL contains spaces")
        
        if len(url) > 200:
            issues.append("URL too long (>200 chars)")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "scheme": parsed.scheme,
            "netloc": parsed.netloc,
            "path": parsed.path
        }