"""
Error handling for the Core SEO crawler pipeline.

Provides:
    CoreSEOError        — base exception
    CrawlError          — crawling failures
    ValidationError     — input/config validation failures
    register_validation_handler — FastAPI exception handler registration
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError as RequestValidationError

if TYPE_CHECKING:
    from fastapi import FastAPI


class CoreSEOError(Exception):
    """Base exception for all Core SEO module errors."""

    def __init__(self, message: str = "", *, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class CrawlError(CoreSEOError):
    """Raised when crawling a page fails."""

    def __init__(self, message: str = "", *, url: str = "", status_code: int = 502):
        super().__init__(message or "Crawl failed", status_code=status_code)
        self.url = url


class ValidationError(CoreSEOError):
    """Raised when configuration or input validation fails."""

    def __init__(self, message: str = "", *, field: str = ""):
        super().__init__(message or "Validation failed", status_code=400)
        self.field = field


def register_validation_handler(app: FastAPI) -> None:
    """Register exception handlers on the FastAPI app."""
    @app.exception_handler(CoreSEOError)
    async def core_seo_error_handler(request: Request, exc: CoreSEOError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.__class__.__name__,
                "message": exc.message,
                "detail": {
                    "path": str(request.url),
                    **({"url": exc.url} if isinstance(exc, CrawlError) and exc.url else {}),
                    **({"field": exc.field} if isinstance(exc, ValidationError) and exc.field else {}),
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "ValidationError",
                "message": "Request validation failed",
                "detail": exc.errors(),
            },
        )


__all__ = [
    "CoreSEOError",
    "CrawlError",
    "ValidationError",
    "register_validation_handler",
]
