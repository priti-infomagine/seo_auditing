from typing import Any, Dict, List

from pydantic import BaseModel, Field


class StructuredDataItem(BaseModel):
    format: str

    raw: str = ""

    parsed: Any = None

    types: List[str] = Field(default_factory=list)

    context: str = ""

    attributes: Dict[str, Any] = Field(default_factory=dict)