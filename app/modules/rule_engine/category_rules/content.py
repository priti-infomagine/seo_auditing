"""
Content Quality Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


class WordCountRule(BaseRule):
    """Check content length with context-aware thresholds."""
    rule_id = "content_001"
    name = "Word Count"
    category = "content"
    description = "Page should have sufficient content for its purpose"
    weight = 1.2
    tags = ["critical", "content", "quality"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        content = data.get("content", {})
        word_count = content.get("word_count", 0)
        page_type = data.get("page_type", "")
        
        if word_count == 0:
            return [self._create_result(
                passed=False,
                message="No content found on page",
                severity=Severity.CRITICAL,
                score_impact=-15,
                recommendation="Add substantial content to the page",
            )]
        
        # Context-aware thresholds
        if page_type in ("product_page", "category_page", "ecommerce"):
            thresholds = {"thin": 50, "acceptable": 150, "good": 300, "excellent": 500}
        else:
            thresholds = {"thin": 150, "acceptable": 300, "good": 800, "excellent": 1500}
        
        details = {"word_count": word_count, "page_type": page_type or "unknown"}
        
        if word_count < thresholds["thin"]:
            return [self._create_result(
                passed=False,
                message=f"Thin content: {word_count} words (recommended: {thresholds['thin']}+ for {page_type or 'standard'} pages)",
                severity=Severity.WARNING,
                score_impact=-8,
                recommendation=f"Increase content to at least {thresholds['thin']} words",
                data=details,
            )]
        
        if word_count < thresholds["acceptable"]:
            return [self._create_result(
                passed=True,
                message=f"Acceptable content length: {word_count} words",
                severity=Severity.PASSED,
                score_impact=0,
                data=details,
            )]
        
        if word_count >= thresholds["excellent"]:
            return [self._create_result(
                passed=True,
                message=f"Excellent content length: {word_count} words",
                severity=Severity.PASSED,
                score_impact=2,
                data=details,
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Good content length: {word_count} words",
            severity=Severity.PASSED,
            score_impact=0,
            data=details,
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
        target_keyword = data.get("target_keyword") or data.get("keyword")
        if not target_keyword:
            return [self._create_result(
                passed=True,
                message="Keyword presence check skipped (no target keyword specified)",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        basic = data.get("basic", {})
        title = basic.get("title", "")
        meta_description = basic.get("meta_description", "")
        headings = data.get("headings", {})
        h1_tags = headings.get("h1", [])
        h2_tags = headings.get("h2", [])
        content = data.get("content", {})
        content_text = content.get("text", "") or content.get("normalized_text", "")
        url_info = data.get("url", {})
        url_path = url_info.get("path", "")
        
        keyword_lower = target_keyword.lower()
        locations = []
        impacts = 0
        
        # Title check
        if keyword_lower in title.lower():
            locations.append("title")
        else:
            impacts -= 1
        
        # H1 check
        h1_text = " ".join(h1_tags).lower()
        if keyword_lower in h1_text:
            locations.append("h1")
        else:
            impacts -= 1
        
        # URL check
        if keyword_lower in url_path.lower():
            locations.append("url")
        
        # Meta description check
        if keyword_lower in meta_description.lower():
            locations.append("meta_description")
        
        # Introduction (first 100 words)
        intro = " ".join(content_text.split()[:100]).lower()
        if keyword_lower in intro:
            locations.append("introduction")
        else:
            impacts -= 1
        
        # Body (full content)
        if keyword_lower in content_text.lower():
            locations.append("body")
        
        # Headings (H2-H6)
        all_headings = " ".join(h2_tags).lower()
        if keyword_lower in all_headings:
            locations.append("headings")
        
        # Density (informational only)
        word_count = len(content_text.split()) if content_text else 0
        density = 0.0
        if word_count > 0:
            density = content_text.lower().count(keyword_lower) / word_count
        
        details = {
            "keyword": target_keyword,
            "found_in": locations,
            "density": round(density, 4),
            "locations_count": len(locations),
        }
        
        if len(locations) >= 4:
            return [self._create_result(
                passed=True,
                message=f"Keyword '{target_keyword}' present in {len(locations)} locations (title, H1, intro, body, etc.)",
                severity=Severity.PASSED,
                score_impact=0,
                data=details,
            )]
        
        if len(locations) >= 2:
            return [self._create_result(
                passed=False,
                message=f"Keyword '{target_keyword}' found in {len(locations)} locations: {', '.join(locations)}",
                severity=Severity.WARNING,
                score_impact=impacts,
                recommendation=f"Include '{target_keyword}' in title, H1, introduction, and body",
                data=details,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Keyword '{target_keyword}' rarely found (only in: {', '.join(locations) or 'nowhere'})",
            severity=Severity.WARNING,
            score_impact=impacts,
            recommendation=f"Include '{target_keyword}' naturally in title, H1, introduction, and body content",
            data=details,
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
        content_hash = seo.get("content_hash", "")
        duplicate_group_size = seo.get("duplicate_group_size", 0)
        
        issues = []
        impacts = 0
        details = {"canonical_url": canonical}
        
        # Canonical check
        if not canonical:
            issues.append("No canonical URL")
            impacts -= 2
        
        # Exact duplicate detection
        if duplicate_group_size and duplicate_group_size > 1:
            issues.append(f"Exact duplicate of {duplicate_group_size} pages")
            impacts -= 5
            details["duplicate_group_size"] = duplicate_group_size
        
        if content_hash and not canonical:
            issues.append("Content hash present but no canonical")
            impacts -= 1
        
        if not issues:
            return [self._create_result(
                passed=True,
                message="No duplicate content issues detected",
                severity=Severity.PASSED,
                score_impact=0,
                data=details,
            )]
        
        severity = Severity.WARNING if impacts > -6 else Severity.CRITICAL
        return [self._create_result(
            passed=False,
            message=f"Duplicate content risk: {', '.join(issues)}",
            severity=severity,
            score_impact=impacts,
            recommendation="Add canonical URL tag and ensure unique content",
            data=details,
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


class DuplicateTitlesRule(BaseRule):
    """Check for duplicate page titles across the site."""
    rule_id = "duplicate_001"
    name = "Duplicate Titles"
    category = "content"
    description = "Pages should have unique title tags"
    weight = 1.0
    tags = ["warning", "content", "duplicate"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        seo = data.get("seo", {})
        title = seo.get("title", "")
        duplicate_titles = seo.get("duplicate_titles", [])
        
        if not title:
            return [self._create_result(
                passed=True,
                message="No title to check for duplicates",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if title in duplicate_titles:
            return [self._create_result(
                passed=False,
                message=f"Duplicate title found ({len(duplicate_titles)} pages share this title)",
                severity=Severity.INFO,
                score_impact=-3,
                recommendation="Make title tags unique across the site",
                data={"title": title, "duplicate_count": len(duplicate_titles)},
            )]
        
        return [self._create_result(
            passed=True,
            message="Title is unique",
            severity=Severity.PASSED,
            score_impact=0,
            data={"title": title},
        )]


class DuplicateDescriptionsRule(BaseRule):
    """Check for duplicate meta descriptions across the site."""
    rule_id = "duplicate_002"
    name = "Duplicate Descriptions"
    category = "content"
    description = "Pages should have unique meta descriptions"
    weight = 1.0
    tags = ["warning", "content", "duplicate"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        seo = data.get("seo", {})
        meta_description = seo.get("meta_description", "")
        duplicate_descriptions = seo.get("duplicate_descriptions", [])
        
        if not meta_description:
            return [self._create_result(
                passed=True,
                message="No meta description to check for duplicates",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if meta_description in duplicate_descriptions:
            return [self._create_result(
                passed=False,
                message=f"Duplicate meta description found ({len(duplicate_descriptions)} pages share this description)",
                severity=Severity.INFO,
                score_impact=-3,
                recommendation="Make meta descriptions unique across the site",
                data={"meta_description": meta_description, "duplicate_count": len(duplicate_descriptions)},
            )]
        
        return [self._create_result(
            passed=True,
            message="Meta description is unique",
            severity=Severity.PASSED,
            score_impact=0,
            data={"meta_description": meta_description},
        )]


class DuplicateH1sRule(BaseRule):
    """Check for duplicate H1 tags across the site."""
    rule_id = "duplicate_003"
    name = "Duplicate H1s"
    category = "content"
    description = "Pages should have unique H1 tags"
    weight = 1.0
    tags = ["warning", "content", "duplicate"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        headings = data.get("headings", {})
        h1_tags = headings.get("h1", [])
        duplicate_h1s = data.get("duplicate_h1s", [])
        
        if not h1_tags:
            return [self._create_result(
                passed=True,
                message="No H1 to check for duplicates",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        h1_text = h1_tags[0] if h1_tags else ""
        if h1_text in duplicate_h1s:
            return [self._create_result(
                passed=False,
                message=f"Duplicate H1 found ({len(duplicate_h1s)} pages share this H1)",
                severity=Severity.INFO,
                score_impact=-3,
                recommendation="Make H1 tags unique across the site",
                data={"h1": h1_text, "duplicate_count": len(duplicate_h1s)},
            )]
        
        return [self._create_result(
            passed=True,
            message="H1 is unique",
            severity=Severity.PASSED,
            score_impact=0,
            data={"h1": h1_text},
        )]