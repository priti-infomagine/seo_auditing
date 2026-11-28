"""
HTML Validation Rules.

Validates HTML structural correctness, DOCTYPE, charset, head elements,
and common placeholder content detection.
"""
from typing import Any, Dict, List
import re

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


class SingleTitleElementRule(BaseRule):
    """HTML document should contain exactly one <title> element."""
    rule_id = "htmlval_001"
    name = "Single Title Element"
    category = "html_validation"
    description = "HTML document must contain exactly one <title> element in the head"
    weight = 1.0
    tags = ["html", "validation", "title", "structure"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        html = data.get("html", "") or ""
        head = data.get("head", {}) or {}
        basic = data.get("basic", {}) or {}
        
        # Try multiple sources for title count
        title_count = 0
        title_text = basic.get("title", "") or ""
        
        # Count from raw HTML
        if html:
            title_count = len(re.findall(r"<title[^>]*>", html, re.IGNORECASE))
        
        # Fallback: check head parsed data
        if title_count == 0 and head:
            head_titles = head.get("title", [])
            if isinstance(head_titles, list):
                title_count = len(head_titles)
            elif head_titles:
                title_count = 1
        
        # If still no count but basic has title, assume 1
        if title_count == 0 and title_text:
            title_count = 1
        
        if title_count == 0:
            return [self._create_result(
                passed=False,
                message="No <title> element found in document",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add exactly one <title> element within the <head> section",
                data={"title_count": 0, "title_text": "", "source": "html"},
            )]
        
        if title_count > 1:
            return [self._create_result(
                passed=False,
                message=f"Multiple <title> elements found ({title_count}) - only one allowed",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Remove duplicate <title> elements, keep only one in <head>",
                data={"title_count": title_count, "title_text": title_text[:200], "source": "html"},
            )]
        
        # Check for empty title
        if not title_text or not title_text.strip():
            return [self._create_result(
                passed=False,
                message="Single <title> element found but it is empty",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Add descriptive text content within the <title> element",
                data={"title_count": 1, "title_text": "", "source": "html"},
            )]
        
        return [self._create_result(
            passed=True,
            message="Exactly one <title> element found with content",
            severity=Severity.PASSED,
            score_impact=0,
            data={"title_count": 1, "title_text": title_text[:200], "character_count": len(title_text), "source": "html"},
        )]


class SingleMetaDescriptionRule(BaseRule):
    """Document should contain exactly one meta description."""
    rule_id = "htmlval_002"
    name = "Single Meta Description"
    category = "html_validation"
    description = "HTML document must contain exactly one <meta name='description'> element"
    weight = 1.0
    tags = ["html", "validation", "meta", "description", "structure"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        html = data.get("html", "") or ""
        head = data.get("head", {}) or {}
        basic = data.get("basic", {}) or {}
        
        meta_desc_count = 0
        meta_desc_text = basic.get("meta_description", "") or ""
        
        # Count from raw HTML (case-insensitive name attribute)
        if html:
            # Match <meta name="description" ...> or <meta name='description' ...>
            meta_desc_count = len(re.findall(r'<meta\s+[^>]*name\s*=\s*["\']description["\'][^>]*>', html, re.IGNORECASE))
        
        # Fallback: check head parsed data
        if meta_desc_count == 0 and head:
            head_meta = head.get("meta", [])
            if isinstance(head_meta, list):
                meta_desc_count = sum(1 for m in head_meta if isinstance(m, dict) and m.get("name", "").lower() == "description")
            elif isinstance(head_meta, dict):
                if head_meta.get("name", "").lower() == "description":
                    meta_desc_count = 1
        
        if meta_desc_count == 0:
            return [self._create_result(
                passed=False,
                message="No meta description found",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add exactly one <meta name='description' content='...'> element within <head>",
                data={"meta_description_count": 0, "description_text": "", "source": "html"},
            )]
        
        if meta_desc_count > 1:
            return [self._create_result(
                passed=False,
                message=f"Multiple meta descriptions found ({meta_desc_count}) - only one allowed",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Remove duplicate <meta name='description'> elements, keep only one in <head>",
                data={"meta_description_count": meta_desc_count, "description_text": meta_desc_text[:200], "source": "html"},
            )]
        
        if not meta_desc_text or not meta_desc_text.strip():
            return [self._create_result(
                passed=False,
                message="Single meta description found but it is empty",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Add descriptive content to the meta description",
                data={"meta_description_count": 1, "description_text": "", "source": "html"},
            )]
        
        return [self._create_result(
            passed=True,
            message="Exactly one meta description found with content",
            severity=Severity.PASSED,
            score_impact=0,
            data={"meta_description_count": 1, "description_text": meta_desc_text[:200], "character_count": len(meta_desc_text), "source": "html"},
        )]


class DoctypeDeclarationRule(BaseRule):
    """Document should contain a valid HTML5 DOCTYPE declaration."""
    rule_id = "htmlval_003"
    name = "DOCTYPE Declaration"
    category = "html_validation"
    description = "HTML document must start with valid HTML5 DOCTYPE declaration"
    weight = 1.0
    tags = ["html", "validation", "doctype", "standards"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        html = data.get("html", "") or ""
        
        if not html:
            return [self._create_result(
                passed=False,
                message="No HTML content to validate DOCTYPE",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Ensure HTML content is available for validation",
                data={"doctype": "", "valid": False, "source": "html"},
            )]
        
        # Check for DOCTYPE at the start of HTML (allowing leading whitespace)
        # HTML5 DOCTYPE: <!DOCTYPE html> (case-insensitive)
        doctype_match = re.match(r"^\s*<!DOCTYPE\s+html\s*>", html, re.IGNORECASE)
        
        if not doctype_match:
            # Check if there's any DOCTYPE at all
            any_doctype = re.match(r"^\s*<!DOCTYPE\s+[^>]+>", html, re.IGNORECASE)
            if any_doctype:
                found_doctype = any_doctype.group(0).strip()
                return [self._create_result(
                    passed=False,
                    message=f"Non-HTML5 DOCTYPE found: {found_doctype}",
                    severity=Severity.WARNING,
                    score_impact=-3,
                    recommendation="Use HTML5 DOCTYPE: <!DOCTYPE html> as the very first line",
                    data={"doctype": found_doctype, "valid": False, "expected": "<!DOCTYPE html>", "source": "html"},
                )]
            
            return [self._create_result(
                passed=False,
                message="DOCTYPE declaration is missing",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add <!DOCTYPE html> as the very first line of the document",
                data={"doctype": "", "valid": False, "expected": "<!DOCTYPE html>", "source": "html"},
            )]
        
        return [self._create_result(
            passed=True,
            message="Valid HTML5 DOCTYPE declaration found",
            severity=Severity.PASSED,
            score_impact=0,
            data={"doctype": doctype_match.group(0).strip(), "valid": True, "source": "html"},
        )]


class CharacterEncodingRule(BaseRule):
    """HTML document should declare its character encoding."""
    rule_id = "htmlval_004"
    name = "Character Encoding"
    category = "html_validation"
    description = "HTML document must declare character encoding via meta charset or HTTP header"
    weight = 1.0
    tags = ["html", "validation", "charset", "encoding", "standards"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        html = data.get("html", "") or ""
        head = data.get("head", {}) or {}
        http = data.get("http", {}) or {}
        
        has_charset = False
        charset_value = ""
        source = "none"
        
        # 1. Check HTML meta charset
        if html:
            # <meta charset="UTF-8">
            meta_charset = re.search(r'<meta\s+charset\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
            if meta_charset:
                has_charset = True
                charset_value = meta_charset.group(1)
                source = "meta_charset"
        
        # 2. Check meta http-equiv Content-Type
        if not has_charset and html:
            http_equiv = re.search(r'<meta\s+http-equiv\s*=\s*["\']Content-Type["\'][^>]*content\s*=\s*["\'][^"\']*charset\s*=\s*([^"\';\s]+)', html, re.IGNORECASE)
            if http_equiv:
                has_charset = True
                charset_value = http_equiv.group(1)
                source = "meta_http_equiv"
        
        # 3. Check HTTP Content-Type header
        if not has_charset and http:
            headers = http.get("headers", {}) or {}
            content_type = headers.get("content-type", "") or headers.get("Content-Type", "")
            if content_type:
                charset_match = re.search(r"charset\s*=\s*([^;\s]+)", content_type, re.IGNORECASE)
                if charset_match:
                    has_charset = True
                    charset_value = charset_match.group(1)
                    source = "http_header"
        
        # 4. Check parsed head data
        if not has_charset and head:
            head_meta = head.get("meta", [])
            if isinstance(head_meta, list):
                for m in head_meta:
                    if isinstance(m, dict):
                        if m.get("charset"):
                            has_charset = True
                            charset_value = m.get("charset")
                            source = "parsed_head_charset"
                            break
                        if m.get("http-equiv", "").lower() == "content-type":
                            content = m.get("content", "")
                            cs_match = re.search(r"charset\s*=\s*([^;\s]+)", content, re.IGNORECASE)
                            if cs_match:
                                has_charset = True
                                charset_value = cs_match.group(1)
                                source = "parsed_head_http_equiv"
                                break
        
        # Validate encoding if found
        valid_encodings = {"utf-8", "utf8", "iso-8859-1", "windows-1252", "ascii", "utf-16", "utf-32"}
        encoding_valid = has_charset and charset_value.lower() in valid_encodings
        
        if not has_charset:
            return [self._create_result(
                passed=False,
                message="Character encoding is not declared",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add <meta charset='UTF-8'> to <head> or ensure server sends Content-Type header with charset",
                data={"has_charset": False, "charset": "", "source": "none", "valid_encodings": list(valid_encodings)},
            )]
        
        if not encoding_valid:
            return [self._create_result(
                passed=False,
                message=f"Character encoding '{charset_value}' may not be valid or widely supported",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation=f"Use a standard encoding like UTF-8. Current: {charset_value}",
                data={"has_charset": True, "charset": charset_value, "source": source, "valid": False, "valid_encodings": list(valid_encodings)},
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Character encoding declared: {charset_value.upper()}",
            severity=Severity.PASSED,
            score_impact=0,
            data={"has_charset": True, "charset": charset_value, "source": source, "valid": True},
        )]


class ValidHeadElementsRule(BaseRule):
    """Elements inside <head> should follow HTML5 content-model rules."""
    rule_id = "htmlval_005"
    name = "Valid Head Elements"
    category = "html_validation"
    description = "Only valid HTML5 head children allowed (title, base, link, meta, style, script, noscript, template)"
    weight = 1.0
    tags = ["html", "validation", "head", "structure", "standards"]

    # Valid head children per HTML5 spec
    VALID_HEAD_CHILDREN = {"title", "base", "link", "meta", "style", "script", "noscript", "template"}

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        head = data.get("head", {}) or {}
        head_rendered = data.get("head_rendered", {}) or {}
        
        # Use rendered head if available (for SPA), otherwise raw
        head_data = head_rendered if head_rendered else head
        
        if not head_data:
            return [self._create_result(
                passed=False,
                message="No head data available for validation",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Ensure HTML head is parsed correctly",
                data={"head_children": [], "invalid_elements": [], "valid_elements": list(self.VALID_HEAD_CHILDREN)},
            )]
        
        invalid_elements = []
        head_children = []
        
        # Check all keys in head data that represent elements
        # Skip metadata fields that are not actual head child elements
        META_FIELDS = {"viewport", "charset", "language", "preconnect_hints", "dns_prefetch_hints", 
                       "preload_hints", "google_fonts_urls", "meta_http_equiv"}
        for key, value in head_data.items():
            if key in self.VALID_HEAD_CHILDREN:
                # Valid element - count instances
                if isinstance(value, list):
                    head_children.extend([key] * len(value))
                else:
                    head_children.append(key)
            elif key not in {"html", "head", "body"} | META_FIELDS:  # Skip wrapper keys and metadata fields
                # Potentially invalid element in head
                if isinstance(value, list) and len(value) > 0:
                    invalid_elements.append(key)
                    head_children.extend([key] * len(value))
                elif value:
                    invalid_elements.append(key)
                    head_children.append(key)
        
        if invalid_elements:
            return [self._create_result(
                passed=False,
                message=f"Invalid elements in <head>: {', '.join(invalid_elements)}",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation=f"Move invalid elements out of <head>. Valid head children: {', '.join(sorted(self.VALID_HEAD_CHILDREN))}",
                data={
                    "head_children": head_children,
                    "invalid_elements": invalid_elements,
                    "valid_elements": list(self.VALID_HEAD_CHILDREN),
                },
            )]
        
        return [self._create_result(
            passed=True,
            message="All <head> children are valid HTML5 elements",
            severity=Severity.PASSED,
            score_impact=0,
            data={
                "head_children": head_children,
                "invalid_elements": [],
                "valid_elements": list(self.VALID_HEAD_CHILDREN),
            },
        )]


class NoscriptInHeadRule(BaseRule):
    """Detect invalid <noscript> placement inside <head>."""
    rule_id = "htmlval_006"
    name = "Noscript in Head"
    category = "html_validation"
    description = "<noscript> in <head> must only contain link, style, or meta elements"
    weight = 1.0
    tags = ["html", "validation", "noscript", "head", "structure"]

    VALID_NOSCRIPT_HEAD_CHILDREN = {"link", "style", "meta"}

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        head = data.get("head", {}) or {}
        head_rendered = data.get("head_rendered", {}) or {}
        html = data.get("html", "") or ""
        
        head_data = head_rendered if head_rendered else head
        noscript_details = []
        has_noscript_in_head = False
        
        # Check parsed head data for noscript
        if head_data:
            noscript_content = head_data.get("noscript", [])
            if isinstance(noscript_content, list) and len(noscript_content) > 0:
                has_noscript_in_head = True
                for ns in noscript_content:
                    if isinstance(ns, dict):
                        # Check children of noscript
                        for child_key, child_value in ns.items():
                            if child_key not in self.VALID_NOSCRIPT_HEAD_CHILDREN:
                                if isinstance(child_value, list) and len(child_value) > 0:
                                    noscript_details.append(f"<noscript> contains invalid child <{child_key}>")
                                elif child_value:
                                    noscript_details.append(f"<noscript> contains invalid child <{child_key}>")
        
        # Also check raw HTML for noscript in head (fallback)
        if not has_noscript_in_head and html:
            # Simple check: find noscript within head tags
            head_match = re.search(r"<head[^>]*>(.*?)</head>", html, re.IGNORECASE | re.DOTALL)
            if head_match:
                head_content = head_match.group(1)
                noscript_matches = re.findall(r"<noscript[^>]*>(.*?)</noscript>", head_content, re.IGNORECASE | re.DOTALL)
                if noscript_matches:
                    has_noscript_in_head = True
                    # Check if noscript content has invalid elements
                    for ns_content in noscript_matches:
                        # Look for tags other than link, style, meta
                        invalid_in_ns = re.findall(r"<(?!/?(?:link|style|meta|/noscript)\b)(\w+)", ns_content, re.IGNORECASE)
                        if invalid_in_ns:
                            noscript_details.append(f"<noscript> in head contains: {', '.join(set(invalid_in_ns))}")
        
        if has_noscript_in_head and noscript_details:
            return [self._create_result(
                passed=False,
                message=f"Invalid <noscript> placement in <head>: {'; '.join(noscript_details)}",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Move <noscript> content to <body> or ensure it only contains <link>, <style>, or <meta> when in <head>",
                data={
                    "has_noscript_in_head": True,
                    "noscript_details": noscript_details,
                    "valid_children": list(self.VALID_NOSCRIPT_HEAD_CHILDREN),
                },
            )]
        
        if has_noscript_in_head and not noscript_details:
            # noscript in head but with valid children only
            return [self._create_result(
                passed=True,
                message="<noscript> in <head> contains only valid children (link, style, meta)",
                severity=Severity.PASSED,
                score_impact=0,
                data={
                    "has_noscript_in_head": True,
                    "noscript_details": [],
                    "valid_children": list(self.VALID_NOSCRIPT_HEAD_CHILDREN),
                },
            )]
        
        return [self._create_result(
            passed=True,
            message="No invalid <noscript> placement detected in <head>",
            severity=Severity.PASSED,
            score_impact=0,
            data={"has_noscript_in_head": False, "noscript_details": []},
        )]


class SingleHeadElementRule(BaseRule):
    """Document should contain exactly one <head> element."""
    rule_id = "htmlval_007"
    name = "Single Head Element"
    category = "html_validation"
    description = "HTML document must contain exactly one <head> element"
    weight = 1.0
    tags = ["html", "validation", "head", "structure"]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        html = data.get("html", "") or ""
        head = data.get("head", {}) or {}
        
        head_count = 0
        source = "parsed"
        
        # Count from raw HTML
        if html:
            head_count = len(re.findall(r"<head\b", html, re.IGNORECASE))
            source = "html"
        
        # Fallback to parsed data
        if head_count == 0 and head:
            head_count = 1
            source = "parsed"
        
        if head_count == 0:
            return [self._create_result(
                passed=False,
                message="No <head> element found",
                severity=Severity.WARNING,
                score_impact=-5,
                recommendation="Add a <head> element to the document",
                data={"head_count": 0, "source": source},
            )]
        
        if head_count > 1:
            return [self._create_result(
                passed=False,
                message=f"Multiple <head> elements found ({head_count}) - only one allowed",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Ensure the document contains exactly one <head> element",
                data={"head_count": head_count, "source": source},
            )]
        
        return [self._create_result(
            passed=True,
            message="Single <head> element found",
            severity=Severity.PASSED,
            score_impact=0,
            data={"head_count": 1, "source": source},
        )]


class HtmlSizeLimitRule(BaseRule):
    """HTML content should remain within the configured size threshold."""
    rule_id = "htmlval_008"
    name = "HTML Size Limit"
    category = "html_validation"
    description = "HTML document size should not exceed recommended limit (default 1MB)"
    weight = 1.0
    tags = ["html", "validation", "size", "performance"]

    # Default threshold: 1 MB
    DEFAULT_MAX_SIZE_BYTES = 1_048_576

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        html = data.get("html", "") or ""
        http = data.get("http", {}) or {}
        
        # Calculate HTML size in UTF-8 bytes
        html_size = len(html.encode("utf-8", errors="replace")) if html else 0
        
        # Also check HTTP content-length if available
        http_content_length = http.get("content_length", 0) or 0
        
        # Use the larger of the two (raw HTML vs compressed response)
        effective_size = max(html_size, http_content_length) if http_content_length > 0 else html_size
        
        max_size = self.DEFAULT_MAX_SIZE_BYTES
        
        if effective_size > max_size:
            return [self._create_result(
                passed=False,
                message=f"HTML size exceeds limit ({effective_size:,} bytes > {max_size:,} bytes)",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation=f"Reduce HTML size to under {max_size:,} bytes (e.g., remove inline scripts/styles, minimize whitespace, use external resources)",
                data={
                    "html_size_bytes": effective_size,
                    "max_size_bytes": max_size,
                    "html_size_kb": round(effective_size / 1024, 1),
                    "max_size_kb": round(max_size / 1024, 1),
                    "raw_html_size_bytes": html_size,
                    "http_content_length": http_content_length,
                },
            )]
        
        return [self._create_result(
            passed=True,
            message=f"HTML size is within limit ({effective_size:,} bytes <= {max_size:,} bytes)",
            severity=Severity.PASSED,
            score_impact=0,
            data={
                "html_size_bytes": effective_size,
                "max_size_bytes": max_size,
                "html_size_kb": round(effective_size / 1024, 1),
                "max_size_kb": round(max_size / 1024, 1),
                "raw_html_size_bytes": html_size,
                "http_content_length": http_content_length,
            },
        )]


class NoPlaceholderTextRule(BaseRule):
    """Detect common unfinished or placeholder content in the webpage."""
    rule_id = "htmlval_009"
    name = "No Placeholder Text"
    category = "html_validation"
    description = "Page content should not contain common placeholder text (lorem ipsum, TODO, coming soon, etc.)"
    weight = 1.0
    tags = ["html", "validation", "content", "placeholder", "quality"]

    # Centralized placeholder patterns (case-insensitive)
    PLACEHOLDER_PATTERNS = [
        (r"lorem\s+ipsum", "Lorem Ipsum"),
        (r"coming\s+soon", "Coming Soon"),
        (r"\bTODO\b", "TODO"),
        (r"replace\s+this\s+text", "Replace This Text"),
        (r"insert\s+text\s+here", "Insert Text Here"),
        (r"your\s+text\s+here", "Your Text Here"),
        (r"placeholder\s+text", "Placeholder Text"),
        (r"sample\s+text", "Sample Text"),
        (r"dummy\s+text", "Dummy Text"),
        (r"under\s+construction", "Under Construction"),
        (r"site\s+under\s+construction", "Site Under Construction"),
        (r"test\s+content", "Test Content"),
        (r"example\s+content", "Example Content"),
        (r"default\s+text", "Default Text"),
    ]

    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        content_text = data.get("content", {}).get("text", "") or ""
        html = data.get("html", "") or ""
        
        # Use content text (visible text) for checking, not raw HTML
        text_to_check = content_text if content_text else html
        
        if not text_to_check:
            return [self._create_result(
                passed=True,
                message="No content text to check for placeholders",
                severity=Severity.INFO,
                score_impact=0,
                data={"placeholder_matches": [], "match_count": 0},
            )]
        
        text_lower = text_to_check.lower()
        placeholder_matches = []
        
        for pattern, label in self.PLACEHOLDER_PATTERNS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            if matches:
                placeholder_matches.append({
                    "pattern": label,
                    "count": len(matches),
                    "examples": matches[:3]  # First 3 matches
                })
        
        if placeholder_matches:
            match_summary = ", ".join([f"{m['pattern']} ({m['count']})" for m in placeholder_matches])
            return [self._create_result(
                passed=False,
                message=f"Placeholder text detected: {match_summary}",
                severity=Severity.WARNING,
                score_impact=-3,
                recommendation="Replace placeholder content with final, meaningful content before publishing",
                data={
                    "placeholder_matches": placeholder_matches,
                    "match_count": sum(m["count"] for m in placeholder_matches),
                },
            )]
        
        return [self._create_result(
            passed=True,
            message="No placeholder text detected",
            severity=Severity.PASSED,
            score_impact=0,
            data={"placeholder_matches": [], "match_count": 0},
        )]


__all__ = [
    "SingleTitleElementRule",
    "SingleMetaDescriptionRule",
    "DoctypeDeclarationRule",
    "CharacterEncodingRule",
    "ValidHeadElementsRule",
    "NoscriptInHeadRule",
    "SingleHeadElementRule",
    "HtmlSizeLimitRule",
    "NoPlaceholderTextRule",
]