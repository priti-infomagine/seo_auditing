from pydantic import BaseModel, Field
from typing import Any


class HeadData(BaseModel):
    """Extracted data from <head> element."""
    preconnect_hints: list[dict[str, Any]] = Field(default_factory=list)
    dns_prefetch_hints: list[dict[str, Any]] = Field(default_factory=list)
    preload_hints: list[dict[str, Any]] = Field(default_factory=list)
    google_fonts_urls: list[dict[str, Any]] = Field(default_factory=list)
    meta_http_equiv: dict[str, str] = Field(default_factory=dict)