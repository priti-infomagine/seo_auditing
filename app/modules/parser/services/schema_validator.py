"""
SchemaValidator - Validates schema markup against Schema.org vocabulary
and Google Rich Results requirements.
"""
from __future__ import annotations

import json
from typing import Any
from collections import Counter

from app.modules.parser.models.schema_data import (
    SchemaData,
    SchemaValidationResult,
    SchemaValidationIssue,
)
from app.modules.parser.schemas.google_rich_results import (
    get_schema_requirements,
    is_google_rich_result_type,
    is_known_schema_type,
    get_required_properties,
    get_recommended_properties,
)


class SchemaValidator:
    """
    Validates schema markup for:
    1. JSON-LD syntax validity
    2. @context presence and correctness
    3. @type presence and validity
    4. Required properties per schema type
    5. Recommended properties per schema type
    6. Property value formats
    7. Duplicate/conflicting entities
    8. Schema vs visible content consistency
    9. Google Rich Result eligibility
    """

    # Common @context values that are valid
    VALID_CONTEXTS = {
        "https://schema.org",
        "http://schema.org",
        "https://schema.org/",
        "http://schema.org/",
        "https://schema.org/docs/schemas.html",
    }

    # Property value format validators
    FORMAT_VALIDATORS = {
        "datePublished": lambda v: SchemaValidator._is_iso_date(v),
        "dateModified": lambda v: SchemaValidator._is_iso_date(v),
        "datePosted": lambda v: SchemaValidator._is_iso_date(v),
        "startDate": lambda v: SchemaValidator._is_iso_date(v),
        "endDate": lambda v: SchemaValidator._is_iso_date(v),
        "validThrough": lambda v: SchemaValidator._is_iso_date(v),
        "uploadDate": lambda v: SchemaValidator._is_iso_date(v),
        "foundingDate": lambda v: SchemaValidator._is_iso_date(v),
        "releaseDate": lambda v: SchemaValidator._is_iso_date(v),
        "birthDate": lambda v: SchemaValidator._is_iso_date(v),
        "deathDate": lambda v: SchemaValidator._is_iso_date(v),
        "url": lambda v: SchemaValidator._is_url(v),
        "image": lambda v: SchemaValidator._is_url(v),
        "logo": lambda v: SchemaValidator._is_url(v),
        "thumbnailUrl": lambda v: SchemaValidator._is_url(v),
        "contentUrl": lambda v: SchemaValidator._is_url(v),
        "embedUrl": lambda v: SchemaValidator._is_url(v),
        "installUrl": lambda v: SchemaValidator._is_url(v),
        "sameAs": lambda v: SchemaValidator._is_url(v),
        "email": lambda v: SchemaValidator._is_email(v),
        "telephone": lambda v: SchemaValidator._is_phone(v),
        "price": lambda v: SchemaValidator._is_price(v),
        "priceCurrency": lambda v: SchemaValidator._is_currency(v),
        "ratingValue": lambda v: SchemaValidator._is_rating(v),
        "bestRating": lambda v: SchemaValidator._is_rating(v),
        "worstRating": lambda v: SchemaValidator._is_rating(v),
        "reviewCount": lambda v: SchemaValidator._is_int(v),
        "ratingCount": lambda v: SchemaValidator._is_int(v),
        "offerCount": lambda v: SchemaValidator._is_int(v),
    }

    def __init__(self):
        self._all_parsed_schemas: list[SchemaData] = []

    def validate(self, schema_data: SchemaData) -> SchemaValidationResult:
        """Validate a single schema data item."""
        result = SchemaValidationResult()

        # 1. Schema presence
        result.has_schema = True  # If we're here, schema was extracted

        # 2. JSON-LD syntax validity
        result.is_valid_json_ld = not bool(schema_data.attributes.get("parse_error"))

        # 3. @context validation
        result.has_context = self._check_context(schema_data, result)

        # 4. @type validation
        result.has_type, result.schema_type = self._check_type(schema_data, result)

        # 5. Known type check
        if result.schema_type:
            result.is_known_type = is_known_schema_type(result.schema_type)
            result.is_google_rich_result = is_google_rich_result_type(result.schema_type)

        # 6. Required/Recommended properties
        if result.schema_type:
            self._check_properties(schema_data, result)

        # 7. Property value formats
        self._validate_property_formats(schema_data, result)

        # 8. Duplicate entities (check across all schemas)
        self._check_duplicates(schema_data, result)

        return result

    def validate_all(self, schemas: list[SchemaData]) -> list[SchemaData]:
        """Validate all schemas and check for cross-schema issues."""
        self._all_parsed_schemas = schemas
        for schema in schemas:
            schema.validation = self.validate(schema)
        # Check cross-schema issues after all individual validations
        self._check_cross_schema_issues()
        return schemas

    def _check_context(self, schema: SchemaData, result: SchemaValidationResult) -> bool:
        """Validate @context presence and value."""
        context = schema.context
        if not context:
            result.issues.append(SchemaValidationIssue(
                severity="warning",
                code="missing_context",
                message="Missing @context - should be 'https://schema.org'",
                property="@context",
                expected="https://schema.org",
                actual="missing",
            ))
            return False

        # Normalize context for comparison
        normalized = context.strip().rstrip("/")
        if normalized not in {c.rstrip("/") for c in self.VALID_CONTEXTS}:
            result.issues.append(SchemaValidationIssue(
                severity="warning",
                code="unexpected_context",
                message=f"Unexpected @context value: '{context}'. Expected 'https://schema.org'",
                property="@context",
                expected="https://schema.org",
                actual=context,
            ))
        return True

    def _check_type(self, schema: SchemaData, result: SchemaValidationResult) -> tuple[bool, str | None]:
        """Validate @type presence and extract primary type."""
        types = schema.types
        if not types:
            result.issues.append(SchemaValidationIssue(
                severity="warning",
                code="missing_type",
                message="Missing @type - cannot identify schema type",
                property="@type",
                expected="Schema.org type (e.g., Article, Product)",
                actual="missing",
            ))
            return False, None

        primary_type = types[0]
        return True, primary_type

    def _check_properties(self, schema: SchemaData, result: SchemaValidationResult) -> None:
        """Check required and recommended properties for the schema type."""
        if not result.schema_type:
            return

        requirements = get_schema_requirements(result.schema_type)
        if not requirements:
            return

        # Extract all properties from schema
        schema_props = self._extract_all_properties(schema)

        required = get_required_properties(result.schema_type)
        recommended = get_recommended_properties(result.schema_type)

        result.required_properties = required
        result.recommended_properties = recommended

        # Check missing required
        for prop in required:
            if prop not in schema_props:
                result.missing_required.append(prop)
                result.issues.append(SchemaValidationIssue(
                    severity="warning",
                    code="missing_required_property",
                    message=f"Missing required property for {result.schema_type}: '{prop}'",
                    property=prop,
                    expected="Required for Google Rich Result eligibility",
                    actual="missing",
                ))

        # Check missing recommended
        for prop in recommended:
            if prop not in schema_props:
                result.missing_recommended.append(prop)
                result.issues.append(SchemaValidationIssue(
                    severity="info",
                    code="missing_recommended_property",
                    message=f"Missing recommended property for {result.schema_type}: '{prop}'",
                    property=prop,
                    expected="Recommended for enhanced Rich Result",
                    actual="missing",
                ))

    def _extract_all_properties(self, schema: SchemaData) -> set[str]:
        """Extract all property names from schema (handles nested structures)."""
        props = set()
        parsed = schema.parsed

        if isinstance(parsed, dict):
            self._collect_properties(parsed, props)
        elif isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    self._collect_properties(item, props)

        # Also check Microdata/RDFa properties in attributes
        attrs = schema.attributes
        if "properties" in attrs:
            for prop in attrs["properties"]:
                if isinstance(prop, dict) and "property" in prop:
                    props.add(prop["property"])

        return props

    def _collect_properties(self, obj: dict, props: set[str], prefix: str = "") -> None:
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

    def _validate_property_formats(self, schema: SchemaData, result: SchemaValidationResult) -> None:
        """Validate property value formats."""
        if not schema.parsed:
            return

        props_to_check = {}
        if isinstance(schema.parsed, dict):
            props_to_check = schema.parsed
        elif isinstance(schema.parsed, list):
            for item in schema.parsed:
                if isinstance(item, dict):
                    props_to_check.update(item)

        for prop_name, validator in self.FORMAT_VALIDATORS.items():
            if prop_name in props_to_check:
                value = props_to_check[prop_name]
                if value and not validator(value):
                    result.issues.append(SchemaValidationIssue(
                        severity="warning",
                        code="invalid_property_format",
                        message=f"Invalid format for property '{prop_name}': '{value}'",
                        property=prop_name,
                        expected=self._get_format_description(prop_name),
                        actual=str(value),
                    ))

    def _get_format_description(self, prop_name: str) -> str:
        """Get expected format description for a property."""
        formats = {
            "datePublished": "ISO 8601 date (YYYY-MM-DD)",
            "dateModified": "ISO 8601 date (YYYY-MM-DD)",
            "datePosted": "ISO 8601 date (YYYY-MM-DD)",
            "startDate": "ISO 8601 date (YYYY-MM-DD)",
            "endDate": "ISO 8601 date (YYYY-MM-DD)",
            "validThrough": "ISO 8601 date (YYYY-MM-DD)",
            "uploadDate": "ISO 8601 date (YYYY-MM-DD)",
            "foundingDate": "ISO 8601 date (YYYY-MM-DD)",
            "releaseDate": "ISO 8601 date (YYYY-MM-DD)",
            "birthDate": "ISO 8601 date (YYYY-MM-DD)",
            "deathDate": "ISO 8601 date (YYYY-MM-DD)",
            "url": "Valid URL",
            "image": "Valid image URL",
            "logo": "Valid image URL",
            "thumbnailUrl": "Valid image URL",
            "contentUrl": "Valid URL",
            "embedUrl": "Valid URL",
            "installUrl": "Valid URL",
            "sameAs": "Valid URL",
            "email": "Valid email address",
            "telephone": "Valid phone number",
            "price": "Numeric price (e.g., 29.99)",
            "priceCurrency": "ISO 4217 currency code (e.g., USD)",
            "ratingValue": "Number between 0-5 (or bestRating)",
            "bestRating": "Number (typically 5)",
            "worstRating": "Number (typically 1)",
            "reviewCount": "Integer",
            "ratingCount": "Integer",
            "offerCount": "Integer",
        }
        return formats.get(prop_name, "Valid value")

    @staticmethod
    def _is_iso_date(value: str) -> bool:
        """Check if value is ISO 8601 date."""
        if not isinstance(value, str):
            return False
        # Basic check for YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
        import re
        return bool(re.match(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?$", value))

    @staticmethod
    def _is_url(value: str) -> bool:
        """Check if value is a valid URL."""
        if not isinstance(value, str):
            return False
        return value.startswith(("http://", "https://", "//"))

    @staticmethod
    def _is_email(value: str) -> bool:
        """Check if value is a valid email."""
        if not isinstance(value, str):
            return False
        import re
        return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", value))

    @staticmethod
    def _is_phone(value: str) -> bool:
        """Check if value is a valid phone number."""
        if not isinstance(value, str):
            return False
        import re
        # Basic phone pattern
        return bool(re.match(r"^[\+]?[\d\s\-\(\)]{7,}$", value))

    @staticmethod
    def _is_price(value: Any) -> bool:
        """Check if value is a valid price."""
        if isinstance(value, (int, float)):
            return value >= 0
        if isinstance(value, str):
            try:
                float(value.replace(",", ""))
                return True
            except ValueError:
                return False
        return False

    @staticmethod
    def _is_currency(value: str) -> bool:
        """Check if value is valid ISO 4217 currency code."""
        if not isinstance(value, str):
            return False
        return len(value) == 3 and value.isalpha() and value.isupper()

    @staticmethod
    def _is_rating(value: Any) -> bool:
        """Check if value is a valid rating number."""
        if isinstance(value, (int, float)):
            return 0 <= value <= 10
        if isinstance(value, str):
            try:
                num = float(value)
                return 0 <= num <= 10
            except ValueError:
                return False
        return False

    @staticmethod
    def _is_int(value: Any) -> bool:
        """Check if value is a valid integer."""
        if isinstance(value, int):
            return value >= 0
        if isinstance(value, str):
            try:
                int(value)
                return True
            except ValueError:
                return False
        return False

    def _check_duplicates(self, schema: SchemaData, result: SchemaValidationResult) -> None:
        """Check for duplicate entities within same schema."""
        # Check for duplicate @id
        if schema.parsed:
            ids = self._collect_ids(schema.parsed)
            if ids:
                id_counts = Counter(ids)
                duplicates = [id_val for id_val, count in id_counts.items() if count > 1]
                if duplicates:
                    result.duplicate_entities = duplicates
                    for dup in duplicates:
                        result.issues.append(SchemaValidationIssue(
                            severity="info",
                            code="duplicate_entity_id",
                            message=f"Duplicate @id found: '{dup}'",
                            property="@id",
                            expected="Unique @id per entity",
                            actual=f"Appears {id_counts[dup]} times",
                        ))

    def _collect_ids(self, obj: dict | list, ids: list[str] = None) -> list[str]:
        """Recursively collect @id values."""
        if ids is None:
            ids = []
        if isinstance(obj, dict):
            if "@id" in obj:
                ids.append(obj["@id"])
            for value in obj.values():
                if isinstance(value, (dict, list)):
                    self._collect_ids(value, ids)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    self._collect_ids(item, ids)
        return ids

    def _check_cross_schema_issues(self) -> None:
        """Check for issues across all schemas on the page."""
        # Group schemas by type
        type_groups: dict[str, list[SchemaData]] = {}
        for schema in self._all_parsed_schemas:
            if schema.validation and schema.validation.schema_type:
                t = schema.validation.schema_type
                type_groups.setdefault(t, []).append(schema)

        # Check for conflicting entities of same type
        for schema_type, schemas in type_groups.items():
            if len(schemas) > 1:
                for schema in schemas:
                    if schema.validation:
                        schema.validation.issues.append(SchemaValidationIssue(
                            severity="info",
                            code="multiple_entities_same_type",
                            message=f"Multiple {schema_type} entities found on page ({len(schemas)} total)",
                            property="@type",
                            expected="Single entity per type (typically)",
                            actual=f"{len(schemas)} entities of type {schema_type}",
                        ))

    def check_content_consistency(self, schema: SchemaData, visible_content: dict) -> list[SchemaValidationIssue]:
        """
        Check if schema data is consistent with visible page content.
        This is a basic check - can be extended with more sophisticated NLP.
        """
        issues = []
        if not schema.parsed or not isinstance(schema.parsed, dict):
            return issues

        # Check headline vs page title
        if "headline" in schema.parsed:
            schema_headline = schema.parsed["headline"]
            page_title = visible_content.get("title", "")
            if page_title and schema_headline != page_title:
                issues.append(SchemaValidationIssue(
                    severity="info",
                    code="content_inconsistency_headline",
                    message=f"Schema headline differs from page title",
                    property="headline",
                    expected=f"Match page title: '{page_title[:100]}'",
                    actual=f"'{schema_headline[:100]}'",
                ))

        # Check description vs meta description
        if "description" in schema.parsed:
            schema_desc = schema.parsed["description"]
            meta_desc = visible_content.get("meta_description", "")
            if meta_desc and schema_desc != meta_desc:
                issues.append(SchemaValidationIssue(
                    severity="info",
                    code="content_inconsistency_description",
                    message=f"Schema description differs from meta description",
                    property="description",
                    expected=f"Match meta description: '{meta_desc[:100]}'",
                    actual=f"'{schema_desc[:100]}'",
                ))

        return issues