"""Parser Service - Orchestrates all parsers and provides unified interface."""
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from bs4 import BeautifulSoup

from .html_parser import HTMLParser
from .seo_parser import SEOParser
from .content_parser import ContentParser
from .heading_parser import HeadingParser
from .link_parser import LinkParser
from .image_parser import ImageParser
from .schema_parser import SchemaParser
from .social_parser import SocialParser
from .technical_parser import TechnicalParser
from .geo_parser import GeoParser


class ParserService:
    """
    Orchestrates all parsers and provides unified interface for parsing crawled data.
    
    This service coordinates multiple specialized parsers to extract comprehensive
    SEO and content information from HTML pages.
    """
    
    def __init__(self, crawl_dir: str = "crawl_data"):
        """
        Initialize parser service.
        
        Args:
            crawl_dir: Base directory containing crawl data
        """
        self.crawl_dir = Path(crawl_dir)
    
    def parse_html(self, html: str, url: str = "", crawler_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Parse HTML content and extract all SEO-relevant data.
        
        Args:
            html: Raw HTML content
            url: URL of the page
            crawler_data: Optional dictionary from crawler response
            
        Returns:
            Dictionary containing all parsed data
        """
        if not html:
            return {}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Initialize with crawler data if provided
        if not crawler_data:
            crawler_data = {}
        
        # Extract HTTP data from crawler
        http_data = crawler_data.get('http', {
            "status_code": 200,
            "headers": {},
            "response_time": 0,
            "redirects": []
        })
        
        headers = http_data.get("headers", {})
        
        # Parse all sections using specialized parsers
        data = {
            "basic": self._parse_basic(soup, html, url),
            "http": TechnicalParser.parse_http_headers(headers),
            "url": {
                "url_structure": SEOParser.get_url_structure(url),
                "https": url.startswith("https"),
            },
            "seo": {
                "canonical_url": SEOParser.get_canonical(soup),
                "robots_meta": SEOParser.get_robots_meta(soup),
                "x_robots_tag": headers.get("X-Robots-Tag", ""),
            },
            "headings": {
                "headings": HeadingParser.get_headings(soup),
                "heading_stats": HeadingParser.get_heading_stats(soup),
            },
            "content": {
                "word_count": ContentParser.get_word_count(soup),
                "reading_time": ContentParser.get_reading_time(soup),
                "paragraph_count": ContentParser.get_paragraph_count(soup),
                "text_html_ratio": ContentParser.get_text_html_ratio(html, soup),
                "content_hash": ContentParser.get_content_hash(soup),
            },
            "links": LinkParser.get_links(soup, url),
            "images": ImageParser.get_images(soup, url),
            "media": self._parse_media(soup),
            "social": SocialParser.get_social_summary(soup),
            "structured_data": {
                "schema_markup": SchemaParser.get_schema_markup(soup),
            },
            "local_seo": {
                "address": GeoParser.extract_address_info(soup),
                "phone_numbers": GeoParser.extract_phone_numbers(soup),
                "business_hours": GeoParser.extract_business_hours(soup),
                "geo_meta_tags": GeoParser.extract_geo_meta_tags(soup),
                "location_keywords": GeoParser.extract_location_keywords(soup),
                "google_business": GeoParser.check_google_my_business(soup),
                "nap_consistency": GeoParser.check_nap_consistency(soup),
            },
        }
        
        return data
    
    def _parse_basic(self, soup: BeautifulSoup, html: str, url: str) -> Dict[str, Any]:
        """
        Parse basic HTML elements.
        
        Args:
            soup: BeautifulSoup object
            html: Raw HTML string
            url: Page URL
            
        Returns:
            Basic page information
        """
        return {
            "title": SEOParser.get_title(soup),
            "title_length": SEOParser.get_title_length(soup),
            "meta_description": SEOParser.get_meta_description(soup),
            "meta_description_length": SEOParser.get_meta_description_length(soup),
            "meta_keywords": SEOParser.get_meta_keywords(soup),
            "author": SEOParser.get_author(soup),
            "language": TechnicalParser.get_html_language(soup),
            "charset": TechnicalParser.get_charset(soup),
            "viewport": TechnicalParser.get_viewport(soup),
            "doctype": TechnicalParser.get_doctype(html),
        }
    
    def _parse_media(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Parse media elements.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Media information
        """
        return {
            "videos": len(soup.find_all('video')),
            "iframes": len(soup.find_all('iframe')),
            "tables": len(soup.find_all('table')),
            "lists": len(soup.find_all(['ul', 'ol'])),
            "forms": len(soup.find_all('form')),
            "buttons": len(soup.find_all('button')),
        }
    
    def load_crawl_file(self, filepath: str) -> Dict[str, Any]:
        """
        Load a single crawl data file.
        
        Args:
            filepath: Path to crawl data JSON file
            
        Returns:
            Crawl data dictionary
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_latest_crawl_by_domain(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent crawl for a domain.
        
        Args:
            domain: Domain name (e.g., 'cyfuture.com')
            
        Returns:
            Latest crawl data or None
        """
        domain_dir = self.crawl_dir / domain
        
        if not domain_dir.exists():
            return None
        
        # Get all JSON files in domain directory
        files = sorted(domain_dir.glob("*.json"), reverse=True)
        
        if not files:
            return None
        
        return self.load_crawl_file(str(files[0]))
    
    def get_latest_crawl(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent crawl for a URL.
        
        Args:
            url: URL to search for
            
        Returns:
            Latest crawl data or None
        """
        from urllib.parse import urlparse
        import hashlib
        
        domain = urlparse(url).netloc.replace(':', '_')
        url_hash = hashlib.md5(url.encode()).hexdigest()
        domain_dir = self.crawl_dir / domain
        
        if not domain_dir.exists():
            return None
        
        pattern = f"{url_hash}_*.json"
        files = sorted(domain_dir.glob(pattern), reverse=True)
        
        if not files:
            return None
        
        return self.load_crawl_file(str(files[0]))
    
    def analyze_seo_score(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate comprehensive SEO score and identify issues.
        
        Args:
            data: Crawled data dictionary
            
        Returns:
            SEO analysis results
        """
        page_data = data.get('data', {})
        
        # Initialize scores
        onpage_score = 100
        offpage_score = 100
        technical_score = 100
        geo_score = 100
        local_score = 100
        
        onpage_issues = []
        onpage_warnings = []
        onpage_passed = []
        
        offpage_issues = []
        offpage_warnings = []
        offpage_passed = []
        
        technical_issues = []
        technical_warnings = []
        technical_passed = []
        
        geo_issues = []
        geo_warnings = []
        geo_passed = []
        
        # ========================
        # ON-PAGE SEO CHECKS
        # ========================
        
        basic_data = page_data.get('basic', {})
        title = basic_data.get('title') or page_data.get('title')
        title_length = basic_data.get('title_length') or page_data.get('title_length', 0)
        
        if not title:
            onpage_score -= 10
            onpage_issues.append("Missing page title")
        else:
            if 30 <= title_length <= 60:
                onpage_passed.append("Title length is optimal (30-60 characters)")
            elif title_length < 30:
                onpage_warnings.append(f"Title too short ({title_length} chars, recommended: 30-60)")
                onpage_score -= 3
            else:
                onpage_warnings.append(f"Title too long ({title_length} chars, recommended: 30-60)")
                onpage_score -= 3
        
        meta_desc = basic_data.get('meta_description') or page_data.get('meta_description')
        meta_desc_length = basic_data.get('meta_description_length') or page_data.get('meta_description_length', 0)
        
        if not meta_desc:
            onpage_score -= 10
            onpage_issues.append("Missing meta description")
        else:
            if 150 <= meta_desc_length <= 160:
                onpage_passed.append("Meta description length is optimal (150-160 characters)")
            elif meta_desc_length < 150:
                onpage_warnings.append(f"Meta description too short ({meta_desc_length} chars)")
                onpage_score -= 3
            else:
                onpage_warnings.append(f"Meta description too long ({meta_desc_length} chars)")
                onpage_score -= 3
        
        headings = page_data.get('headings', {})
        headings_data = headings.get('headings', headings)
        h1_tags = headings_data.get('h1', [])
        
        if len(h1_tags) == 0:
            onpage_issues.append("Missing H1 tag")
            onpage_score -= 10
        elif len(h1_tags) == 1:
            onpage_passed.append("Has exactly one H1 tag")
        else:
            onpage_warnings.append(f"Multiple H1 tags found ({len(h1_tags)})")
            onpage_score -= 5
        
        images = page_data.get('images', {})
        total_images = images.get('total_count', 0)
        images_without_alt = images.get('without_alt', 0)
        
        if total_images > 0:
            if images_without_alt == 0:
                onpage_passed.append("All images have alt text")
            else:
                onpage_warnings.append(f"{images_without_alt} images missing alt text")
                onpage_score -= min(images_without_alt * 2, 10)
        
        content_data = page_data.get('content', {})
        word_count = content_data.get('word_count') or page_data.get('word_count', 0)
        if word_count < 300:
            onpage_warnings.append(f"Thin content: only {word_count} words (recommended: 300+)")
            onpage_score -= 10
        else:
            onpage_passed.append(f"Good content length: {word_count} words")
        
        url_data = page_data.get('url', {})
        url_structure = url_data.get('url_structure') or page_data.get('url_structure', {})
        if isinstance(url_structure, dict) and not url_structure.get('valid', True):
            for issue in url_structure.get('issues', []):
                onpage_warnings.append(f"URL: {issue}")
                onpage_score -= 3
        
        links_data = page_data.get('links', {})
        internal_links = links_data.get('internal_count') or page_data.get('internal_links_count', 0)
        if internal_links == 0:
            onpage_warnings.append("No internal links found")
            onpage_score -= 5
        else:
            onpage_passed.append(f"Has {internal_links} internal links")
        
        images_data = page_data.get('images', {})
        lazy_loading = images_data.get('lazy_loading') if 'lazy_loading' in images_data else page_data.get('lazy_loading', False)
        if lazy_loading:
            onpage_passed.append("Lazy loading implemented")
        else:
            onpage_warnings.append("Lazy loading not detected")
        
        # ========================
        # TECHNICAL SEO CHECKS
        # ========================
        
        http_data = page_data.get('http', {})
        ssl_cert = page_data.get('ssl') or page_data.get('ssl_certificate', False)
        if ssl_cert or (http_data.get('status_code') == 200 and 'https' in str(http_data.get('redirects', []))):
            technical_passed.append("SSL certificate present (HTTPS)")
        else:
            technical_issues.append("No SSL certificate (not using HTTPS)")
            technical_score -= 15
        
        viewport = basic_data.get('viewport') or page_data.get('viewport')
        if viewport:
            technical_passed.append("Mobile-friendly (viewport meta tag present)")
        else:
            technical_issues.append("Missing viewport meta tag (not mobile-friendly)")
            technical_score -= 10
        
        seo_data = page_data.get('seo', {})
        canonical = seo_data.get('canonical_url') or page_data.get('canonical_url')
        has_canonical = canonical is not None
        if has_canonical:
            technical_passed.append("Has canonical URL")
        else:
            technical_warnings.append("Missing canonical URL")
            technical_score -= 5
        
        language = basic_data.get('language') or page_data.get('language')
        if language:
            technical_passed.append(f"Language declared: {language}")
        else:
            technical_warnings.append("Language not specified")
        
        social_data = page_data.get('social', {})
        open_graph = social_data.get('open_graph') or page_data.get('open_graph', {})
        if open_graph:
            technical_passed.append(f"Open Graph tags present ({len(open_graph)} tags)")
        else:
            technical_warnings.append("No Open Graph tags found")
        
        structured_data = page_data.get('structured_data', {})
        schema = structured_data.get('schema_markup') or page_data.get('schema_markup', [])
        if schema:
            technical_passed.append(f"Schema markup found ({len(schema)} items)")
        else:
            technical_warnings.append("No structured data/schema markup")
        
        performance_data = page_data.get('performance', {})
        html_size = performance_data.get('html_size') or page_data.get('html_size', 0)
        if html_size > 0:
            if html_size < 100000:
                technical_passed.append(f"Good HTML size: {html_size/1024:.1f}KB")
            else:
                technical_warnings.append(f"Large HTML size: {html_size/1024:.1f}KB")
                technical_score -= 3
        
        content_data = page_data.get('content', {})
        text_html_ratio = content_data.get('text_html_ratio') or page_data.get('text_html_ratio', 0)
        if text_html_ratio < 0.1:
            technical_warnings.append("Low text-to-HTML ratio")
            technical_score -= 3
        
        minification = page_data.get('minified_css_js', {})
        if minification.get('likely_minified', False):
            technical_passed.append("HTML appears to be minified")
        
        # ========================
        # OFF-PAGE SEO CHECKS
        # ========================
        
        social_links = page_data.get('social_media_links', [])
        if social_links:
            offpage_passed.append(f"Social media links found ({len(social_links)})")
        else:
            offpage_warnings.append("No social media links detected")
        
        external_domains = page_data.get('external_domains', [])
        if external_domains:
            offpage_passed.append(f"Links to {len(external_domains)} external domains")
        
        backlink_indicators = page_data.get('backlink_indicators', {})
        total_external = backlink_indicators.get('total_external_links', 0)
        if total_external > 0:
            offpage_passed.append(f"Has {total_external} external links")
        
        # ========================
        # GEO/LOCAL SEO CHECKS
        # ========================
        
        address_info = page_data.get('address_info', {})
        if address_info.get('found', False):
            geo_passed.append("Address information found")
            local_score += 5
        else:
            geo_warnings.append("No address information found")
        
        phone_numbers = page_data.get('phone_numbers', [])
        if phone_numbers:
            geo_passed.append(f"Phone numbers found ({len(phone_numbers)})")
            local_score += 5
        else:
            geo_warnings.append("No phone numbers found")
        
        business_hours = page_data.get('business_hours', {})
        if business_hours.get('found', False):
            geo_passed.append("Business hours information found")
            local_score += 5
        else:
            geo_warnings.append("No business hours found")
        
        gmb = page_data.get('google_my_business', {})
        gmb_score = gmb.get('integration_score', 0)
        if gmb_score > 0:
            geo_passed.append(f"Google My Business integration ({gmb_score}/3)")
            local_score += gmb_score * 5
        else:
            geo_warnings.append("No Google My Business integration")
        
        local_schema = page_data.get('local_business_schema', {})
        if local_schema.get('found', False):
            geo_passed.append(f"Local business schema ({local_schema.get('type', '')})")
            local_score += 10
        else:
            geo_warnings.append("No local business schema markup")
        
        geo_meta = page_data.get('geo_meta_tags', {})
        if geo_meta.get('found', False):
            geo_passed.append("Geo meta tags present")
        else:
            geo_warnings.append("No geo meta tags")
        
        location_keywords = page_data.get('location_keywords', [])
        if location_keywords:
            geo_passed.append(f"Location keywords found ({len(location_keywords)})")
        
        nap = page_data.get('nap_consistency', {})
        nap_score = nap.get('consistency_score', 0)
        if nap_score >= 0.7:
            geo_passed.append("Good NAP consistency")
            local_score += 5
        elif nap_score > 0:
            geo_warnings.append("Partial NAP information")
        
        # Calculate final scores
        onpage_score = max(0, onpage_score)
        offpage_score = max(0, offpage_score)
        technical_score = max(0, technical_score)
        geo_score = max(0, geo_score)
        local_score = min(100, max(0, local_score))
        
        # Overall score (weighted average)
        overall_score = int(
            onpage_score * 0.30 +
            technical_score * 0.30 +
            offpage_score * 0.20 +
            geo_score * 0.10 +
            local_score * 0.10
        )
        
        return {
            "overall_score": overall_score,
            "overall_grade": self._get_grade(overall_score),
            "breakdown": {
                "on_page_seo": {
                    "score": onpage_score,
                    "grade": self._get_grade(onpage_score),
                    "issues": onpage_issues,
                    "warnings": onpage_warnings,
                    "passed": onpage_passed
                },
                "technical_seo": {
                    "score": technical_score,
                    "grade": self._get_grade(technical_score),
                    "issues": technical_issues,
                    "warnings": technical_warnings,
                    "passed": technical_passed
                },
                "off_page_seo": {
                    "score": offpage_score,
                    "grade": self._get_grade(offpage_score),
                    "issues": offpage_issues,
                    "warnings": offpage_warnings,
                    "passed": offpage_passed
                },
                "geo_seo": {
                    "score": geo_score,
                    "grade": self._get_grade(geo_score),
                    "issues": geo_issues,
                    "warnings": geo_warnings,
                    "passed": geo_passed
                },
                "local_seo": {
                    "score": local_score,
                    "grade": self._get_grade(local_score),
                    "note": "Local SEO score based on geo signals and local business optimization"
                }
            },
            "reading_time_minutes": page_data.get('reading_time_minutes', 0)
        }
    
    def _get_grade(self, score: int) -> str:
        """Convert score to letter grade."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"
    
    def extract_keywords(self, data: Dict[str, Any], top_n: int = 10) -> List[Dict[str, Any]]:
        """
        Extract potential keywords from page content.
        
        Args:
            data: Crawled data dictionary
            top_n: Number of top keywords to return
            
        Returns:
            List of keywords with frequency
        """
        from collections import Counter
        import re
        
        page_data = data.get('data', {})
        
        # Extract from title
        title = page_data.get('title', '')
        meta_keywords = page_data.get('meta_keywords', [])
        
        # Extract from headings
        headings = page_data.get('headings', {})
        heading_text = []
        for level in ['h1', 'h2', 'h3']:
            heading_text.extend(headings.get(level, []))
        
        # Combine text sources
        all_text = ' '.join([title] + heading_text + [', '.join(meta_keywords)])
        
        # Simple keyword extraction (word frequency)
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
            'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare', 'ought',
            'used', 'it', 'its', 'this', 'that', 'these', 'those', 'i', 'you', 'he',
            'she', 'we', 'they', 'what', 'which', 'who', 'when', 'where', 'why', 'how',
            'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some',
            'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too',
            'very', 'just', 'also', 'now', 'here', 'there', 'then', 'once'
        }
        
        # Extract words
        words = re.findall(r'\b[a-zA-Z]{3,}\b', all_text.lower())
        word_freq = Counter(words)
        
        # Remove stop words
        keywords = [
            {"keyword": word, "frequency": count}
            for word, count in word_freq.most_common(top_n)
            if word not in stop_words and len(word) > 2
        ]
        
        return keywords
    
    def analyze_links(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze link structure.
        
        Args:
            data: Crawled data dictionary
            
        Returns:
            Link analysis results
        """
        page_data = data.get('data', {})
        links = page_data.get('links', {})
        
        internal_count = links.get('internal_count', 0)
        external_count = links.get('external_count', 0)
        internal_links = links.get('internal_links', [])
        external_links = links.get('external_links', [])
        
        # Analyze internal links
        internal_domains = []
        for link in internal_links:
            url = link.get('url', '')
            if url:
                internal_domains.append(url)
        
        # Analyze external links
        external_domains = []
        for link in external_links:
            url = link.get('url', '')
            if url:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                if domain:
                    external_domains.append(domain)
        
        from collections import Counter
        external_domain_counts = Counter(external_domains)
        
        return {
            "total_links": internal_count + external_count,
            "internal_links": internal_count,
            "external_links": external_count,
            "ratio": f"{internal_count}:{external_count}" if external_count > 0 else f"{internal_count}:0",
            "external_domains": dict(external_domain_counts.most_common(10)),
            "sample_internal": internal_links[:5],
            "sample_external": external_links[:5]
        }
    
    def analyze_images(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze image usage.
        
        Args:
            data: Crawled data dictionary
            
        Returns:
            Image analysis results
        """
        page_data = data.get('data', {})
        images = page_data.get('images', {})
        
        total = images.get('total_count', 0)
        without_alt = images.get('without_alt', 0)
        sample = images.get('sample', [])
        
        # Calculate alt text coverage
        alt_coverage = ((total - without_alt) / total * 100) if total > 0 else 0
        
        return {
            "total_images": total,
            "images_with_alt": total - without_alt,
            "images_without_alt": without_alt,
            "alt_text_coverage_percent": round(alt_coverage, 1),
            "status": "Good" if without_alt == 0 else "Needs Improvement",
            "sample_images": sample[:5]
        }
    
    def generate_report_by_domain(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Generate comprehensive SEO report for a domain.
        
        Args:
            domain: Domain name (e.g., 'cyfuture.com')
            
        Returns:
            Complete SEO report
        """
        crawl_data = self.get_latest_crawl_by_domain(domain)
        
        if not crawl_data:
            print(f"No crawl data found for domain: {domain}")
            return None
        
        # Parse the HTML from crawl data
        html = crawl_data.get('html', '')
        url = crawl_data.get('url', '')
        
        parsed_data = self.parse_html(html, url, crawl_data)
        crawl_data['data'] = parsed_data
        
        page_data = parsed_data
        
        # Generate all analyses
        seo_analysis = self.analyze_seo_score(crawl_data)
        keywords = self.extract_keywords(crawl_data)
        link_analysis = self.analyze_links(crawl_data)
        image_analysis = self.analyze_images(crawl_data)
        
        # Compile report
        report = {
            "url": url,
            "crawled_at": crawl_data.get('crawled_at'),
            "domain": crawl_data.get('domain'),
            "seo_score": seo_analysis,
            "keywords": keywords,
            "links": link_analysis,
            "images": image_analysis,
            "basic_info": {
                "title": page_data.get('basic', {}).get('title'),
                "meta_description": page_data.get('basic', {}).get('meta_description'),
                "word_count": page_data.get('content', {}).get('word_count'),
                "reading_time_minutes": page_data.get('content', {}).get('reading_time'),
                "language": page_data.get('basic', {}).get('language'),
                "doctype": page_data.get('basic', {}).get('doctype')
            },
            "technical": {
                "html_size_bytes": page_data.get('technical', {}).get('html_size_bytes', 0),
                "text_html_ratio": page_data.get('content', {}).get('text_html_ratio'),
                "viewport": page_data.get('basic', {}).get('viewport'),
                "charset": page_data.get('basic', {}).get('charset'),
                "canonical_url": page_data.get('seo', {}).get('canonical_url'),
                "robots_meta": page_data.get('seo', {}).get('robots_meta'),
                "ssl_certificate": page_data.get('url', {}).get('https', False),
                "mobile_friendly": bool(page_data.get('basic', {}).get('viewport'))
            },
            "social": {
                "open_graph_tags": len(page_data.get('social', {}).get('open_graph', {})),
                "twitter_cards": len(page_data.get('social', {}).get('twitter_cards', {})),
                "schema_markup_count": len(page_data.get('structured_data', {}).get('schema_markup', []))
            },
            "geo_local": {
                "address_info": page_data.get('local_seo', {}).get('address', {}),
                "phone_numbers": page_data.get('local_seo', {}).get('phone_numbers', []),
                "business_hours": page_data.get('local_seo', {}).get('business_hours', {}),
                "google_my_business": page_data.get('local_seo', {}).get('google_business', {}),
                "local_business_schema": page_data.get('local_seo', {}).get('local_business_schema', {}),
                "social_media_links": page_data.get('social', {}).get('social_links', {}).get('links', [])
            }
        }
        
        return report
    
    def generate_report(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Generate comprehensive SEO report for a URL.
        
        Args:
            url: URL to analyze
            
        Returns:
            Complete SEO report
        """
        crawl_data = self.get_latest_crawl(url)
        
        if not crawl_data:
            print(f"No crawl data found for: {url}")
            return None
        
        # Parse the HTML from crawl data
        html = crawl_data.get('html', '')
        
        parsed_data = self.parse_html(html, url, crawl_data)
        crawl_data['data'] = parsed_data
        
        page_data = parsed_data
        
        # Generate all analyses
        seo_analysis = self.analyze_seo_score(crawl_data)
        keywords = self.extract_keywords(crawl_data)
        link_analysis = self.analyze_links(crawl_data)
        image_analysis = self.analyze_images(crawl_data)
        
        # Compile report
        report = {
            "url": url,
            "crawled_at": crawl_data.get('crawled_at'),
            "domain": crawl_data.get('domain'),
            "seo_score": seo_analysis,
            "keywords": keywords,
            "links": link_analysis,
            "images": image_analysis,
            "basic_info": {
                "title": page_data.get('basic', {}).get('title'),
                "meta_description": page_data.get('basic', {}).get('meta_description'),
                "word_count": page_data.get('content', {}).get('word_count'),
                "reading_time_minutes": page_data.get('content', {}).get('reading_time'),
                "language": page_data.get('basic', {}).get('language'),
                "doctype": page_data.get('basic', {}).get('doctype')
            },
            "technical": {
                "html_size_bytes": page_data.get('content', {}).get('text_html_ratio', 0),
                "text_html_ratio": page_data.get('content', {}).get('text_html_ratio'),
                "viewport": page_data.get('basic', {}).get('viewport'),
                "charset": page_data.get('basic', {}).get('charset'),
                "canonical_url": page_data.get('seo', {}).get('canonical_url'),
                "robots_meta": page_data.get('seo', {}).get('robots_meta'),
                "ssl_certificate": False,
                "mobile_friendly": bool(page_data.get('basic', {}).get('viewport'))
            },
            "social": {
                "open_graph_tags": len(page_data.get('social', {}).get('open_graph', {}).get('tags', {})),
                "twitter_cards": len(page_data.get('social', {}).get('twitter_cards', {}).get('tags', {})),
                "schema_markup_count": len(page_data.get('structured_data', {}).get('schema_markup', []))
            },
            "geo_local": {
                "address_info": page_data.get('local_seo', {}).get('address', {}),
                "phone_numbers": page_data.get('local_seo', {}).get('phone_numbers', []),
                "business_hours": page_data.get('local_seo', {}).get('business_hours', {}),
                "google_my_business": page_data.get('local_seo', {}).get('google_business', {}),
                "local_business_schema": {},
                "social_media_links": page_data.get('social', {}).get('social_links', {}).get('links', [])
            }
        }
        
        return report
    
    def save_parsed_data(self, report: Dict[str, Any], domain: str) -> Path:
        """
        Save parsed SEO report to JSON file with incremental test number.
        
        Args:
            report: Report dictionary to save
            domain: Domain name for organizing files
            
        Returns:
            Path to saved file
        """
        from datetime import datetime
        
        # Create parsed_data directory with domain subdirectory
        parsed_dir = Path("parsed_data") / domain
        parsed_dir.mkdir(parents=True, exist_ok=True)
        
        # Find next test number
        existing_files = list(parsed_dir.glob(f"{domain}_test_*.json"))
        if existing_files:
            test_numbers = []
            for f in existing_files:
                try:
                    filename = f.stem
                    test_part = filename.split('_test_')[1]
                    test_num = int(test_part.split('_')[0])
                    test_numbers.append(test_num)
                except (IndexError, ValueError):
                    continue
            next_test = max(test_numbers, default=0) + 1
        else:
            next_test = 1
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{domain}_test_{next_test}_{timestamp}.json"
        filepath = parsed_dir / filename
        
        # Save to file
        with open(filepath, 'w', encoding='utf-8') as f:
            import json
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def print_report(self, report: Dict[str, Any]) -> None:
        """
        Print formatted SEO report to console.
        
        Args:
            report: Report dictionary from generate_report()
        """
        if not report:
            return
        
        print("\n" + "="*60)
        print("COMPREHENSIVE SEO ANALYSIS REPORT")
        print("="*60)
        print(f"URL: {report['url']}")
        print(f"Crawled: {report['crawled_at']}")
        print(f"Domain: {report['domain']}")
        
        # SEO Score Breakdown
        seo = report.get('seo_score', {})
        if seo:
            print("\n" + "="*60)
            print("OVERALL SEO SCORE")
            print("="*60)
            print(f"Score: {seo.get('overall_score', 0)}/100 (Grade: {seo.get('overall_grade', 'N/A')})")
            print(f"Reading Time: {seo.get('reading_time_minutes', 0)} minute(s)")
            
            breakdown = seo.get('breakdown', {})
            
            for category, data in breakdown.items():
                if category == 'local_seo':
                    print("\n" + "-"*60)
                    print(f"LOCAL SEO: {data.get('score', 0)}/100 (Grade: {data.get('grade', 'N/A')})")
                    if data.get('note'):
                        print(f"  Note: {data['note']}")
                    continue
                
                score = data.get('score', 0)
                grade = data.get('grade', 'N/A')
                issues = data.get('issues', [])
                warnings = data.get('warnings', [])
                passed = data.get('passed', [])
                
                print("\n" + "-"*60)
                print(f"{category.upper().replace('_', ' ')}: {score}/100 (Grade: {grade})")
                
                if issues:
                    print(f"\n  ❌ CRITICAL ISSUES ({len(issues)}):")
                    for issue in issues[:5]:
                        print(f"    • {issue}")
                
                if warnings:
                    print(f"\n  ⚠️  WARNINGS ({len(warnings)}):")
                    for warning in warnings[:5]:
                        print(f"    • {warning}")
                
                if passed:
                    print(f"\n  ✅ PASSED CHECKS ({len(passed)}):")
                    for check in passed[:5]:
                        print(f"    • {check}")
        
        # Keywords
        keywords = report.get('keywords', [])
        if keywords:
            print("\n" + "="*60)
            print("TOP KEYWORDS")
            print("="*60)
            for kw in keywords[:10]:
                print(f"  • {kw['keyword']} (frequency: {kw['frequency']})")
        
        # Links
        links = report.get('links', {})
        if links:
            print("\n" + "="*60)
            print("LINK ANALYSIS")
            print("="*60)
            print(f"  Total Links: {links.get('total_links', 0)}")
            print(f"  Internal: {links.get('internal_links', 0)}")
            print(f"  External: {links.get('external_links', 0)}")
            print(f"  Ratio: {links.get('ratio', 'N/A')}")
            
            ext_domains = links.get('external_domains', {})
            if ext_domains:
                print(f"\n  Top External Domains:")
                for domain, count in list(ext_domains.items())[:5]:
                    print(f"    • {domain} ({count} links)")
        
        # Images
        images = report.get('images', {})
        if images:
            print("\n" + "="*60)
            print("IMAGE ANALYSIS")
            print("="*60)
            print(f"  Total Images: {images.get('total_images', 0)}")
            print(f"  Images with Alt Text: {images.get('images_with_alt', 0)}")
            print(f"  Images without Alt Text: {images.get('images_without_alt', 0)}")
            print(f"  Alt Text Coverage: {images.get('alt_text_coverage_percent', 0)}%")
            print(f"  Status: {images.get('status', 'N/A')}")
        
        # Technical Details
        print("\n" + "="*60)
        print("TECHNICAL DETAILS")
        print("="*60)
        html_size = report.get('technical', {}).get('html_size_bytes', 0) or 0
        print(f"  HTML Size: {html_size/1024:.1f} KB")
        text_html_ratio = report.get('technical', {}).get('text_html_ratio', 0) or 0
        print(f"  Text/HTML Ratio: {text_html_ratio}")
        print(f"  Viewport: {'Present' if report.get('technical', {}).get('viewport') else 'Missing'}")
        print(f"  Charset: {report.get('technical', {}).get('charset', 'N/A')}")
        print(f"  Canonical URL: {report.get('technical', {}).get('canonical_url', 'Not set')}")
        
        # Social Media
        social = report.get('social', {})
        if social:
            print("\n" + "="*60)
            print("SOCIAL MEDIA & SCHEMA")
            print("="*60)
            print(f"  Open Graph Tags: {social.get('open_graph_tags', 0)}")
            print(f"  Twitter Cards: {social.get('twitter_cards', 0)}")
            print(f"  Schema Markup Items: {social.get('schema_markup_count', 0)}")
        
        # Geo/Local SEO Details
        geo_local = report.get('geo_local', {})
        if geo_local:
            print("\n" + "="*60)
            print("GEO & LOCAL SEO DETAILS")
            print("="*60)
            
            address = geo_local.get('address_info', {})
            if address.get('found'):
                print(f"  Address: Found")
            
            phones = geo_local.get('phone_numbers', [])
            if phones:
                print(f"  Phone Numbers: {', '.join(phones[:3])}")
            
            hours = geo_local.get('business_hours', {})
            if hours.get('found'):
                print(f"  Business Hours: Available")
            
            gmb = geo_local.get('google_my_business', {})
            if gmb:
                print(f"  Google My Business Integration: {gmb.get('integration_score', 0)}/3")
            
            social_links = geo_local.get('social_media_links', [])
            if social_links:
                print(f"  Social Media Links: {len(social_links)} found")
        
        print("\n" + "="*60 + "\n")