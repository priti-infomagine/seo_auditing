"""Test the scorer implementation."""
import json
import sys
from pathlib import Path

# Test imports
from app.services.scorer import (
    Scorer,
    ScoreService,
    ScoreWeights,
    Severity,
    SeverityLevel,
    RecommendationEngine,
    TechnicalScorer,
    OnPageScorer,
    ContentScorer,
    ImageScorer,
    LinkScorer,
    GeoScorer,
    LocalScorer,
    PerformanceScorer,
    AIScorer,
    SSLRule,
    ViewportRule,
    CanonicalRule,
    TitleRule,
    MetaDescriptionRule,
    H1Rule,
    WordCountRule,
    AltTextRule,
    InternalLinksRule,
    AddressRule,
    PhoneRule,
    BusinessHoursRule,
    NAPRule,
    ResponseTimeRule,
    StructuredDataRule,
)

print("=== All scorer imports OK ===")

# Test API router imports
from app.apis.endpoints.v1.sc
print(f"=== Weights: {weights.get_all_weights()} ===")

# Test Severity
print(f"=== Severity levels: {[s.value for s in SeverityLevel]} ===")
print(f"=== Critical deduction: {Severity.get_deduction(SeverityLevel.CRITICAL)} ===")

# Test RecommendationEngine
recs = RecommendationEngine.get_all_recommendations()
print(f"=== Available recommendations: {len(recs)} ===")

# Test with sample parsed data
sample_data = {
    "url": "https://example.com/",
    "basic": {
        "title": "Example Domain - A Comprehensive Test Website",
        "title_length": 45,
        "meta_description": "This is a sample meta description for testing purposes that is within the optimal length range.",
        "meta_description_length": 155,
        "language": "en",
        "charset": "utf-8",
        "doctype": "html",
        "viewport": "width=device-width, initial-scale=1",
    },
    "http": {
        "status_code": 200,
        "response_time": 150,
        "redirects": [],
    },
    "seo": {
        "canonical_url": "https://example.com/",
        "robots_meta": "index,follow",
    },
    "headings": {
        "headings": {
            "h1": ["Welcome to Example"],
            "h2": ["About Us", "Services"],
        }
    },
    "content": {
        "word_count": 750,
        "reading_time": 3,
        "paragraph_count": 8,
        "text_html_ratio": 0.25,
        "content_hash": "abc123",
    },
    "links": {
        "total_links": 15,
        "internal_count": 10,
        "external_count": 5,
        "external_domains": {"google.com": 2, "twitter.com": 2, "facebook.com": 1},
    },
    "images": {
        "total_count": 10,
        "without_alt": 1,
        "lazy_loading": True,
        "sample": [
            {"src": "img1.jpg", "alt": "Image 1", "title": "Image 1", "width": "100", "height": "100"},
            {"src": "img2.jpg", "alt": "Image 2", "title": "", "width": "", "height": ""},
        ],
    },
    "social": {
        "open_graph_tags": 3,
        "twitter_cards": 2,
        "schema_markup_count": 1,
    },
    "structured_data": {
        "schema_markup": [{"@type": "WebSite"}],
    },
    "local_seo": {
        "address": {"found": True},
        "phone_numbers": ["+1234567890"],
        "business_hours": {"found": True},
        "geo_meta_tags": {"found": True},
        "location_keywords": ["New York", "NYC"],
        "google_business": {"integration_score": 2},
        "nap_consistency": {"consistency_score": 0.8},
    },
    "technical": {
        "ssl_certificate": True,
        "html_size_bytes": 50000,
        "text_html_ratio": 0.25,
    },
}

# Test individual category scorers
print("\n=== Testing individual category scorers ===")
scorers = [
    TechnicalScorer(sample_data),
    OnPageScorer(sample_data),
    ContentScorer(sample_data),
    ImageScorer(sample_data),
    LinkScorer(sample_data),
    GeoScorer(sample_data),
    LocalScorer(sample_data),
    PerformanceScorer(sample_data),
    AIScorer(sample_data),
]

for scorer in scorers:
    result = scorer.evaluate()
    print(f"  {scorer.category_label}: score={result['score']}, grade={result['grade']}, issues={len(result['issues'])}, warnings={len(result['warnings'])}, passed={len(result['passed'])}")

# Test main Scorer
print("\n=== Testing main Scorer ===")
scorer = Scorer()
result = scorer.score(sample_data)
print(f"  Overall score: {result['overall_score']}")
print(f"  Overall grade: {result['overall_grade']}")
print(f"  Issue count: {result['issue_count']}")
print(f"  Warning count: {result['warning_count']}")
print(f"  Passed count: {result['passed_count']}")
print(f"  Recommendations: {len(result['recommendations'])}")

# Test ScoreService
print("\n=== Testing ScoreService ===")
service = ScoreService()
print(f"  Available weights: {service.get_available_weights()}")
print(f"  Available recommendations: {len(service.get_available_recommendations())}")

# Test rules
print("\n=== Testing rules ===")
rules = [
    SSLRule(sample_data),
    ViewportRule(sample_data),
    CanonicalRule(sample_data),
    TitleRule(sample_data),
    MetaDescriptionRule(sample_data),
    H1Rule(sample_data),
    WordCountRule(sample_data),
    AltTextRule(sample_data),
    InternalLinksRule(sample_data),
    AddressRule(sample_data),
    PhoneRule(sample_data),
    BusinessHoursRule(sample_data),
    NAPRule(sample_data),
    ResponseTimeRule(sample_data),
    StructuredDataRule(sample_data),
]

for rule in rules:
    result = rule.check()
    status = "PASS" if result["passed"] else "FAIL"
    print(f"  [{status}] {rule.rule_name}: {result['message']}")

print("\n=== All tests passed ===")