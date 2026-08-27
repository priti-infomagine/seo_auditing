"""
On-Page SEO Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity

from typing import Any, Dict, List
import re


class TitleTagRule(BaseRule):
    """Check title tag presence, length, pixel width, uniqueness, and relevance."""

    rule_id = "on_page_001"
    name = "Title Tag"
    category = "on_page"
    description = (
        "Page must have a descriptive, relevant title tag. "
        "Length and pixel width are optimization signals, not hard SEO requirements."
    )
    weight = 1.5
    tags = ["on_page", "title"]

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    MIN_GOOD_LENGTH = 30
    RECOMMENDED_MIN_LENGTH = 50
    RECOMMENDED_MAX_LENGTH = 60
    LONG_TITLE_LENGTH = 70

    # Approximate only. Do not treat this as a hard Google requirement.
    MAX_ESTIMATED_PIXEL_WIDTH = 600

    # Titles that are clearly non-descriptive.
    GENERIC_TITLES = {
        "welcome",
        "home",
        "untitled",
        "page",
        "index",
        "new page",
        "default",
        "homepage",
        "main page",
    }

    # Very common words that shouldn't be heavily weighted
    # when checking title/content consistency.
    STOP_WORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "vs",
        "with",
        "your",
        "you",
        "this",
        "that",
        "what",
        "why",
        "when",
        "where",
        "which",
        "can",
        "will",
        "into",
        "using",
        "about",
    }

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {}) or {}
        content = data.get("content", {}) or {}

        title = (basic.get("title") or "").strip()

        title_length = basic.get("title_length")

        if title_length is None:
            title_length = len(title)

        try:
            title_length = int(title_length)
        except (TypeError, ValueError):
            title_length = len(title)

        content_text = (
            content.get("text")
            or content.get("normalized_text")
            or ""
        )

        content_text = str(content_text).strip()

        details: Dict[str, Any] = {
            "title": title,
            "character_count": title_length,
        }

        # ==============================================================
        # 1. Missing title
        # ==============================================================

        if not title:
            return [
                self._create_result(
                    passed=False,
                    message="Missing page title tag",
                    severity=Severity.WARNING,
                    score_impact=-8,
                    recommendation=(
                        "Add a unique, descriptive <title> tag that clearly "
                        "describes the page content and search intent."
                    ),
                    data={
                        **details,
                        "length_status": "missing",
                    },
                )
            ]

        # ==============================================================
        # 2. Pixel width estimation
        # ==============================================================

        pixel_width = self._estimate_pixel_width(title)

        details["pixel_width_estimate"] = pixel_width

        if pixel_width > self.MAX_ESTIMATED_PIXEL_WIDTH:
            details["truncation_risk"] = True
        else:
            details["truncation_risk"] = False

        # ==============================================================
        # 3. Length analysis
        #
        # IMPORTANT:
        # Character length is an optimization signal, NOT a hard SEO
        # requirement.
        # ==============================================================

        length_status = "good"

        if title_length < 30:
            length_status = "very_short"

        elif title_length < self.RECOMMENDED_MIN_LENGTH:
            length_status = "short"

        elif title_length <= self.RECOMMENDED_MAX_LENGTH:
            length_status = "recommended"

        elif title_length <= self.LONG_TITLE_LENGTH:
            length_status = "long"

        else:
            length_status = "very_long"

        details["length_status"] = length_status

        # ==============================================================
        # 4. Generic title
        # ==============================================================

        normalized_title = self._normalize_text(title)

        is_generic = normalized_title in self.GENERIC_TITLES

        details["generic"] = is_generic

        # ==============================================================
        # 5. Target keyword/topic check
        #
        # Keyword absence is NOT automatically an SEO failure.
        # It is only treated as a quality signal when target keyword
        # information is explicitly available.
        # ==============================================================

        target_keyword = (
            data.get("target_keyword")
            or data.get("keyword")
        )

        target_keyword = (
            str(target_keyword).strip()
            if target_keyword
            else ""
        )

        keyword_present = None

        if target_keyword:
            keyword_present = self._keyword_is_present(
                target_keyword,
                title
            )

            details["target_keyword"] = target_keyword
            details["keyword_present"] = keyword_present

        # ==============================================================
        # 6. Title/content relevance
        # ==============================================================

        consistency_score = None

        if content_text and len(content_text) > 50:
            consistency_score = self._calculate_content_consistency(
                title,
                content_text
            )

            details["content_consistency_score"] = consistency_score

        # ==============================================================
        # 7. Build actual issues
        # ==============================================================

        issues: List[str] = []

        # Generic title is a real quality problem.
        if is_generic:
            issues.append("generic title")

        # Very short titles are worth flagging.
        if length_status == "very_short":
            issues.append("very short")

        # Long titles are advisory.
        elif length_status == "very_long":
            issues.append("very long")

        elif length_status == "long":
            issues.append("slightly long")

        # Pixel width is advisory, not a major SEO failure.
        if pixel_width > self.MAX_ESTIMATED_PIXEL_WIDTH:
            issues.append("possible SERP truncation")

        # Keyword absence is a minor quality signal only.
        if target_keyword and keyword_present is False:
            issues.append("target topic not clearly reflected in title")

        # Only flag strong content mismatch.
        if (
            consistency_score is not None
            and consistency_score < 0.20
        ):
            issues.append("title may not describe page content")

        # ==============================================================
        # 8. Determine severity
        #
        # Do NOT calculate severity by adding all minor penalties.
        # A long title + truncation + keyword absence should not suddenly
        # become CRITICAL.
        # ==============================================================

        severity = Severity.PASSED
        score_impact = 0
        passed = True

        # --------------------------------------------------------------
        # High
        # --------------------------------------------------------------

        if is_generic:
            passed = False
            severity = Severity.WARNING
            score_impact = -4

        # Strong content mismatch.
        elif (
            consistency_score is not None
            and consistency_score < 0.20
        ):
            passed = False
            severity = Severity.WARNING
            score_impact = -3

        # --------------------------------------------------------------
        # Low
        # --------------------------------------------------------------

        elif length_status in {"very_short", "very_long"}:
            passed = False
            severity = Severity.INFO
            score_impact = -2

        elif length_status == "long":
            passed = False
            severity = Severity.INFO
            score_impact = -1

        elif pixel_width > self.MAX_ESTIMATED_PIXEL_WIDTH:
            passed = False
            severity = Severity.INFO
            score_impact = -1

        elif target_keyword and keyword_present is False:
            passed = False
            severity = Severity.INFO
            score_impact = -1

        # ==============================================================
        # 9. PASS
        # ==============================================================

        if passed:
            message = (
                f"Title is descriptive and acceptable "
                f"({title_length} characters, ~{pixel_width}px)"
            )

            return [
                self._create_result(
                    passed=True,
                    message=message,
                    severity=Severity.PASSED,
                    score_impact=0,
                    recommendation=(
                        "No action required. Continue using unique, "
                        "descriptive titles that accurately represent "
                        "each page."
                    ),
                    data=details,
                )
            ]

        # ==============================================================
        # 10. Generate recommendation
        # ==============================================================

        recommendation = self._build_recommendation(
            issues=issues,
            title_length=title_length,
            pixel_width=pixel_width,
            target_keyword=target_keyword,
        )

        # Remove empty/duplicate issue names.
        clean_issues = list(dict.fromkeys(issues))

        message = (
            f"Title issues: {', '.join(clean_issues)}"
            if clean_issues
            else "Title needs optimization"
        )

        return [
            self._create_result(
                passed=False,
                message=message,
                severity=severity,
                score_impact=score_impact,
                recommendation=recommendation,
                data=details,
            )
        ]

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for comparisons."""

        text = text.lower().strip()

        # Replace punctuation/separators with spaces.
        text = re.sub(r"[^\w\s]", " ", text)

        # Collapse whitespace.
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    @classmethod
    def _keyword_is_present(
        cls,
        keyword: str,
        title: str,
    ) -> bool:
        """
        Check whether the target topic is reasonably represented.

        Supports both exact phrase and token-level matching.
        This is intentionally more flexible than:
            keyword.lower() in title.lower()
        """

        keyword_normalized = cls._normalize_text(keyword)
        title_normalized = cls._normalize_text(title)

        if not keyword_normalized:
            return True

        # Exact phrase.
        if keyword_normalized in title_normalized:
            return True

        keyword_words = [
            word
            for word in keyword_normalized.split()
            if word not in cls.STOP_WORDS
        ]

        title_words = set(title_normalized.split())

        if not keyword_words:
            return True

        matches = sum(
            1
            for word in keyword_words
            if word in title_words
        )

        # Require most meaningful words rather than exact phrase.
        match_ratio = matches / len(keyword_words)

        return match_ratio >= 0.70

    @classmethod
    def _calculate_content_consistency(
        cls,
        title: str,
        content: str,
    ) -> float:
        """
        Estimate whether meaningful title words appear in the content.

        This is deliberately a lightweight heuristic. It should not be
        treated as semantic similarity or an NLP relevance score.
        """

        title_words = cls._meaningful_words(title)

        if not title_words:
            return 1.0

        content_normalized = cls._normalize_text(content)

        if not content_normalized:
            return 0.0

        content_words = set(content_normalized.split())

        matches = sum(
            1
            for word in title_words
            if word in content_words
        )

        return matches / len(title_words)

    @classmethod
    def _meaningful_words(cls, text: str) -> List[str]:
        """Return meaningful normalized words from text."""

        normalized = cls._normalize_text(text)

        words = normalized.split()

        return [
            word
            for word in words
            if (
                word not in cls.STOP_WORDS
                and len(word) >= 3
                and not word.isdigit()
            )
        ]

    @staticmethod
    def _estimate_pixel_width(text: str) -> int:
        """
        Estimate title pixel width.

        This is only a heuristic. Actual SERP rendering depends on font,
        glyph widths, device/layout, and Google's rendering.

        Weighted character widths are used instead of a fixed
        `len(text) * 6.5` calculation.
        """

        if not text:
            return 0

        width = 0.0

        # Approximate relative widths.
        narrow_chars = set(
            "iIl1.,'`!:;| "
        )

        wide_chars = set(
            "MW@%&QO"
        )

        medium_wide_chars = set(
            "ABCDEFGHKNPRSTUVXYZ"
        )

        for char in text:
            if char in narrow_chars:
                width += 3.5

            elif char in wide_chars:
                width += 9.5

            elif char in medium_wide_chars:
                width += 7.5

            elif char.isdigit():
                width += 6.5

            else:
                width += 6.5

        return int(round(width))

    @staticmethod
    def _build_recommendation(
        issues: List[str],
        title_length: int,
        pixel_width: int,
        target_keyword: str = "",
    ) -> str:
        """Generate a recommendation based on actual issues."""

        recommendations: List[str] = []

        if "generic title" in issues:
            recommendations.append(
                "Replace the generic title with a unique, descriptive "
                "title that clearly identifies the page."
            )

        if "title may not describe page content" in issues:
            recommendations.append(
                "Rewrite the title so it accurately reflects the main "
                "topic and search intent of the page."
            )

        if "very short" in issues:
            recommendations.append(
                "Consider making the title more descriptive. "
                "Do not add filler simply to reach a character count."
            )

        if "slightly long" in issues:
            recommendations.append(
                "Consider shortening the title to make the main topic "
                "clearer and reduce the possibility of SERP truncation."
            )

        if "very long" in issues:
            recommendations.append(
                "Shorten the title substantially and place the most "
                "important topic information toward the beginning."
            )

        if "possible SERP truncation" in issues:
            recommendations.append(
                f"The estimated title width is ~{pixel_width}px. "
                "Consider shortening it if important information appears "
                "near the end."
            )

        if "target topic not clearly reflected in title" in issues:
            recommendations.append(
                "Ensure the title clearly communicates the page's primary "
                "topic or search intent."
            )

        if not recommendations:
            recommendations.append(
                "Use a unique, descriptive title that accurately represents "
                "the page content."
            )

        return " ".join(recommendations)
    
    
