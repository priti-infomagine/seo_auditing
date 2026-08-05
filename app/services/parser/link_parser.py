"""Link Parser - Extracts and analyzes internal and external links."""
from typing import Dict, Any, List
from urllib.parse import urlparse
from bs4 import BeautifulSoup


class LinkParser:
    """Extracts and analyzes links."""
    
    @staticmethod
    def get_links(soup: BeautifulSoup, base_url: str = "") -> Dict[str, Any]:
        """
        Extract all links from page.
        
        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving relative links
            
        Returns:
            Dictionary containing link analysis
        """
        internal_links = []
        external_links = []
        
        # Find all anchor tags with href
        for tag in soup.find_all('a', href=True):
            href = tag.get('href', '').strip()
            if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue
            
            link_data = {
                "url": href,
                "text": tag.get_text(strip=True),
                "title": tag.get('title', ''),
                "rel": tag.get('rel', [])
            }
            
            # Classify as internal or external
            if LinkParser._is_internal_link(href, base_url):
                link_data["type"] = "internal"
                internal_links.append(link_data)
            else:
                link_data["type"] = "external"
                external_links.append(link_data)
        
        # Get external domains
        external_domains = LinkParser._extract_domains(external_links)
        
        return {
            "internal_count": len(internal_links),
            "external_count": len(external_links),
            "internal_links": internal_links,
            "external_links": external_links,
            "external_domains": external_domains
        }
    
    @staticmethod
    def _is_internal_link(url: str, base_url: str) -> bool:
        """
        Determine if a link is internal.
        
        Args:
            url: Link URL
            base_url: Base URL of the page
            
        Returns:
            True if internal, False if external
        """
        if not url:
            return True
        
        # Relative URLs are internal
        if url.startswith('/') or not urlparse(url).netloc:
            return True
        
        # Check against base URL
        if base_url:
            base_domain = urlparse(base_url).netloc
            link_domain = urlparse(url).netloc
            
            # Remove www. for comparison
            base_domain = base_domain.replace('www.', '')
            link_domain = link_domain.replace('www.', '')
            
            return base_domain == link_domain
        
        return False
    
    @staticmethod
    def _extract_domains(external_links: List[Dict[str, Any]]) -> List[str]:
        """
        Extract unique domains from external links.
        
        Args:
            external_links: List of external link dictionaries
            
        Returns:
            List of unique domain names
        """
        domains = []
        
        for link in external_links:
            url = link.get('url', '')
            if url:
                netloc = urlparse(url).netloc
                if netloc:
                    # Remove www. and port numbers
                    domain = netloc.replace('www.', '').split(':')[0]
                    if domain not in domains:
                        domains.append(domain)
        
        return domains
    
    @staticmethod
    def get_internal_link_count(soup: BeautifulSoup, base_url: str = "") -> int:
        """
        Get count of internal links.
        
        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving links
            
        Returns:
            Number of internal links
        """
        links = LinkParser.get_links(soup, base_url)
        return links.get('internal_count', 0)
    
    @staticmethod
    def get_external_link_count(soup: BeautifulSoup, base_url: str = "") -> int:
        """
        Get count of external links.
        
        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving links
            
        Returns:
            Number of external links
        """
        links = LinkParser.get_links(soup, base_url)
        return links.get('external_count', 0)