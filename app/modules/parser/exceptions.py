class ParserError(Exception):
    """Base parser error."""


class HTMLParseError(ParserError):
    """Raised when HTML cannot be parsed."""


class ExtractionError(ParserError):
    """Raised when an extractor fails on a specific element."""

    def __init__(self, extractor: str, message: str, element: str = ""):
        self.extractor = extractor
        self.element = element
        super().__init__(f"[{extractor}] {message}" + (f" (element: {element})" if element else ""))


class PartialParseError(ParserError):
    """Raised when parsing completes with recoverable errors."""

    def __init__(self, message: str, errors: list | None = None):
        self.errors = errors or []
        super().__init__(message)
