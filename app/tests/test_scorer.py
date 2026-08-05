"""
Tests for the Scorer Service.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.scorer.scorer_service import ScorerService
from app.models.scorer_models.rule_result import Severity


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
        assert result["grade"] in ["A", "B", "C", "D", "F"]
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
        from app.services.scorer.score_calculator import ScoreCalculator
        
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
        from app.services.scorer.rules.on_page import TitleTagRule
        
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
        from app.services.scorer.rules.technical import SSL_CertificateRule
        
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
        from app.services.scorer.rules.content import WordCountRule
        
        rule = WordCountRule()
        
        # Test no content
        result = await rule.evaluate({"content": {"word_count": 0}})
        assert result[0].passed is False
        assert result[0].severity == Severity.CRITICAL
        
        # Test thin content
        result = await rule.evaluate({"content": {"word_count": 200}})
        assert result[0].passed is False
        assert result[0].severity == Severity.WARNING
        
        # Test good content
        result = await rule.evaluate({"content": {"word_count": 500}})
        assert result[0].passed is True
    
    @pytest.mark.asyncio
    async def test_image_alt_text_rule(self, scorer_service):
        """Test ImageAltTextRule."""
        from app.services.scorer.rules.images import ImageAltTextRule
        
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