# class TitleTagRule(BaseRule):
#     """Check title tag presence, length, pixel width, and quality."""
#     rule_id = "on_page_001"
#     name = "Title Tag"
#     category = "on_page"
#     description = "Page must have a descriptive title tag with optimal length and pixel width"
#     weight = 1.5
#     tags = ["critical", "on_page", "title"]
    
#     async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
#         basic = data.get("basic", {})
#         title = basic.get("title", "")
#         title_length = basic.get("title_length", len(title) if title else 0)
#         content = data.get("content", {})
#         content_text = content.get("text", "") or content.get("normalized_text", "")
        
#         if not title or not title.strip():
#             return [self._create_result(
#                 passed=False,
#                 message="Missing page title tag",
#                 severity=Severity.CRITICAL,
#                 score_impact=-15,
#                 recommendation="Add a descriptive <title> tag (50-60 characters, include primary keyword)",
#             )]
        
#         pixel_width = self._estimate_pixel_width(title)
#         issues = []
#         impacts = 0
#         details = {
#             "title": title,
#             "character_count": title_length,
#             "pixel_width_estimate": pixel_width,
#         }
        
#         # Length checks
#         if title_length < 30:
#             issues.append("too short")
#             impacts -= 3
#         elif title_length <= 49:
#             issues.append("acceptable length")
#         elif title_length <= 60:
#             issues.append("ideal length")
#             details["length_status"] = "ideal"
#         elif title_length <= 70:
#             issues.append("slightly long")
#             impacts -= 3
#         else:
#             issues.append("too long")
#             impacts -= 5
        
