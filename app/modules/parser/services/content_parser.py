"""Content Parser - Extracts and analyzes page content."""
from typing import Dict, Any, List
import re
from bs4 import BeautifulSoup


class ContentParser:
    """Analyzes page content and text."""
    
    @staticmethod
    def get_word_count(soup: BeautifulSoup) -> int:
        """
        Count words in page content.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Word count
        """
        # Get text from main content areas
        text = ContentParser._extract_main_text(soup)
        if not text:
            return 0
        
        # Split on whitespace and filter empty strings
        words = re.findall(r'\b\w+\b', text)
        return len(words)
    
    @staticmethod
    def get_reading_time(soup: BeautifulSoup) -> int:
        """
        Estimate reading time in minutes.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Reading time in minutes
        """
        word_count = ContentParser.get_word_count(soup)
        # Average reading speed: 200-250 words per minute
        return max(1, round(word_count / 200))
    
    @staticmethod
    def get_paragraph_count(soup: BeautifulSoup) -> int:
        """
        Count paragraphs.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Number of paragraphs
        """
        paragraphs = soup.find_all('p')
        return len(paragraphs)
    
    @staticmethod
    def get_text_html_ratio(html: str, soup: BeautifulSoup) -> float:
        """
        Calculate text-to-HTML ratio.
        
        Args:
            html: Raw HTML string
            soup: BeautifulSoup object
            
        Returns:
            Ratio of text content to HTML size
        """
        if not html:
            return 0.0
        
        text = ContentParser._extract_main_text(soup)
        text_length = len(text)
        html_length = len(html)
        
        if html_length == 0:
            return 0.0
        
        ratio = text_length / html_length
        return round(ratio, 3)
    
    @staticmethod
    def get_content_hash(soup: BeautifulSoup) -> str:
        """
        Generate hash of main content for duplicate detection.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            MD5 hash of content
        """
        import hashlib
        
        text = ContentParser._extract_main_text(soup)
        if not text:
            return ""
        
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    @staticmethod
    def _extract_main_text(soup: BeautifulSoup) -> str:
        """
        Extract main text content from HTML.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Extracted text content
        """
        # Remove script and style elements
        for script in soup(['script', 'style', 'nav', 'header', 'footer']):
            script.decompose()
        
        # Get text from main content areas
        main_content = soup.find('main') or soup.find('article') or soup.find('body')
        
        if main_content:
            text = main_content.get_text(separator=' ', strip=True)
        else:
            text = soup.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()