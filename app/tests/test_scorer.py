"""
Tests for the Scorer Service.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.scorer.services.scorer_service import ScorerService
from app.modules.rule_engine.models.rule_result import Severity


@pytest.fixture
def scorer_service():
    """Create a ScorerService instance."""
    return ScorerService()


@pytest.fixture
def sample_parsed_data():
    """Sample parsed data for testing."""
    return {
        "basic": {
            "title": "Test Page Title",
            "title_length": 20,
            "meta_description": "This is a test meta description for the page.",
            "meta_description_length": 155,
            "meta_keywords": ["test", "sample"],
            "author": "Test Author",
            "language": "en",
            "charset": "UTF-8",
            "viewport": "width=device-width, initial-scale=1.0",
            "doctype": "<!DOCTYPE html>",
        },
        "http": {
            "status_code": 200,
            "headers": {
                "x-frame-options": "DENY",
                "x-content-type-options": "nosniff",
            },
            "response_time": 250,
        },
        "url": {
            "https": True,
            "url_structure": {"valid": True},
        },
        "seo": {
            "canonical_url": "https://example.com/page",
            "robots_meta": "",
            "x_robots_tag": "",
        },
        "headings": {
            "h1": ["Main Heading"],
            "h2": ["Subheading 1", "Subheading 2"],
            "h3": [],
            "heading_stats": {"is_sequential": True},
        },
        "content": {
            "word_count": 500,
            "reading_time": 3.5,
            "reading_time_minutes": 3.5,
            "paragraph_count": 8,
            "text_html_ratio": 0.15,
            "html_size": 50000,
        },
        "links": {
            "internal_count": 15,
            "external_count": 5,
            "internal_links": [{"url": "https://example.com/page1", "anchor_text": "Learn more"}],
            "external_links": [{"url": "https://external.com", "anchor_text": "External link"}],
            "broken_internal": [],
            "broken_external": [],
            "nofollow_count": 2,
        },
        "images": {
            "total_count": 10,
            "without_alt": 2,
            "sample": [
                {"src": "img1.jpg", "alt": "Description", "width": 100, "height": 100},
                {"src": "img2.jpg", "alt": "", "width": 200, "height": 200},
            ],
            "lazy_loading": True,
        },
        "structured_data": {
            "schema_markup": [
                {"@type": "Organization", "name": "Example Corp"}
            ],
        },
        "social": {
            "open_graph": {
                "tags": {
                    "og:title": "Test Page",
                    "og:description": "Test description",
                    "og:image": "https://example.com/image.jpg",
                    "og:url": "https://example.com/page",
                }
            },
            "twitter_cards": {
                "tags": {
                    "twitter:card": "summary_large_image",
                    "twitter:title": "Test Page",
                    "twitter:description": "Test description",
                }
            },
            "social_links": {
                "links": [
                    {"platform": "facebook", "url": "https://facebook.com/example"},
                    {"platform": "twitter", "url": "https://twitter.com/example"},
                ]
            },
        },
        "security": {
            "mixed_content": [],
        },
        "robots": {
            "has_rules": False,
            "sitemap_mentioned": False,
        },
        "sitemap": {
            "urls": ["https://example.com", "https://example.com/about"],
        },
        "performance": {
            "resources": {
                "css": 5,
                "javascript": 10,
                "images": 10,
            },
            "minification": {
                "html_minified": True,
                "css_minified": True,
                "js_minified": False,
            },
        },
        "javascript": {
            "errors": [],
        },
    }


class TestScorerService:
    """Test ScorerService functionality."""
    
    @pytest.mark.asyncio
    async def test_score_parsed_data(self, scorer_service, sample_parsed_data):
        """Test scoring parsed data."""
        result = await scorer_service.score_parsed_data(sample_parsed_data)
        
        assert "overall_score" in result
        assert "grade" in result
        assert "categories" in result
        assert "summary" in result
        assert "top_issues" in result
        assert "rule_results" in result
        
        assert 0 <= result["overall_score"] <= 100
        assert result["grade"] in ["A+", "A", "B+", "B", "C+", "C", "D+", "D", "F"]
        assert isinstance(result["categories"], dict)
        assert len(result["rule_results"]) > 0
    
    @pytest.mark.asyncio
    async def test_rule_evaluation(self, scorer_service, sample_parsed_data):
        """Test that rules evaluate correctly."""
        result = await scorer_service.score_parsed_data(sample_parsed_data)
        
        # Check that we have results from multiple categories
        categories = set(r.category for r in result["rule_results"])
        assert len(categories) >= 5  # At least 5 different categories
        
        # Check that we have both passed and failed rules
        passed = sum(1 for r in result["rule_results"] if r.passed)
        failed = sum(1 for r in result["rule_results"] if not r.passed)
        assert passed > 0
        assert failed > 0
    
    @pytest.mark.asyncio
    async def test_score_calculator_weights(self, scorer_service):
        """Test score calculator with custom weights."""
        from app.modules.scorer.services.score_calculator import ScoreCalculator
        
        custom_weights = {
            "on_page": 0.5,
            "technical": 0.5,
        }
        
        calculator = ScoreCalculator(weights=custom_weights)
        assert calculator.weights == custom_weights
    
    def test_get_rule_statistics(self, scorer_service):
        """Test getting rule statistics."""
        stats = scorer_service.get_rule_statistics()
        
        assert "total_rules" in stats
        assert "categories" in stats
        assert stats["total_rules"] > 0
        assert len(stats["categories"]) > 0


class TestIndividualRules:
    """Test individual scoring rules."""
    
    @pytest.mark.asyncio
    async def test_title_tag_rule(self, scorer_service):
        """Test TitleTagRule."""
        from app.modules.rule_engine.category_rules.on_page import TitleTagRule
        
        rule = TitleTagRule()
        
        # Test missing title
        result = await rule.evaluate({"basic": {}})
        assert len(result) == 1
        assert result[0].passed is False
        assert result[0].severity == Severity.CRITICAL
        
        # Test optimal title
        result = await rule.evaluate({"basic": {"title": "Test Title", "title_length": 45}})
        assert result[0].passed is True
        
        # Test too short title
        result = await rule.evaluate({"basic": {"title": "Short", "title_length": 15}})
        assert result[0].passed is False
        assert result[0].severity == Severity.WARNING
    
    @pytest.mark.asyncio
    async def test_ssl_certificate_rule(self, scorer_service):
        """Test SSLCertificateRule."""
        from app.modules.rule_engine.category_rules.technical import SSL_CertificateRule
        
        rule = SSL_CertificateRule()
        
        # Test HTTPS with valid SSL
        result = await rule.evaluate({
            "url": {"https": True},
            "ssl": {"valid": True, "issuer": "Let's Encrypt"}
        })
        assert result[0].passed is True
        
        # Test no HTTPS
        result = await rule.evaluate({
            "url": {"https": False},
            "ssl": {}
        })
        assert result[0].passed is False
        assert result[0].severity == Severity.CRITICAL
    
    @pytest.mark.asyncio
    async def test_word_count_rule(self, scorer_service):
        """Test WordCountRule."""
        from app.modules.rule_engine.category_rules.content import WordCountRule
        
        rule = WordCountRule()
        
        # Test no content
        result = await rule.evaluate({"content": {"word_count": 0}})
        assert result[0].passed is False
        assert result[0].severity == Severity.CRITICAL
        
        # Test thin content (<150 words)
        result = await rule.evaluate({"content": {"word_count": 100}})
        assert result[0].passed is False
        assert result[0].severity == Severity.WARNING
        
        # Test acceptable content (150-300 words)
        result = await rule.evaluate({"content": {"word_count": 200}})
        assert result[0].passed is True
        assert result[0].severity == Severity.PASSED
        
        # Test good content (300+ words)
        result = await rule.evaluate({"content": {"word_count": 500}})
        assert result[0].passed is True
        assert result[0].severity == Severity.PASSED
    
    @pytest.mark.asyncio
    async def test_image_alt_text_rule(self, scorer_service):
        """Test ImageAltTextRule."""
        from app.modules.rule_engine.category_rules.images import ImageAltTextRule
        
        rule = ImageAltTextRule()
        
        # Test no images
        result = await rule.evaluate({"images": {"total_count": 0}})
        assert result[0].passed is True
        
        # Test all images have alt
        result = await rule.evaluate({
            "images": {"total_count": 5, "without_alt": 0}
        })
        assert result[0].passed is True
        
        # Test missing alt text
        result = await rule.evaluate({
            "images": {"total_count": 10, "without_alt": 5}
        })
        assert result[0].passed is False
        assert result[0].severity == Severity.WARNING

    @pytest.mark.asyncio
    async def test_title_tag_pixel_width(self, scorer_service):
        """Test TitleTagRule pixel width estimation."""
        from app.modules.rule_engine.category_rules.on_page import TitleTagRule
        
        rule = TitleTagRule()
        result = await rule.evaluate({
            "basic": {"title": "A" * 100},
            "content": {"text": "word " * 20}
        })
        assert result[0].data["pixel_width_estimate"] == 650

    @pytest.mark.asyncio
    async def test_h1_tag_improvements(self, scorer_service):
        """Test H1TagRule with empty H1s and consistency."""
        from app.modules.rule_engine.category_rules.on_page import H1TagRule
        
        rule = H1TagRule()
        
        # Empty H1s
        result = await rule.evaluate({
            "headings": {"h1": ["", ""]},
            "basic": {"title": "Title"}
        })
        assert result[0].passed is False
        assert result[0].severity == Severity.WARNING
        
        # Multiple H1s
        result = await rule.evaluate({
            "headings": {"h1": ["H1 A", "H1 B"]},
            "basic": {"title": "Title"}
        })
        assert result[0].passed is False
        assert result[0].severity == Severity.WARNING

    @pytest.mark.asyncio
    async def test_heading_hierarchy_improvements(self, scorer_service):
        """Test HeadingHierarchyRule with excessive/duplicate headings."""
        from app.modules.rule_engine.category_rules.on_page import HeadingHierarchyRule
        
        rule = HeadingHierarchyRule()
        
        # Excessive headings
        result = await rule.evaluate({
            "headings": {
                "h1": ["H1"],
                "h2": [f"H2{i}" for i in range(12)],
                "heading_stats": {"heading_count": 13, "is_sequential": True}
            }
        })
        assert result[0].passed is False
        assert "Too many H2 headings" in result[0].message or "Excessive headings" in result[0].message
        
        # Duplicate headings
        result = await rule.evaluate({
            "headings": {
                "h1": ["Same"],
                "h2": ["Same", "Same"],
                "heading_stats": {"heading_count": 3, "is_sequential": True}
            }
        })
        assert result[0].passed is False
        assert "duplicate headings" in result[0].message

    @pytest.mark.asyncio
    async def test_keyword_in_content_rule(self, scorer_service):
        """Test KeywordInContentRule location checks."""
        from app.modules.rule_engine.category_rules.content import KeywordInContentRule
        
        rule = KeywordInContentRule()
        
        result = await rule.evaluate({
            "target_keyword": "seo",
            "basic": {"title": "SEO Guide", "meta_description": "Learn SEO"},
            "headings": {"h1": ["SEO Basics"], "h2": ["SEO Tips"]},
            "url": {"path": "/seo-guide"},
            "content": {"text": "SEO is important. SEO helps."}
        })
        assert result[0].passed is True
        assert "title" in result[0].data["found_in"]
        assert "h1" in result[0].data["found_in"]
        assert "body" in result[0].data["found_in"]

    @pytest.mark.asyncio
    async def test_duplicate_content_rule(self, scorer_service):
        """Test DuplicateContentRule with canonical and duplicates."""
        from app.modules.rule_engine.category_rules.content import DuplicateContentRule
        
        rule = DuplicateContentRule()
        
        # No issues
        result = await rule.evaluate({
            "seo": {"canonical_url": "https://example.com/page"}
        })
        assert result[0].passed is True
        
        # Duplicate group
        result = await rule.evaluate({
            "seo": {
                "canonical_url": "",
                "content_hash": "abc123",
                "duplicate_group_size": 3
            }
        })
        assert result[0].passed is False
        assert result[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_ssl_certificate_https_false(self, scorer_service):
        """Test SSLCertificateRule returns CRITICAL when HTTPS is False."""
        from app.modules.rule_engine.category_rules.technical import SSL_CertificateRule
        
        rule = SSL_CertificateRule()
        result = await rule.evaluate({
            "url": {"https": False},
            "http": {"status_code": 200},
            "ssl": {}
        })
        assert result[0].passed is False
        assert result[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_broken_links_no_data(self, scorer_service):
        """Test BrokenLinksRule returns INFO when no broken link data."""
        from app.modules.rule_engine.category_rules.links import BrokenLinksRule
        
        rule = BrokenLinksRule()
        result = await rule.evaluate({"links": {}})
        assert result[0].passed is True
        assert result[0].severity == Severity.INFO

    @pytest.mark.asyncio
    async def test_canonical_url_improvements(self, scorer_service):
        """Test CanonicalUrlRule with self-referencing and relative."""
        from app.modules.rule_engine.category_rules.on_page import CanonicalUrlRule
        
        rule = CanonicalUrlRule()
        
        # Self-referencing canonical
        result = await rule.evaluate({
            "seo": {"canonical_url": "https://example.com/page"},
            "url": {"url": "https://example.com/page"}
        })
        assert result[0].passed is True
        assert result[0].data.get("self_referencing") is True
        
        # Relative canonical
        result = await rule.evaluate({
            "seo": {"canonical_url": "/page"},
            "url": {"url": "https://example.com/page"}
        })
        assert result[0].passed is False
        assert result[0].data.get("relative_canonical") is True

    @pytest.mark.asyncio
    async def test_new_url_rule(self, scorer_service):
        """Test UrlRule."""
        from app.modules.rule_engine.category_rules.technical import UrlRule
        
        rule = UrlRule()
        result = await rule.evaluate({
            "url": {"url": "https://example.com/clean-url", "path": "/clean-url", "query": ""}
        })
        assert result[0].passed is True

    @pytest.mark.asyncio
    async def test_new_mobile_rule(self, scorer_service):
        """Test MobileRule."""
        from app.modules.rule_engine.category_rules.technical import MobileRule
        
        rule = MobileRule()
        result = await rule.evaluate({
            "basic": {"viewport": "width=device-width, initial-scale=1.0"}
        })
        assert result[0].passed is True

    @pytest.mark.asyncio
    async def test_new_http_status_rule(self, scorer_service):
        """Test HttpStatusRule."""
        from app.modules.rule_engine.category_rules.technical import HttpStatusRule
        
        rule = HttpStatusRule()
        result = await rule.evaluate({"http": {"status_code": 404}})
        assert result[0].passed is False
        assert result[0].severity == Severity.WARNING
        
        result = await rule.evaluate({"http": {"status_code": 500}})
        assert result[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_new_hreflang_rule(self, scorer_service):
        """Test HreflangRule."""
        from app.modules.rule_engine.category_rules.technical import HreflangRule
        
        rule = HreflangRule()
        result = await rule.evaluate({"hreflang": []})
        assert result[0].passed is True
        assert result[0].severity == Severity.INFO

    @pytest.mark.asyncio
    async def test_new_duplicate_rules(self, scorer_service):
        """Test duplicate title/description/h1 rules."""
        from app.modules.rule_engine.category_rules.content import (
            DuplicateTitlesRule, DuplicateDescriptionsRule, DuplicateH1sRule
        )
        
        # Duplicate title
        rule = DuplicateTitlesRule()
        result = await rule.evaluate({
            "seo": {"title": "Same Title", "duplicate_titles": ["Same Title", "Other"]}
        })
        assert result[0].passed is False
        assert result[0].severity == Severity.WARNING
        
        # Duplicate description
        rule = DuplicateDescriptionsRule()
        result = await rule.evaluate({
            "seo": {"meta_description": "Same Desc", "duplicate_descriptions": ["Same Desc"]}
        })
        assert result[0].passed is False
        
        # Duplicate H1
        rule = DuplicateH1sRule()
        result = await rule.evaluate({
            "headings": {"h1": ["Same H1"]},
            "duplicate_h1s": ["Same H1"]
        })
        assert result[0].passed is False

    @pytest.mark.asyncio
    async def test_new_core_web_vitals_rule(self, scorer_service):
        """Test CoreWebVitalsRule."""
        from app.modules.rule_engine.category_rules.performance import CoreWebVitalsRule
        
        rule = CoreWebVitalsRule()
        result = await rule.evaluate({})
        assert result[0].passed is True
        assert result[0].severity == Severity.INFO
        
        result = await rule.evaluate({
            "core_web_vitals": {"lcp": 5.0, "inp": 600, "cls": 0.3}
        })
        assert result[0].passed is False
        assert result[0].severity == Severity.CRITICAL


class TestScoreAPI:
    """Test the score API endpoint."""
    
    @pytest.mark.asyncio
    async def test_score_endpoint_with_parsed_data(self):
        """Test scoring endpoint with parsed data."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            sample_data = {
                "basic": {
                    "title": "Test Page",
                    "title_length": 30,
                    "meta_description": "Test description",
                    "meta_description_length": 150,
                    "language": "en",
                    "charset": "UTF-8",
                    "viewport": "width=device-width, initial-scale=1.0",
                    "doctype": "<!DOCTYPE html>",
                },
                "http": {"status_code": 200, "headers": {}, "response_time": 200},
                "url": {"https": True},
                "content": {"word_count": 500},
            }
            
            response = await client.post(
                "/api/v1/scorer/score",
                json={"parsed_data": sample_data}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "overall_score" in data
            assert "grade" in data
    
    @pytest.mark.asyncio
    async def test_score_endpoint_missing_data(self):
        """Test scoring endpoint with missing data."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/scorer/score",
                json={}
            )
            
            assert response.status_code == 400
            assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_get_rule_statistics(self):
        """Test getting rule statistics."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/scorer/rules/statistics")
            
            assert response.status_code == 200
            data = response.json()
            assert "total_rules" in data
            assert "categories" in data
            assert data["total_rules"] > 0
    
    @pytest.mark.asyncio
    async def test_get_rule_categories(self):
        """Test getting rule categories."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/scorer/rules/categories")
            
            assert response.status_code == 200
            data = response.json()
            assert "categories" in data
            assert "weights" in data
            assert "total_rules" in data
            assert len(data["categories"]) > 0