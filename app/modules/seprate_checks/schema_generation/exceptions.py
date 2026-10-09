class SchemaGenerationError(Exception):
    """Raised when schema generation fails."""

    pass


class SchemaAuditError(Exception):
    """Raised when schema audit fails."""

    pass


class InvalidSchemaTypeError(ValueError):
    """Raised when an unsupported schema type is requested."""

    pass


class InvalidArticleSubTypeError(ValueError):
    """Raised when an unsupported article subtype is requested."""

    pass


class ValidationError(ValueError):
    """Raised when input validation fails."""

    pass