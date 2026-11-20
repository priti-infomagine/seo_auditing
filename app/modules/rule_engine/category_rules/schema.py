"""
Schema / Structured Data Rules.

This module implements 5 core validation rules for structured data:
1. schema_001 - Schema Markup Presence
2. schema_002 - Schema Syntax Validation
3. schema_003 - Schema Type Validation
4. schema_004 - Schema Required Properties
5. schema_005 - Schema Content Consistency

Plus type-specific rules (schema_006+) for common schema types.

Design principles:
- Support JSON-LD, Microdata, and RDFa formats
- Don't assume every page must have schema (some page types legitimately don't)
- Validate required properties per schema type (Google Rich Results spec)
- Valid JSON ≠ valid Schema.org markup (must have @context, @type)
- Compare schema with visible content using fuzzy matching (tolerate minor formatting differences)
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Set

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


# ================================================================
# CORE SCHEMA VALIDATION RULES (schema_001 - schema_005)
# ================================================================

class SchemaMarkupPresenceRule(BaseRule):
    """
    schema_001 - Schema Markup Presence
    
    Checks whether the page contains structured data using JSON-LD, Microdata, or RDFa.
    
    Note: Not all pages need structured data (e.g., utility pages, login pages, 
    search results, paginated archives). This rule reports presence as INFO when 
    absent, not a hard failure.
    """
    rule_id = "schema_001"
    name = "Schema Markup Presence"
    category = "schema"
    description = "Page may have structured data markup (JSON-LD, Microdata, or RDFa)"
    weight = 0.8
    tags = ["info", "schema", "rich_snippets"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        formats = structured_data.get("formats", [])
        
        if not schema_markup:
            # Not all pages need schema - report as INFO, not WARNING
            return [self._create_result(
                passed=True,  # Not a failure - many pages legitimately lack schema
                message="No structured data / schema markup found on page",
                severity=Severity.INFO,
                score_impact=0,
                recommendation="Consider adding Schema.org markup (JSON-LD recommended) if this page represents an entity (Article, Product, Event, LocalBusiness, etc.) that could benefit from rich snippets",
            )]
        
        # Count by format
        format_counts: Dict[str, int] = {}
        for fmt in formats:
            format_counts[fmt] = format_counts.get(fmt, 0) + 1
        
        # Get unique schema types found
        schema_types: List[str] = []
        for schema in schema_markup[:10]:
            schema_type = schema.get("@type") or schema.get("type", "Unknown")
            if schema_type not in schema_types:
                schema_types.append(schema_type)
        
        return [self._create_result(
            passed=True,
            message=f"Structured data found: {len(schema_markup)} item(s) across {len(formats)} format(s) — Types: {', '.join(schema_types[:5])}",
            severity=Severity.PASSED,
            score_impact=0,
            data={
                "schema_count": len(schema_markup),
                "formats": format_counts,
                "types": schema_types[:10],
            },
        )]


class SchemaSyntaxValidationRule(BaseRule):
    """
    schema_002 - Schema Syntax Validation
    
    Checks whether structured data is valid and parseable:
    - JSON-LD: valid JSON with @context and @type
    - Microdata: valid HTML with itemscope/itemtype/itemprop
    - RDFa: valid HTML with vocab/typeof/property
    
    Valid JSON ≠ valid Schema.org markup — must have Schema.org structure.
    """
    rule_id = "schema_002"
    name = "Schema Syntax Validation"
    category = "schema"
    description = "Structured data must be valid and parseable with Schema.org structure (@context, @type)"
    weight = 1.2
    tags = ["critical", "schema", "syntax", "json-ld", "microdata", "rdfa"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        formats = structured_data.get("formats", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to validate",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        total_schemas = len(schema_markup)
        parse_errors = []
        structure_errors = []
        valid_items = 0
        
        for idx, schema in enumerate(schema_markup):
            fmt = formats[idx] if idx < len(formats) else "unknown"
            schema_type = schema.get("@type") or schema.get("type", "Unknown")
            
            # Check for parse errors from extractor
            parse_error = schema.get("parse_error") or schema.get("attributes", {}).get("parse_error")
            if parse_error:
                parse_errors.append({
                    "index": idx,
                    "format": fmt,
                    "type": schema_type,
                    "error": str(parse_error)[:200],
                })
                continue
            
            # Validate Schema.org structure (not just JSON syntax)
            structure_issues = self._validate_schema_structure(schema, fmt)
            if structure_issues:
                structure_errors.append({
                    "index": idx,
                    "format": fmt,
                    "type": schema_type,
                    "issues": structure_issues,
                })
                continue
            
            valid_items += 1
        
        # Determine result
        has_errors = bool(parse_errors or structure_errors)
        
        if has_errors:
            all_errors = parse_errors + structure_errors
            return [self._create_result(
                passed=False,
                message=f"Schema validation errors: {len(all_errors)} of {total_schemas} item(s) invalid",
                severity=Severity.WARNING if valid_items > 0 else Severity.CRITICAL,
                score_impact=-min(len(all_errors) * 3, 10),
                recommendation="Fix structured data syntax and structure — use Google's Rich Results Test or Schema.org Validator",
                data={
                    "total_schemas": total_schemas,
                    "valid_count": valid_items,
                    "parse_errors": parse_errors[:3],
                    "structure_errors": structure_errors[:3],
                },
            )]
        
        return [self._create_result(
            passed=True,
            message=f"All {total_schemas} schema item(s) are valid and well-structured",
            severity=Severity.PASSED,
            score_impact=0,
            data={"total_schemas": total_schemas, "valid_count": valid_items},
        )]
    
    def _validate_schema_structure(self, schema: Dict[str, Any], fmt: str) -> List[str]:
        """Validate Schema.org structure per format."""
        issues = []
        
        if fmt.lower() == "json-ld":
            # JSON-LD must have @context and @type
            if not schema.get("@context"):
                issues.append("Missing @context (should be 'https://schema.org')")
            elif "schema.org" not in str(schema.get("@context", "")).lower():
                issues.append("@context should reference schema.org")
            
            if not schema.get("@type") and not schema.get("type"):
                issues.append("Missing @type")
            
            # Check parsed object exists
            if not schema.get("parsed"):
                issues.append("JSON-LD could not be parsed to object")
                
        elif fmt.lower() in ("microdata", "rdfa"):
            # Microdata/RDFa validation via attributes
            attrs = schema.get("attributes", {})
            if not attrs.get("itemscope") and not attrs.get("typeof"):
                issues.append(f"Missing {'itemscope' if fmt == 'microdata' else 'typeof'} attribute")
            if not attrs.get("itemtype") and not attrs.get("vocab"):
                issues.append(f"Missing {'itemtype' if fmt == 'microdata' else 'vocab'} attribute")
        
        return issues


class SchemaTypeValidationRule(BaseRule):
    """
    schema_003 - Schema Type Validation
    
    Checks whether schema contains a valid and recognizable @type from Schema.org vocabulary.
    Recognizes both Google Rich Result eligible types and general Schema.org types.
    """
    rule_id = "schema_003"
    name = "Schema Type Validation"
    category = "schema"
    description = "Each schema item must have a valid @type from Schema.org vocabulary"
    weight = 1.1
    tags = ["critical", "schema", "type", "schema.org"]
    
    # Known Schema.org types (matches google_rich_results.py SCHEMA_ORG_KNOWN_TYPES)
    KNOWN_TYPES: Set[str] = {
        "Thing", "CreativeWork", "Article", "NewsArticle", "BlogPosting", "ScholarlyArticle",
        "Product", "Offer", "AggregateOffer", "LocalBusiness", "Organization", "Person",
        "Event", "JobPosting", "FAQPage", "Question", "Answer", "HowTo", "HowToStep",
        "Recipe", "BreadcrumbList", "ListItem", "VideoObject", "WebSite", "SearchAction",
        "Review", "AggregateRating", "Rating", "Course", "CourseInstance", "Dataset",
        "PodcastSeries", "PodcastEpisode", "SoftwareApplication", "Movie", "Book",
        "Place", "PostalAddress", "GeoCoordinates", "OpeningHoursSpecification",
        "ContactPoint", "Brand", "ImageObject", "MediaObject", "AudioObject",
        "MusicRecording", "MusicAlbum", "MusicGroup", "MusicPlaylist",
        "TVSeries", "TVEpisode", "TVSeason", "Clip", "Game", "VideoGame",
        "EducationalOccupationalProgram", "Occupation",
        "Vehicle", "Car", "Bus", "Train", "Flight",
        "MedicalEntity", "MedicalCondition", "Drug", "Hospital", "Pharmacy",
        "GovernmentOrganization", "NGO", "Corporation", "EducationalOrganization",
        "SportsOrganization", "PerformingGroup", "Project", "ResearchProject",
        "FundingScheme", "Grant", "MonetaryAmount", "QuantitativeValue",
        "StructuredValue", "PropertyValue", "PropertyValueSpecification",
        "Action", "AchieveAction", "AssessAction", "ConsumeAction", "ControlAction",
        "CreateAction", "FindAction", "InteractAction", "MoveAction", "OrganizeAction",
        "PlayAction", "SearchAction", "TradeAction", "TransferAction", "UpdateAction",
        "WebPage", "WebPageElement", "SiteNavigationElement", "Table", "WPHeader",
        "WPFooter", "WPSideBar", "ItemPage", "CollectionPage", "ImageGallery",
        "VideoGallery", "Message", "EmailMessage", "SocialMediaPosting",
        "DiscussionForumPosting", "QAPage", "Comment",
    }
    
    # Google Rich Result eligible types
    GOOGLE_RICH_TYPES: Set[str] = {
        "Article", "NewsArticle", "BlogPosting", "ScholarlyArticle",
        "Product", "Offer", "AggregateOffer",
        "LocalBusiness", "Organization",
        "Event", "JobPosting",
        "FAQPage", "Question", "Answer", "HowTo", "HowToStep",
        "Recipe", "BreadcrumbList", "ListItem",
        "VideoObject", "WebSite", "SearchAction",
        "Person", "Review", "AggregateRating", "Rating",
        "Course", "CourseInstance", "Dataset",
        "PodcastSeries", "PodcastEpisode",
        "SoftwareApplication", "Movie", "Book",
    }
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to validate",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        total_schemas = len(schema_markup)
        issues = []
        recognized_types = []
        unrecognized_types = []
        google_rich_eligible = []
        missing_type_count = 0
        
        for idx, schema in enumerate(schema_markup):
            schema_type = schema.get("@type") or schema.get("type")
            
            if not schema_type:
                missing_type_count += 1
                issues.append({
                    "index": idx,
                    "issue": "missing_type",
                    "message": "Schema item missing @type",
                })
                continue
            
            # Handle array of types (e.g., ["Article", "NewsArticle"])
            if isinstance(schema_type, list):
                schema_type = schema_type[0] if schema_type else ""
            
            schema_type = str(schema_type).strip()
            
            if schema_type in self.KNOWN_TYPES:
                recognized_types.append(schema_type)
                if schema_type in self.GOOGLE_RICH_TYPES:
                    google_rich_eligible.append(schema_type)
            else:
                unrecognized_types.append(schema_type)
                issues.append({
                    "index": idx,
                    "issue": "unrecognized_type",
                    "type": schema_type,
                    "message": f"Unrecognized schema type: '{schema_type}'",
                })
        
        # Determine severity - only WARN if we have schemas with issues
        if missing_type_count > 0 or unrecognized_types:
            severity = Severity.WARNING
            impact = -min((missing_type_count + len(unrecognized_types)) * 2, 8)
        else:
            severity = Severity.PASSED
            impact = 0
        
        # Build message
        msg_parts = []
        if recognized_types:
            unique_recognized = list(set(recognized_types))
            msg_parts.append(f"{len(unique_recognized)} recognized type(s): {', '.join(unique_recognized[:5])}")
        if google_rich_eligible:
            unique_rich = list(set(google_rich_eligible))
            msg_parts.append(f"{len(unique_rich)} Google Rich Result eligible: {', '.join(unique_rich[:3])}")
        if unrecognized_types:
            msg_parts.append(f"{len(unrecognized_types)} unrecognized type(s)")
        if missing_type_count:
            msg_parts.append(f"{missing_type_count} missing @type")
        
        message = "; ".join(msg_parts) if msg_parts else "No valid schema types found"
        
        recommendation = None
        if missing_type_count > 0:
            recommendation = "Ensure every schema item has an @type property"
        elif unrecognized_types:
            recommendation = "Use standard Schema.org types; unrecognized types won't qualify for Rich Results"
        
        return [self._create_result(
            passed=(missing_type_count == 0 and len(unrecognized_types) == 0),
            message=message,
            severity=severity,
            score_impact=impact,
            recommendation=recommendation,
            data={
                "total_schemas": total_schemas,
                "recognized_types": list(set(recognized_types)),
                "unrecognized_types": list(set(unrecognized_types)),
                "google_rich_eligible": list(set(google_rich_eligible)),
                "missing_type_count": missing_type_count,
            },
        )]


class SchemaRequiredPropertiesRule(BaseRule):
    """
    schema_004 - Schema Required Properties
    
    Checks whether required properties are present for the declared schema type
    according to Google Rich Results specifications.
    """
    rule_id = "schema_004"
    name = "Schema Required Properties"
    category = "schema"
    description = "Schema types must include all required properties for Google Rich Result eligibility"
    weight = 1.3
    tags = ["critical", "schema", "properties", "google_rich_results"]
    
    # Required properties per schema type (from Google Rich Results docs)
    REQUIRED_PROPS: Dict[str, List[str]] = {
        "Article": ["headline", "image", "datePublished", "author"],
        "NewsArticle": ["headline", "image", "datePublished", "author"],
        "BlogPosting": ["headline", "image", "datePublished", "author"],
        "ScholarlyArticle": ["headline", "image", "datePublished", "author"],
        "Product": ["name", "image", "offers"],
        "Offer": ["price", "priceCurrency", "availability"],
        "AggregateOffer": ["price", "priceCurrency", "availability", "offerCount"],
        "LocalBusiness": ["name", "address"],
        "Organization": ["name", "url"],
        "Event": ["name", "startDate", "location"],
        "JobPosting": ["title", "description", "datePosted", "hiringOrganization", "jobLocation"],
        "FAQPage": ["mainEntity"],
        "Question": ["name", "acceptedAnswer"],
        "Answer": ["text"],
        "HowTo": ["name", "step"],
        "HowToStep": ["name", "itemListElement"],
        "Recipe": ["name", "recipeIngredient", "recipeInstructions"],
        "BreadcrumbList": ["itemListElement"],
        "ListItem": ["position", "item"],
        "VideoObject": ["name", "description", "thumbnailUrl", "uploadDate"],
        "WebSite": ["name", "url"],
        "SearchAction": ["target", "query-input"],
        "Person": ["name"],
        "Review": ["author", "reviewRating", "datePublished"],
        "AggregateRating": ["ratingValue", "reviewCount"],
        "Rating": ["ratingValue"],
        "Course": ["name", "provider"],
        "CourseInstance": ["courseMode", "startDate", "endDate"],
        "Dataset": ["name", "description"],
        "PodcastSeries": ["name", "url", "description"],
        "PodcastEpisode": ["name", "description", "associatedMedia"],
        "SoftwareApplication": ["name", "applicationCategory", "offers"],
        "Movie": ["name", "director"],
        "Book": ["name", "author"],
    }
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to validate",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        all_missing = []
        all_present = []
        schemas_checked = 0
        
        for idx, schema in enumerate(schema_markup):
            schema_type = schema.get("@type") or schema.get("type")
            if isinstance(schema_type, list):
                schema_type = schema_type[0] if schema_type else ""
            if not schema_type:
                continue
            
            schema_type = str(schema_type).strip()
            required = self.REQUIRED_PROPS.get(schema_type)
            
            if not required:
                # Type not in our registry - skip required property check
                continue
            
            schemas_checked += 1
            
            # Extract all properties from parsed schema
            schema_props = self._extract_all_properties(schema)
            
            missing = [prop for prop in required if prop not in schema_props]
            present = [prop for prop in required if prop in schema_props]
            
            if missing:
                all_missing.extend([{
                    "schema_index": idx,
                    "schema_type": schema_type,
                    "property": prop,
                } for prop in missing])
            all_present.extend(present)
        
        if not schemas_checked:
            return [self._create_result(
                passed=True,
                message="No schema types with known required properties found",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if all_missing:
            return [self._create_result(
                passed=False,
                message=f"Missing required properties: {len(all_missing)} property(s) across {schemas_checked} schema item(s)",
                severity=Severity.WARNING,
                score_impact=-min(len(all_missing) * 2, 10),
                recommendation="Add all required properties for each schema type to qualify for Google Rich Results",
                data={
                    "schemas_checked": schemas_checked,
                    "missing_count": len(all_missing),
                    "present_count": len(all_present),
                    "missing_details": all_missing[:10],
                },
            )]
        
        return [self._create_result(
            passed=True,
            message=f"All required properties present for {schemas_checked} schema item(s) ({len(all_present)} properties validated)",
            severity=Severity.PASSED,
            score_impact=0,
            data={"schemas_checked": schemas_checked, "properties_validated": len(all_present)},
        )]
    
    def _extract_all_properties(self, schema: Dict[str, Any]) -> Set[str]:
        """Extract all property names from schema (handles nested structures)."""
        props: Set[str] = set()
        parsed = schema.get("parsed")
        
        if isinstance(parsed, dict):
            self._collect_properties(parsed, props)
        elif isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    self._collect_properties(item, props)
        
        # Also check Microdata/RDFa properties in attributes
        attrs = schema.get("attributes", {})
        if "properties" in attrs:
            for prop in attrs["properties"]:
                if isinstance(prop, dict) and "property" in prop:
                    props.add(prop["property"])
        
        return props
    
    def _collect_properties(self, obj: dict, props: Set[str], prefix: str = "") -> None:
        """Recursively collect property names from JSON-LD object."""
        for key, value in obj.items():
            if key.startswith("@"):  # Skip @context, @type, @id, @graph
                continue
            prop_name = f"{prefix}{key}" if prefix else key
            props.add(prop_name)
            
            if isinstance(value, dict):
                self._collect_properties(value, props, f"{prop_name}.")
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._collect_properties(item, props, f"{prop_name}.")


class SchemaContentConsistencyRule(BaseRule):
    """
    schema_005 - Schema Content Consistency
    
    Checks whether structured data accurately represents visible page content.
    Uses fuzzy matching to tolerate minor formatting differences.
    """
    rule_id = "schema_005"
    name = "Schema Content Consistency"
    category = "schema"
    description = "Structured data should match visible page content (title, description, headline, etc.)"
    weight = 1.0
    tags = ["warning", "schema", "content_consistency", "accuracy"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        
        # Get visible page content for comparison
        basic = data.get("basic", {})
        seo = data.get("seo", {})
        
        visible_content = {
            "title": basic.get("title", "") or seo.get("title", ""),
            "meta_description": basic.get("meta_description", "") or seo.get("meta_description", ""),
            "h1": basic.get("h1", []) if isinstance(basic.get("h1"), list) else [],
            "canonical_url": basic.get("canonical_url", "") or seo.get("canonical_url", ""),
        }
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to validate",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        inconsistencies = []
        consistent_items = 0
        
        for idx, schema in enumerate(schema_markup):
            parsed = schema.get("parsed")
            if not parsed or not isinstance(parsed, dict):
                continue
            
            schema_type = schema.get("@type") or schema.get("type")
            if isinstance(schema_type, list):
                schema_type = schema_type[0] if schema_type else ""
            schema_type = str(schema_type).strip() if schema_type else ""
            
            # Check headline vs page title / H1
            if "headline" in parsed:
                schema_headline = str(parsed["headline"]).strip()
                page_title = visible_content.get("title", "").strip()
                h1_text = visible_content.get("h1", [""])[0] if visible_content.get("h1") else ""
                
                reference = page_title or h1_text
                if reference and not self._texts_match(schema_headline, reference):
                    inconsistencies.append({
                        "schema_index": idx,
                        "schema_type": schema_type,
                        "property": "headline",
                        "schema_value": schema_headline[:100],
                        "page_value": reference[:100],
                        "message": "Schema headline differs from page title/H1",
                    })
            
            # Check description vs meta description
            if "description" in parsed:
                schema_desc = str(parsed["description"]).strip()
                meta_desc = visible_content.get("meta_description", "").strip()
                if meta_desc and not self._texts_match(schema_desc, meta_desc):
                    inconsistencies.append({
                        "schema_index": idx,
                        "schema_type": schema_type,
                        "property": "description",
                        "schema_value": schema_desc[:100],
                        "page_value": meta_desc[:100],
                        "message": "Schema description differs from meta description",
                    })
            
            # Check URL vs canonical URL
            if "url" in parsed or "mainEntityOfPage" in parsed:
                schema_url = str(parsed.get("url") or parsed.get("mainEntityOfPage", {}).get("@id", "")).strip()
                canonical = visible_content.get("canonical_url", "").strip()
                if canonical and schema_url and not self._urls_match(schema_url, canonical):
                    inconsistencies.append({
                        "schema_index": idx,
                        "schema_type": schema_type,
                        "property": "url/mainEntityOfPage",
                        "schema_value": schema_url[:100],
                        "page_value": canonical[:100],
                        "message": "Schema URL differs from canonical URL",
                    })
            
            consistent_items += 1
        
        if inconsistencies:
            return [self._create_result(
                passed=False,
                message=f"Content consistency issues: {len(inconsistencies)} mismatch(es) found across {consistent_items} schema item(s)",
                severity=Severity.WARNING,
                score_impact=-min(len(inconsistencies) * 2, 8),
                recommendation="Ensure schema properties (headline, description, url) match visible page content",
                data={
                    "schemas_checked": consistent_items,
                    "inconsistency_count": len(inconsistencies),
                    "details": inconsistencies[:10],
                },
            )]
        
        if consistent_items == 0:
            return [self._create_result(
                passed=True,
                message="No comparable schema properties found to validate",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=True,
            message=f"Schema content is consistent with visible page ({consistent_items} item(s) validated)",
            severity=Severity.PASSED,
            score_impact=0,
            data={"schemas_validated": consistent_items},
        )]
    
    def _texts_match(self, text1: str, text2: str, threshold: float = 0.8) -> bool:
        """Simple text similarity check - tolerates minor formatting differences."""
        if not text1 or not text2:
            return False
        # Normalize
        t1 = text1.lower().strip()
        t2 = text2.lower().strip()
        if t1 == t2:
            return True
        # Check if one contains the other (for truncated titles)
        if t1 in t2 or t2 in t1:
            return True
        # Simple word overlap
        words1 = set(t1.split())
        words2 = set(t2.split())
        if not words1 or not words2:
            return False
        overlap = len(words1 & words2) / max(len(words1), len(words2))
        return overlap >= threshold
    
    def _urls_match(self, url1: str, url2: str) -> bool:
        """Check if URLs are equivalent (ignore trailing slash, www, protocol)."""
        from urllib.parse import urlparse
        
        def normalize(u: str) -> str:
            try:
                parsed = urlparse(u)
                host = parsed.netloc.lower().replace("www.", "")
                path = parsed.path.rstrip("/")
                return f"{host}{path}"
            except Exception:
                return u.lower().rstrip("/")
        
        return normalize(url1) == normalize(url2)


# ================================================================
# TYPE-SPECIFIC SCHEMA RULES (schema_006+)
# These check for presence of specific schema types
# ================================================================

class OrganizationSchemaRule(BaseRule):
    """schema_006 - Organization Schema Presence"""
    rule_id = "schema_006"
    name = "Organization Schema"
    category = "schema"
    description = "Organization/LocalBusiness schema helps with Knowledge Panel and brand visibility"
    weight = 0.8
    tags = ["info", "schema", "branding", "organization"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to analyze",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        org_types = {"organization", "localbusiness", "corporation", "ngo", "governmentorganization"}
        has_org = any(
            (schema.get("@type") or schema.get("type", "")).lower() in org_types
            for schema in schema_markup
        )
        
        if has_org:
            return [self._create_result(
                passed=True,
                message="Organization/LocalBusiness schema found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message="No Organization or LocalBusiness schema found",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Add Organization or LocalBusiness schema for brand visibility and Knowledge Panel eligibility",
        )]


class BreadcrumbSchemaRule(BaseRule):
    """schema_007 - Breadcrumb Schema Presence"""
    rule_id = "schema_007"
    name = "Breadcrumb Schema"
    category = "schema"
    description = "BreadcrumbList schema improves navigation display in search results"
    weight = 0.7
    tags = ["info", "schema", "navigation", "breadcrumb"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to analyze",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        has_breadcrumb = any(
            "breadcrumb" in ((schema.get("@type") or schema.get("type", "")).lower())
            for schema in schema_markup
        )
        
        if has_breadcrumb:
            return [self._create_result(
                passed=True,
                message="BreadcrumbList schema found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message="No BreadcrumbList schema found",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Add BreadcrumbList schema for better navigation display in search results",
        )]


class ArticleSchemaRule(BaseRule):
    """schema_008 - Article/NewsArticle/BlogPosting Schema Presence"""
    rule_id = "schema_008"
    name = "Article Schema"
    category = "schema"
    description = "Article/NewsArticle/BlogPosting schema for content pages"
    weight = 0.7
    tags = ["info", "schema", "content", "article"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to analyze",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        article_types = {"article", "newsarticle", "blogposting", "scholarlyarticle"}
        has_article = any(
            (schema.get("@type") or schema.get("type", "")).lower() in article_types
            for schema in schema_markup
        )
        
        if has_article:
            return [self._create_result(
                passed=True,
                message="Article schema found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message="No Article/NewsArticle/BlogPosting schema found",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Add Article or BlogPosting schema for content pages to enable Article rich results",
        )]


class ProductSchemaRule(BaseRule):
    """schema_009 - Product Schema Presence"""
    rule_id = "schema_009"
    name = "Product Schema"
    category = "schema"
    description = "Product schema for e-commerce pages"
    weight = 0.7
    tags = ["info", "schema", "ecommerce", "product"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to analyze",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        product_types = {"product", "offer", "aggregateoffer"}
        has_product = any(
            (schema.get("@type") or schema.get("type", "")).lower() in product_types
            for schema in schema_markup
        )
        
        if has_product:
            return [self._create_result(
                passed=True,
                message="Product schema found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message="No Product/Offer schema found",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Add Product schema with offers for e-commerce pages to enable Product rich results",
        )]


class JsonLdFormatRule(BaseRule):
    """schema_010 - JSON-LD Format Check"""
    rule_id = "schema_010"
    name = "JSON-LD Format"
    category = "schema"
    description = "Schema should use valid JSON-LD format (recommended by Google)"
    weight = 0.6
    tags = ["info", "schema", "format", "json-ld"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        structured_data = data.get("structured_data", {})
        schema_markup = structured_data.get("schema_markup", [])
        formats = structured_data.get("formats", [])
        
        if not schema_markup:
            return [self._create_result(
                passed=True,
                message="No schema markup to analyze",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        has_jsonld = "json-ld" in [f.lower() for f in formats] or any(
            isinstance(s, dict) and s.get("@context") and s.get("@type")
            for s in schema_markup
        )
        
        if has_jsonld:
            return [self._create_result(
                passed=True,
                message="JSON-LD schema format detected (Google recommended)",
                severity=Severity.PASSED,
                score_impact=0,
                data={"formats": formats, "jsonld_count": len(schema_markup)},
            )]
        
        return [self._create_result(
            passed=False,
            message="Schema markup found but JSON-LD format not detected",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Use JSON-LD format for structured data (Google recommended over Microdata/RDFa)",
            data={"formats": formats, "schema_count": len(schema_markup)},
        )]


# ================================================================
# EXPORTS
# ================================================================

__all__ = [
    # Core validation rules (schema_001 - schema_005)
    "SchemaMarkupPresenceRule",
    "SchemaSyntaxValidationRule", 
    "SchemaTypeValidationRule",
    "SchemaRequiredPropertiesRule",
    "SchemaContentConsistencyRule",
    # Type-specific rules (schema_006+)
    "OrganizationSchemaRule",
    "BreadcrumbSchemaRule",
    "ArticleSchemaRule",
    "ProductSchemaRule",
    "JsonLdFormatRule",
]