#         # Pixel width check (takes precedence for truncation risk)
#         if pixel_width > 600:
#             issues.append("likely truncated in SERP")
#             impacts -= 3
#             details["truncation_risk"] = True
        
#         # Generic title check
#         generic_titles = ["welcome", "home", "untitled", "page", "index", "new page", "default"]
#         if title.lower().strip() in generic_titles:
#             issues.append("generic title")
#             impacts -= 3
#             details["generic"] = True
        
#         # Keyword/topic presence (if keyword data available)
#         target_keyword = data.get("target_keyword") or data.get("keyword")
#         if target_keyword:
#             keyword_present = target_keyword.lower() in title.lower()
#             details["keyword_present"] = keyword_present
#             if not keyword_present:
#                 issues.append("missing target keyword")
#                 impacts -= 2
        
#         # Title/content consistency
#         if content_text and len(content_text) > 50:
#             title_words = title.lower().split()[:5]
#             content_lower = content_text.lower()
#             consistency_hits = sum(1 for w in title_words if w in content_lower)
#             details["content_consistency_score"] = consistency_hits / len(title_words) if title_words else 0
#             if consistency_hits == 0:
#                 issues.append("title may not describe content")
#                 impacts -= 2
        
#         if not issues or (len(issues) == 1 and "acceptable length" in issues):
#             msg = f"Title length is optimal ({title_length} characters, ~{pixel_width}px)"
#             return [self._create_result(
#                 passed=True,
#                 message=msg,
#                 severity=Severity.PASSED,
#                 score_impact=0,
#                 data=details,
#             )]
        
