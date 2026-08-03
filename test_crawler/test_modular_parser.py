"""Test script for the new modular parser structure."""
import sys
from pathlib import Path

# Add test_crawler to path
sys.path.insert(0, str(Path(__file__).parent))

from parser import ParserService


def test_parse_domain(domain: str = "cyfuture.com"):
    """
    Test parsing with new modular parser.
    
    Args:
        domain: Domain to test with
    """
    print("="*60)
    print(f"TESTING MODULAR PARSER - Domain: {domain}")
    print("="*60)
    
    # Initialize parser service
    parser = ParserService(crawl_dir="crawl_data")
    
    # Get latest crawl data
    crawl_data = parser.get_latest_crawl_by_domain(domain)
    
    if not crawl_data:
        print(f"❌ No crawl data found for domain: {domain}")
        return False
    
    print(f"✅ Found crawl data: {crawl_data.get('url', 'N/A')}")
    print(f"   Crawled at: {crawl_data.get('crawled_at', 'N/A')}")
    
    # Parse HTML
    html = crawl_data.get('html', '')
    url = crawl_data.get('url', '')
    
    print(f"\n📊 Parsing HTML ({len(html)} bytes)...")
    parsed_data = parser.parse_html(html, url, crawl_data)
    
    # Display parsed sections
    print("\n" + "="*60)
    print("PARSED DATA SECTIONS")
    print("="*60)
    
    for section, data in parsed_data.items():
        print(f"\n✓ {section.upper()}")
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (list, dict)):
                    if isinstance(value, list):
                        print(f"  • {key}: [{len(value)} items]")
                    else:
                        print(f"  • {key}: {{{len(value)} keys}}")
                else:
                    display_val = str(value)[:50] if value else "None"
                    print(f"  • {key}: {display_val}")
    
    # Generate SEO analysis
    print("\n" + "="*60)
    print("SEO ANALYSIS")
    print("="*60)
    
    crawl_data['data'] = parsed_data
    seo_analysis = parser.analyze_seo_score(crawl_data)
    
    print(f"\nOverall Score: {seo_analysis.get('overall_score', 0)}/100")
    print(f"Grade: {seo_analysis.get('overall_grade', 'N/A')}")
    
    breakdown = seo_analysis.get('breakdown', {})
    for category, data in breakdown.items():
        if category == 'local_seo':
            continue
        score = data.get('score', 0)
        grade = data.get('grade', 'N/A')
        print(f"  • {category.replace('_', ' ').title()}: {score}/100 ({grade})")
    
    # Extract keywords
    keywords = parser.extract_keywords(crawl_data, top_n=5)
    if keywords:
        print(f"\nTop Keywords:")
        for kw in keywords:
            print(f"  • {kw['keyword']} (freq: {kw['frequency']})")
    
    # Analyze links
    link_analysis = parser.analyze_links(crawl_data)
    print(f"\nLink Analysis:")
    print(f"  • Total: {link_analysis.get('total_links', 0)}")
    print(f"  • Internal: {link_analysis.get('internal_links', 0)}")
    print(f"  • External: {link_analysis.get('external_links', 0)}")
    
    # Analyze images
    image_analysis = parser.analyze_images(crawl_data)
    print(f"\nImage Analysis:")
    print(f"  • Total: {image_analysis.get('total_images', 0)}")
    print(f"  • With Alt: {image_analysis.get('images_with_alt', 0)}")
    print(f"  • Without Alt: {image_analysis.get('images_without_alt', 0)}")
    
    # Save parsed data
    print("\n" + "="*60)
    print("SAVING RESULTS")
    print("="*60)
    
    saved_path = parser.save_parsed_data(parsed_data, domain)
    print(f"✅ Parsed data saved to: {saved_path}")
    
    # Generate and save report
    report = parser.generate_report_by_domain(domain)
    if report:
        report_path = parser.save_parsed_data(report, domain)
        print(f"✅ Report saved to: {report_path}")
    
    print("\n" + "="*60)
    print("✅ TEST COMPLETED SUCCESSFULLY")
    print("="*60)
    
    return True


def test_all_domains():
    """Test with all available crawled domains."""
    crawl_dir = Path("crawl_data")
    if not crawl_dir.exists():
        print("❌ crawl_data directory not found")
        return
    
    domains = [d.name for d in crawl_dir.iterdir() if d.is_dir()]
    
    if not domains:
        print("❌ No crawled domains found")
        return
    
    print(f"\nFound {len(domains)} domains: {', '.join(domains)}")
    
    for domain in domains:
        print(f"\n\n{'='*60}")
        test_parse_domain(domain)
        print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        domain = sys.argv[1]
        test_parse_domain(domain)
    else:
        # Test with first available domain
        crawl_dir = Path("crawl_data")
        if crawl_dir.exists():
            domains = [d.name for d in crawl_dir.iterdir() if d.is_dir()]
            if domains:
                test_parse_domain(domains[0])
            else:
                print("No domains found to test")
        else:
            print("crawl_data directory not found")