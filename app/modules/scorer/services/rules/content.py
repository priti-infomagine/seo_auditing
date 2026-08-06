"""
Content Quality Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.scorer.models.rule_result import RuleResult, Severity


class WordCountRule(BaseRule):
    """Check content length."""
    rule_id = "content_001"
    name = "Word Count"
    category = "content"
    description = "Page should have sufficient content (300+ words recommended)"
    weight = 1.2
    tags = ["critical", "content", "quality"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        content = data.get("content", {})
        word_count = content.get("word_count", 0)
        
        if word_count == 0:
            return [self._create_result(
                passed=False,
                message="No content found on page",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Add substantial content to the page (aim for 300+ words)",
            )]
        
        if word_count < 300:
            return [self._create_result(
                passed=False,
                message=f"Thin content: {word_count} words (recommended: 300+)",
                severity=Severity.WARNING,
                score_impact=-8,
                recommendation=f"Increase content to at least 300 words (currently {word_count})",
                data={"word_count": word_count},
            )]
        
        if word_count >= 1000:
            return [self._create_result(
                passed=True,
                message=f"Excellent content length: {word_count} words",
                severity=Severity.PASSED,
                score_impact=2,
                data={"word_count": word_count},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Good content length: {word_count} words",
            severity=Severity.PASSED,
            score_impact=0,
            data={"word_count": word_count},
        )]


class ReadingTimeRule(BaseRule):
    """Check reading time."""
    rule_id = "content_002"
    name = "Reading Time"
    category = "content"
    description = "Optimal reading time for user engagement"
    weight = 0.7
    tags = ["info", "content", "ux"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        content = data.get("content", {})
        reading_time = content.get("reading_time", 0)
        reading_time_minutes = content.get("reading_time_minutes", reading_time / 60 if reading_time else 0)
        
        if reading_time_minutes == 0:
            return [self._create_result(
                passed=True,
                message="No reading time data available",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if reading_time_minutes > 15:
            return [self._create_result(
                passed=False,
                message=f"Long reading time: {reading_time_minutes:.1f} minutes (consider breaking into sections)",
                severity=Severity.INFO,
                score_impact=-2,
                recommendation="Consider breaking long content into multiple pages or sections",
                data={"reading_time_minutes": reading_time_minutes},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Reading time: {reading_time_minutes:.1f} minutes",
            severity=Severity.PASSED,
            score_impact=0,
            data={"reading_time_minutes": reading_time_minutes},
        )]


class ParagraphCountRule(BaseRule):
    """Check paragraph count and structure."""
    rule_id = "content_003"
    name = "Paragraph Structure"
    category = "content"
    description = "Content should have well-structured paragraphs"
    weight = 0.8
    tags = ["warning", "content", "readability"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        content = data.get("content", {})
        paragraph_count = content.get("paragraph_count", 0)
        word_count = content.get("word_count", 0)
        
        if paragraph_count == 0:
            return [self._create_result(
                passed=False,
                message="No paragraphs found",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Break content into paragraphs for better readability",
            )]
        
        avg_words_per_para = word_count / paragraph_count if paragraph_count > 0 else 0
        
        if avg_words_per_para > 150:
            return [self._create_result(
                passed=False,
                message=f"Paragraphs are too long (avg {avg_words_per_para:.0f} words/paragraph)",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Break long paragraphs into smaller chunks (aim for 50-150 words)",
                data={"paragraph_count": paragraph_count, "avg_words_per_para": avg_words_per_para},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Good paragraph structure ({paragraph_count} paragraphs, avg {avg_words_per_para:.0f} words)",
            severity=Severity.PASSED,
            score_impact=0,
            data={"paragraph_count": paragraph_count, "avg_words_per_para": avg_words_per_para},
        )]


class TextHtmlRatioRule(BaseRule):
    """Check text-to-HTML ratio."""
    rule_id = "content_004"
    name = "Text-to-HTML Ratio"
    category = "content"
    description = "Good text-to-HTML ratio indicates quality content"
    weight = 1.0
    tags = ["warning", "content", "quality"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        content = data.get("content", {})
        ratio = content.get("text_html_ratio", 0)
        html_size = content.get("html_size", 0)
        
        if ratio == 0:
            return [self._create_result(
                passed=True,
                message="Text-to-HTML ratio not available",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if ratio < 0.1:
            return [self._create_result(
                passed=False,
                message=f"Low text-to-HTML ratio: {ratio:.2%} (too much code, not enough content)",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Increase text content or reduce HTML/CSS/JavaScript bloat",
                data={"text_html_ratio": ratio, "html_size": html_size},
            )]
        
        if ratio >= 0.25:
            return [self._create_result(
                passed=True,
                message=f"Excellent text-to-HTML ratio: {ratio:.2%}",
                severity=Severity.PASSED,
                score_impact=1,
                data={"text_html_ratio": ratio},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Good text-to-HTML ratio: {ratio:.2%}",
            severity=Severity.PASSED,
            score_impact=0,
            data={"text_html_ratio": ratio},
        )]


class KeywordInContentRule(BaseRule):
    """Check if primary keyword appears in content."""
    rule_id = "content_005"
    name = "Keyword in Content"
    category = "content"
    description = "Primary keyword should appear in first 100 words"
    weight = 1.1
    tags = ["critical", "content", "keywords"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        # This rule requires keyword data which may come from extract_keywords
        content = data.get("content", {})
        first_paragraph = content.get("first_paragraph", "")
        
        if not first_paragraph:
            return [self._create_result(
                passed=True,
                message="Keyword presence check skipped (requires keyword analysis)",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=True,
            message="Content present for keyword analysis",
            severity=Severity.PASSED,
            score_impact=0,
        )]


class DuplicateContentRule(BaseRule):
    """Check for duplicate content indicators."""
    rule_id = "content_006"
    name = "Duplicate Content"
    category = "content"
    description = "Check for potential duplicate content issues"
    weight = 1.0
    tags = ["warning", "content", "duplicate"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        seo = data.get("seo", {})
        canonical = seo.get("canonical_url", "")
        
        # If no canonical, might indicate duplicate content risk
        if not canonical:
            return [self._create_result(
                passed=False,
                message="No canonical URL (potential duplicate content risk)",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Add canonical URL tag to indicate preferred version",
            )]
        
        return [self._create_result(
            passed=True,
            message="Canonical URL present (duplicate content risk mitigated)",
            severity=Severity.PASSED,
            score_impact=0,
            data={"canonical_url": canonical},
        )]


class ContentFreshnessRule(BaseRule):
    """Check content freshness indicators."""
    rule_id = "content_007"
    name = "Content Freshness"
    category = "content"
    description = "Check for content freshness signals"
    weight = 0.6
    tags = ["info", "content", "freshness"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        
        # Check for last-modified, published dates, etc.
        has_date_meta = bool(basic.get("article_published_time") or 
                            basic.get("article_modified_time") or
                            basic.get("date"))
        
        if not has_date_meta:
            return [self._create_result(
                passed=False,
                message="No content freshness dates found",
                severity=Severity.INFO,
                score_impact=-1,
                recommendation="Consider adding article published/modified dates",
            )]
        
        return [self._create_result(
            passed=True,
            message="Content freshness dates present",
            severity=Severity.PASSED,
            score_impact=0,
        )]