#         severity = Severity.WARNING if impacts > -8 else Severity.CRITICAL
#         msg = f"Title issues: {', '.join(i for i in issues if i not in ('acceptable length',))}"
#         if title_length >= 50 and title_length <= 60:
#             msg = f"Title length is optimal ({title_length} characters), but: {', '.join(i for i in issues if i not in ('acceptable length', 'ideal length'))}"
        
#         return [self._create_result(
#             passed=False,
#             message=msg,
#             severity=severity,
#             score_impact=impacts,
#             recommendation="Adjust title: 50-60 characters, include primary keyword, avoid truncation",
#             data=details,
#         )]
    
#     @staticmethod
#     def _estimate_pixel_width(text: str) -> int:
#         """Estimate pixel width of title for SERP display.
        
#         Uses proportional font heuristic (~6.5px average per character).
#         Google desktop SERP typically allows ~580-600px for titles.
#         """
#         if not text:
#             return 0
#         return int(len(text) * 6.5)


class MetaDescriptionRule(BaseRule):
    """Check meta description presence, length, pixel width, and quality."""
    rule_id = "on_page_002"
    name = "Meta Description"
    category = "on_page"
    description = "Page must have meta description with optimal length (140-160 chars)"
    weight = 1.2
    tags = ["critical", "on_page", "meta"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        meta_desc = basic.get("meta_description", "")
        meta_desc_length = basic.get("meta_description_length", len(meta_desc) if meta_desc else 0)
        
        if not meta_desc or not meta_desc.strip():
            return [self._create_result(
                passed=False,
                message="Missing meta description",
                severity=Severity.WARNING,
                score_impact=-12,
                recommendation="Add a compelling meta description (140-160 characters)",
            )]
        
        pixel_width = self._estimate_pixel_width(meta_desc)
        impacts = 0
        details = {
            "meta_description": meta_desc,
            "character_count": meta_desc_length,
            "pixel_width_estimate": pixel_width,
        }
        
        if meta_desc_length < 70:
            impacts -= 3
            details["length_status"] = "too_short"
        elif meta_desc_length <= 139:
            impacts -= 1
            details["length_status"] = "acceptable"
        elif meta_desc_length <= 160:
            impacts += 0
            details["length_status"] = "preferred"
        elif meta_desc_length <= 180:
            impacts -= 2
            details["length_status"] = "slightly_long"
        else:
            impacts -= 4
            details["length_status"] = "too_long"
        
        if pixel_width > 920:
            impacts -= 2
            details["truncation_risk"] = True
        
        target_keyword = data.get("target_keyword") or data.get("keyword")
        if target_keyword:
            keyword_present = target_keyword.lower() in meta_desc.lower()
            details["keyword_present"] = keyword_present
            if not keyword_present:
                impacts -= 1
        
        if meta_desc_length >= 140 and meta_desc_length <= 160:
            return [self._create_result(
                passed=True,
                message=f"Meta description length is optimal ({meta_desc_length} characters, ~{pixel_width}px)",
                severity=Severity.PASSED,
                score_impact=0,
                data=details,
            )]
        
        severity = Severity.WARNING if impacts > -6 else Severity.CRITICAL
        return [self._create_result(
            passed=False,
            message=f"Meta description length is {meta_desc_length} characters (recommended: 140-160)",
            severity=severity,
            score_impact=impacts,
            recommendation="Adjust meta description to 140-160 characters for optimal SERP display",
            data=details,
        )]
    
    @staticmethod
    def _estimate_pixel_width(text: str) -> int:
        if not text:
            return 0
        return int(len(text) * 6.5)


class H1TagRule(BaseRule):
    """Check H1 tag presence, count, length, and quality."""
    rule_id = "on_page_003"
    name = "H1 Tag"
    category = "on_page"
    description = "Page should have exactly one non-empty H1 tag"
    weight = 1.3
    tags = ["critical", "on_page", "headings"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        headings = data.get("headings", {})
        h1_tags = headings.get("h1", [])
        h1_count = len(h1_tags) if h1_tags else 0
        basic = data.get("basic", {})
        title = basic.get("title", "")
        
        if h1_count == 0:
            return [self._create_result(
                passed=False,
                message="Missing H1 tag",
                severity=Severity.CRITICAL,
                score_impact=-10,
                recommendation="Add a single <h1> tag containing your primary keyword",
            )]
        
        # Check for empty H1s
        empty_h1s = sum(1 for h in h1_tags if not h or not h.strip())
        if empty_h1s > 0:
            return [self._create_result(
                passed=False,
                message=f"Found {h1_count} H1 tags, including {empty_h1s} empty",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Ensure H1 tags contain descriptive text",
                data={"h1_count": h1_count, "empty_h1s": empty_h1s, "h1_tags": h1_tags[:3]},
            )]
        
        if h1_count > 1:
            return [self._create_result(
                passed=False,
                message=f"Multiple H1 tags found ({h1_count})",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Use only one H1 tag per page for better SEO",
                data={"h1_count": h1_count, "h1_tags": h1_tags[:3]},
            )]
        
        h1_text = h1_tags[0] if h1_tags else ""
        h1_length = len(h1_text)
        impacts = 0
        details = {"h1_count": 1, "h1_text": h1_text, "h1_length": h1_length}
        
        # Length check
        if h1_length > 100:
            impacts -= 2
            details["length_warning"] = True
        
        # H1/title consistency
        if title and h1_text:
            title_words = set(title.lower().split()[:5])
            h1_words = set(h1_text.lower().split()[:5])
            overlap = title_words & h1_words
            details["title_h1_overlap"] = len(overlap) / len(title_words) if title_words else 0
            if len(overlap) == 0:
                impacts -= 1
                details["consistency_warning"] = True
        
        if impacts == 0:
            return [self._create_result(
                passed=True,
                message="Has exactly one H1 tag",
                severity=Severity.PASSED,
                score_impact=0,
                data=details,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"H1 tag issues detected (length={h1_length}, consistency issues)",
            severity=Severity.WARNING,
            score_impact=impacts,
            recommendation="Use one concise H1 tag that aligns with the page title",
            data=details,
        )]


class HeadingHierarchyRule(BaseRule):
    """Check heading hierarchy (H1 → H2 → H3)."""
    rule_id = "on_page_004"
    name = "Heading Hierarchy"
    category = "on_page"
    description = "Headings should follow logical hierarchy"
    weight = 1.0
    tags = ["warning", "on_page", "headings"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        headings = data.get("headings", {})
        heading_stats = headings.get("heading_stats", {})
        
        h1_count = len(headings.get("h1", []))
        h2_count = len(headings.get("h2", []))
        h3_count = len(headings.get("h3", []))
        h4_count = len(headings.get("h4", []))
        h5_count = len(headings.get("h5", []))
        h6_count = len(headings.get("h6", []))
        total_headings = heading_stats.get("heading_count", h1_count + h2_count + h3_count + h4_count + h5_count + h6_count)
        
        issues = []
        impacts = 0
        
        if h1_count == 0:
            issues.append("Missing H1")
            impacts -= 3
        
        if h2_count == 0 and h3_count > 0:
            issues.append("H3 used without H2")
            impacts -= 2
        
        if not heading_stats.get("is_sequential", True):
            issues.append("Heading levels are not sequential")
            impacts -= 2
        
        # Excessive headings
        if total_headings > 20:
            issues.append("Excessive headings")
            impacts -= 2
        elif h2_count > 10:
            issues.append("Too many H2 headings")
            impacts -= 1
        
        # Empty headings
        all_headings = []
        for level in range(1, 7):
            all_headings.extend(headings.get(f"h{level}", []))
        empty_headings = sum(1 for h in all_headings if not h or not h.strip())
        if empty_headings > 0:
            issues.append(f"{empty_headings} empty headings")
            impacts -= 1
        
        # Duplicate headings
        seen = set()
        duplicates = 0
        for h in all_headings:
            h_norm = h.strip().lower()
            if h_norm in seen:
                duplicates += 1
            seen.add(h_norm)
        if duplicates > 0:
            issues.append(f"{duplicates} duplicate headings")
            impacts -= 1
        
        # Heading length warnings
        long_headings = sum(1 for h in all_headings if len(h) > 100)
        if long_headings > 0:
            issues.append(f"{long_headings} headings longer than 100 characters")
            impacts -= 1
        
        if not issues:
            return [self._create_result(
                passed=True,
                message="Heading hierarchy is logical",
                severity=Severity.PASSED,
                score_impact=0,
                data={"h1": h1_count, "h2": h2_count, "h3": h3_count, "h4": h4_count, "h5": h5_count, "h6": h6_count, "total": total_headings},
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Heading hierarchy issues: H1={h1_count}, H2={h2_count}, H3={h3_count}, H4={h4_count}, H5={h5_count}, H6={h6_count} — {', '.join(issues)}",
            severity=Severity.WARNING,
            score_impact=impacts,
            recommendation="Organize headings in logical hierarchy (H1 → H2 → H3)",
            data={"h1": h1_count, "h2": h2_count, "h3": h3_count, "h4": h4_count, "h5": h5_count, "h6": h6_count, "issues": issues, "total": total_headings},
        )]


class MetaKeywordsRule(BaseRule):
    """Check meta keywords (less important but still checked)."""
    rule_id = "on_page_005"
    name = "Meta Keywords"
    category = "on_page"
    description = "Check for meta keywords tag"
    weight = 0.5
    tags = ["info", "on_page", "meta"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        basic = data.get("basic", {})
        meta_keywords = basic.get("meta_keywords", [])
        
        if meta_keywords:
            return [self._create_result(
                passed=True,
                message=f"Meta keywords present ({len(meta_keywords)} keywords)",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=True,
            message="Meta keywords not present (not critical for modern SEO)",
            severity=Severity.INFO,
            score_impact=0,
            recommendation="Meta keywords are deprecated but can be added if desired",
        )]


class CanonicalUrlRule(BaseRule):
    """Check canonical URL tag."""
    rule_id = "on_page_006"
    name = "Canonical URL"
    category = "on_page"
    description = "Page should have canonical URL to avoid duplicate content"
    weight = 1.1
    tags = ["critical", "on_page", "duplicate_content"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        seo = data.get("seo", {})
        canonical = seo.get("canonical_url", "")
        url_info = data.get("url", {})
        current_url = url_info.get("url", "") or url_info.get("normalized_url", "")
        
        if not canonical:
            return [self._create_result(
                passed=False,
                message="Missing canonical URL tag",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add <link rel='canonical' href='...'> to prevent duplicate content issues",
            )]
        
        impacts = 0
        details = {"canonical_url": canonical}
        
        # Check if canonical is absolute
        if canonical.startswith("//") or (not canonical.startswith("http") and "//" not in canonical):
            impacts -= 2
            details["relative_canonical"] = True
        
        # Check self-referencing canonical
        if canonical == current_url:
            details["self_referencing"] = True
        
        # Check for common issues
        if "noindex" in canonical.lower():
            impacts -= 3
            details["noindex_in_canonical"] = True
        
        if impacts == 0:
            return [self._create_result(
                passed=True,
                message=f"Canonical URL is set: {canonical}",
                severity=Severity.PASSED,
                score_impact=0,
                data=details,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Canonical URL has issues: {canonical}",
            severity=Severity.WARNING,
            score_impact=impacts,
            recommendation="Ensure canonical URL is absolute and points to the preferred version",
            data=details,
        )]


class RobotsMetaRule(BaseRule):
    """Check robots meta tag."""
    rule_id = "on_page_007"
    name = "Robots Meta Tag"
    category = "on_page"
    description = "Check robots meta directives"
    weight = 1.0
    tags = ["warning", "on_page", "indexing"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        seo = data.get("seo", {})
        robots_meta = seo.get("robots_meta", "")
        x_robots = seo.get("x_robots_tag", "")
        
        robots_value = robots_meta or x_robots
        
        if not robots_value:
            return [self._create_result(
                passed=True,
                message="No robots restrictions (page will be indexed)",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        robots_lower = robots_value.lower()
        if "noindex" in robots_lower:
            return [self._create_result(
                passed=False,
                message=f"Page is set to noindex: {robots_value}",
                severity=Severity.CRITICAL,
                score_impact=-20,
                recommendation="Remove noindex directive if page should be indexed",
                data={"robots_meta": robots_meta, "x_robots_tag": x_robots},
            )]
        
        if "nofollow" in robots_lower:
            return [self._create_result(
                passed=False,
                message=f"Links will not be followed: {robots_value}",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Remove nofollow if links should be crawled",
                data={"robots_meta": robots_meta, "x_robots_tag": x_robots},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Robots meta: {robots_value}",
            severity=Severity.PASSED,
            score_impact=0,
            data={"robots_meta": robots_meta, "x_robots_tag": x_robots},
        )]


class OpenGraphRule(BaseRule):
    """Check Open Graph tags for social sharing."""
    rule_id = "on_page_008"
    name = "Open Graph Tags"
    category = "on_page"
    description = "Check for Open Graph meta tags"
    weight = 0.8
    tags = ["info", "on_page", "social"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        og = social.get("open_graph", {})
        og_tags = og.get("tags", {})
        
        required = ["og:title", "og:description", "og:image", "og:url"]
        missing = [tag for tag in required if tag not in og_tags]
        
        if not missing:
            return [self._create_result(
                passed=True,
                message=f"All required Open Graph tags present ({len(og_tags)} total)",
                severity=Severity.PASSED,
                score_impact=0,
                data={"og_tags": list(og_tags.keys())},
            )]
        
        impact = -len(missing) * 2
        return [self._create_result(
            passed=False,
            message=f"Missing Open Graph tags: {', '.join(missing)}",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation=f"Add missing OG tags: {', '.join(missing)}",
            data={"missing": missing, "present": list(og_tags.keys())},
        )]


class TwitterCardsRule(BaseRule):
    """Check Twitter Card tags."""
    rule_id = "on_page_009"
    name = "Twitter Cards"
    category = "on_page"
    description = "Check for Twitter Card meta tags"
    weight = 0.6
    tags = ["info", "on_page", "social"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        social = data.get("social", {})
        twitter = social.get("twitter_cards", {})
        twitter_tags = twitter.get("tags", {})
        
        if not twitter_tags:
            return [self._create_result(
                passed=True,
                message="No Twitter Card tags (optional)",
                severity=Severity.INFO,
                score_impact=0,
                recommendation="Consider adding Twitter Card tags for better social sharing",
            )]
        
        required = ["twitter:card", "twitter:title", "twitter:description"]
        missing = [tag for tag in required if tag not in twitter_tags]
        
        if not missing:
            return [self._create_result(
                passed=True,
                message="Twitter Card tags present",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"Incomplete Twitter Card tags. Missing: {', '.join(missing)}",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation=f"Add missing Twitter tags: {', '.join(missing)}",
        )]