"""HTML Parser - Extracts basic HTML elements and metadata."""
from typing import Dict, Any
from bs4 import BeautifulSoup


class HTMLParser:
    """Extracts basic HTML structure and metadata."""
    
    @staticmethod
    def parse(html: str, url: str = "") -> Dict[str, Any]:
        """Parse HTML and extract basic elements."""
        if not html:
            return {
                "title": "", "meta_description": "", "canonical": "",
                "language": "", "charset": "", "viewport": "",
                "robots_meta": "", "doctype": "", "html_size": 0
            }
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            title = ""
            title_tag = soup.find('title')
            if title_tag and title_tag.string:
                title = title_tag.string.strip()
            
            meta_description = ""
            meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
            if meta_desc_tag:
                meta_description = meta_desc_tag.get('content', '').strip()
            
            canonical = ""
            canonical_tag = soup.find('link', attrs={'rel': 'canonical'})
            if canonical_tag:
                canonical = canonical_tag.get('href', '').strip()
            
            language = ""
            html_tag = soup.find('html')
            if html_tag:
                language = html_tag.get('lang', '').strip()
            
            charset = ""
            charset_meta = soup.find('meta', attrs={'charset': True})
            if charset_meta:
                charset = charset_meta.get('charset', '').strip()
            
            viewport = ""
            viewport_meta = soup.find('meta', attrs={'name': 'viewport'})
            if viewport_meta:
                viewport = viewport_meta.get('content', '').strip()
            
            robots_meta = ""
            robots_tag = soup.find('meta', attrs={'name': 'robots'})
            if robots_tag:
                robots_meta = robots_tag.get('content', '').strip()
            
            doctype = ""
            if html.strip().upper().startswith('<!DOCTYPE'):
                doctype_end = html.find('>', 10)
                if doctype_end != -1:
                    doctype = html[10:doctype_end].strip()
            
            html_size = len(html.encode('utf-8'))
            
            return {
                "title": title,
                "meta_description": meta_description,
                "canonical": canonical,
                "language": language,
                "charset": charset,
                "viewport": viewport,
                "robots_meta": robots_meta,
                "doctype": doctype,
                "html_size": html_size
            }
            
        except Exception as e:
            return {
                "title": "", "meta_description": "", "canonical": "",
                "language": "", "charset": "", "viewport": "",
                "robots_meta": "", "doctype": "", "html_size": 0,
                "error": str(e)
            }
