from pydantic import BaseModel, Field
from typing import Any


class InlineJSData(BaseModel):
    """Extracted inline JavaScript block data."""
    content: str = ""
    size_kb: float = 0.0
    whitespace_percentage: float = 0.0
    is_minified: bool = False
    attributes: dict[str, str] = Field(default_factory=dict)