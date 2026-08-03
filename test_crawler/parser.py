"""
Crawl Data Parser Module
========================
Parses and analyzes crawled website data for SEO insights.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import Counter


class CrawlDataParser:
    """Parses crawled data files and extracts SEO insights."""

    def __init__(self, crawl_dir: str = "crawl_data"):
        """
        Initialize parser.

        Args:
            crawl_dir: Base directory containing crawl data
        """
        self.crawl_dir = Path(crawl_dir)

    def load_crawl_file(self, filepath: str) -> Dict[str, Any]:
        """
        Load a single crawl data file.

        Args:
            filepath: Path to crawl data JSON file

        Returns:
            Parsed data dictionary
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

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
        Calculate SEO score and identify issues.

        Args:
            data: Crawled data dictionary

        Returns:
            SEO analysis results
        """
        page_data = data.get('data', {})
        score = 100
        issues = []
        warnings = []
        passed = []

        # Title checks
        title = page_data.get('title')
        title_length = page_data.get('title_length', 0)

        if not title:
            score -= 10
            issues.append("Missing page title")
        else:
            if 30 <= title_length <= 60:
                passed.append("Title length is optimal (30-60 characters)")
            elif title_length < 30:
                warnings.append(f"Title too short ({title_length} chars, recommended: 30-60)")
                score -= 3
            else:
                warnings.append(f"Title too long ({title_length} chars, recommended: 30-60)")
                score -= 3

        # Meta description checks
        meta_desc = page_data.get('meta_description')
        meta_desc_length = page_data.get('meta_description_length', 0)

        if not meta_desc:
            score -= 10
            issues.append("Missing meta description")
        else:
            if 150 <= meta_desc_length <= 160:
                passed.append("Meta description length is optimal (150-160 characters)")
            elif meta_desc_length < 150:
                warnings.append(f"Meta description too short ({meta_desc_length} chars)")
                score -= 3
            else:
                warnings.append(f"Meta description too long ({meta_desc_length} chars)")
                score -= 3

        # Heading checks
        headings = page_data.get('headings', {})
        h1_tags = headings.get('h1', [])

        if len(h1_tags) == 0:
            issues.append("Missing H1 tag")
            score -= 10
        elif len(h1_tags) == 1:
            passed.append("Has exactly one H1 tag")
        else:
            warnings.append(f"Multiple H1 tags found ({len(h1_tags)})")
            score -= 5

        # Image alt text checks
        images = page_data.get('images', {})
        total_images = images.get('total_count', 0)
        images_without_alt = images.get('without_alt', 0)

        if total_images > 0:
            if images_without_alt == 0:
                passed.append("All images have alt text")
            else:
                warnings.append(f"{images_without_alt} images missing alt text")
                score -= min(images_without_alt * 2, 10)

        # Links check
        links = page_data.get('links', {})
        total_links = links.get('internal_count', 0) + links.get('external_count', 0)

        if total_links == 0:
            warnings.append("No links found on page")
            score -= 5
        else:
            passed.append(f"Page has {total_links} links")

        # Word count check
        word_count = page_data.get('word_count', 0)
        if word_count < 300:
            warnings.append(f"Thin content: only {word_count} words (recommended: 300+)")
            score -= 10
        else:
            passed.append(f"Good content length: {word_count} words")

        # Canonical URL check
        has_canonical = page_data.get('has_canonical', False)
        if has_canonical:
            passed.append("Has canonical URL")
        else:
            warnings.append("Missing canonical URL")
            score -= 5

        # Language check
        language = page_data.get('language')
        if language:
            passed.append(f"Language declared: {language}")
        else:
            warnings.append("Language not specified")

        # Open Graph check
        open_graph = page_data.get('open_graph', {})
        if open_graph:
            passed.append(f"Open Graph tags present ({len(open_graph)} tags)")
        else:
            warnings.append("No Open Graph tags found")

        # Schema markup check
        schema = page_data.get('schema_markup', [])
        if schema:
            passed.append(f"Schema markup found ({len(schema)} items)")
        else:
            warnings.append("No structured data/schema markup")

        # Viewport check
        viewport = page_data.get('viewport')
        if viewport:
            passed.append("Viewport meta tag present (mobile-friendly)")
        else:
            issues.append("Missing viewport meta tag (not mobile-friendly)")
            score -= 10

        # Reading time
        reading_time = page_data.get('reading_time_minutes', 0)

        return {
            "score": max(0, score),
            "grade": self._get_grade(score),
            "issues": issues,
            "warnings": warnings,
            "passed": passed,
            "reading_time_minutes": reading_time
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
        from bs4 import BeautifulSoup
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
        # Remove common stop words
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
                # Extract domain from relative URLs if possible
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

        # Count external domains
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

        # Check for large images (basic check)
        large_images = []
        for img in sample:
            src = img.get('src', '')
            # Check if it looks like a large image file
            if any(ext in src.lower() for ext in ['.png', '.jpg', '.jpeg']) and src:
                large_images.append(src)

        return {
            "total_images": total,
            "images_with_alt": total - without_alt,
            "images_without_alt": without_alt,
            "alt_text_coverage_percent": round(alt_coverage, 1),
            "status": "Good" if without_alt == 0 else "Needs Improvement",
            "sample_images": sample[:5]
        }

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

        page_data = crawl_data.get('data', {})

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
                "title": page_data.get('title'),
                "meta_description": page_data.get('meta_description'),
                "word_count": page_data.get('word_count'),
                "reading_time_minutes": page_data.get('reading_time_minutes'),
                "language": page_data.get('language'),
                "doctype": page_data.get('doctype')
            },
            "technical": {
                "html_size_bytes": page_data.get('html_size'),
                "text_html_ratio": page_data.get('text_html_ratio'),
                "viewport": page_data.get('viewport'),
                "charset": page_data.get('charset'),
                "canonical_url": page_data.get('canonical_url'),
                "robots_meta": page_data.get('robots_meta')
            },
            "social": {
                "open_graph_tags": len(page_data.get('open_graph', {})),
                "twitter_cards": len(page_data.get('twitter_cards', {})),
                "schema_markup_count": len(page_data.get('schema_markup', []))
            }
        }

        return report

    def print_report(self, report: Dict[str, Any]) -> None:
        """
        Print formatted SEO report to console.

        Args:
            report: Report dictionary from generate_report()
        """
        if not report:
            return

        print("\n" + "="*60)
        print("SEO ANALYSIS REPORT")
        print("="*60)
        print(f"URL: {report['url']}")
        print(f"Crawled: {report['crawled_at']}")
        print(f"Domain: {report['domain']}")

        # SEO Score
        seo = report['seo_score']
        print("\n" + "-"*60)
        print(f"SEO SCORE: {seo['score']}/100 (Grade: {seo['grade']})")
        print(f"Reading Time: {seo['reading_time_minutes']} minute(s)")

        if seo['issues']:
            print("\n❌ CRITICAL ISSUES:")
            for issue in seo['issues']:
                print(f"  • {issue}")

        if seo['warnings']:
            print("\n⚠️  WARNINGS:")
            for warning in seo['warnings']:
                print(f"  • {warning}")

        if seo['passed']:
            print("\n✅ PASSED CHECKS:")
            for check in seo['passed'][:5]:  # Show top 5
                print(f"  • {check}")

        # Keywords
        keywords = report['keywords']
        if keywords:
            print("\n" + "-"*60)
            print("TOP KEYWORDS:")
            for kw in keywords[:5]:
                print(f"  • {kw['keyword']} (frequency: {kw['frequency']})")

        # Links
        links = report['links']
        print("\n" + "-"*60)
        print("LINK ANALYSIS:")
        print(f"  Total Links: {links['total_links']}")
        print(f"  Internal: {links['internal_links']}")
        print(f"  External: {links['external_links']}")
        print(f"  Ratio: {links['ratio']}")

        # Images
        images = report['images']
        print("\n" + "-"*60)
        print("IMAGE ANALYSIS:")
        print(f"  Total Images: {images['total_images']}")
        print(f"  Alt Text Coverage: {images['alt_text_coverage_percent']}%")
        print(f"  Status: {images['status']}")

        # Social
        social = report['social']
        print("\n" + "-"*60)
        print("SOCIAL MEDIA:")
        print(f"  Open Graph Tags: {social['open_graph_tags']}")
        print(f"  Twitter Cards: {social['twitter_cards']}")
        print(f"  Schema Markup: {social['schema_markup_count']}")

        print("\n" + "="*60 + "\n")


def main():
    """Main entry point for CLI usage."""
    import sys

    print("="*60)
    print("CRAWL DATA PARSER")
    print("="*60)

    # Check if URL provided as argument
    if len(sys.argv) >= 2:
        url = sys.argv[1]
    else:
        # List available crawled domains
        crawl_dir = Path("crawl_data")
        if crawl_dir.exists():
            domains = [d.name for d in crawl_dir.iterdir() if d.is_dir()]

            if domains:
                print("\nAvailable crawled domains:")
                for i, domain in enumerate(domains, 1):
                    print(f"  {i}. {domain}")

                choice = input("\nEnter domain number or URL: ").strip()

                # Check if it's a number
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(domains):
                        domain = domains[idx]
                        # Get a sample URL from this domain
                        files = list((crawl_dir / domain).glob("*.json"))
                        if files:
                            # Load first file to get URL
                            with open(files[0], 'r') as f:
                                data = json.load(f)
                                url = data.get('url', '')
                        else:
                            print(f"No crawl data found for domain: {domain}")
                            sys.exit(1)
                    else:
                        url = choice
                except ValueError:
                    url = choice
            else:
                url = input("\nEnter URL to analyze: ").strip()
        else:
            url = input("\nEnter URL to analyze: ").strip()

        if not url:
            print("Error: No URL provided")
            sys.exit(1)

    try:
        parser = CrawlDataParser()
        report = parser.generate_report(url)

        if report:
            parser.print_report(report)
        else:
            print(f"No crawl data found for: {url}")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()