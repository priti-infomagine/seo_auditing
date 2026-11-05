from pydantic import BaseModel, Field
from typing import Any


class SchemaValidationIssue(BaseModel):
    """Represents a single validation issue found in schema markup."""
    severity: str  # "error", "warning", "info"
    code: str      # Machine-readable code (e.g., "missing_required_property")
    message: str   # Human-readable message
    property: str | None = None  # Property name if applicable
    expected: str | None = None  # Expected value/type
    actual: str | None = None    # Actual value found


class SchemaValidationResult(BaseModel):
    """Complete validation result for a schema item."""
    has_schema: bool = False
    is_valid_json_ld: bool = True
    has_context: bool = False
    has_type: bool = False
    schema_type: str | None = None
    is_known_type: bool = False
    is_google_rich_result: bool = False
    issues: list[SchemaValidationIssue] = Field(default_factory=list)
    required_properties: list[str] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)
    recommended_properties: list[str] = Field(default_factory=list)
    missing_recommended: list[str] = Field(default_factory=list)
    duplicate_entities: list[str] = Field(default_factory=list)
    content_consistency_issues: list[str] = Field(default_factory=list)


class SchemaData(BaseModel):
    format: str

    raw: str = ""

    parsed: Any = None

    types: list[str] = Field(default_factory=list)

    context: str = ""

    attributes: dict[str, Any] = Field(default_factory=dict)

    # Validation results (populated by SchemaValidator)
    validation: SchemaValidationResult | None = None
