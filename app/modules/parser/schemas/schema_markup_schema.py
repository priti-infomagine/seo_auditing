from pydantic import BaseModel, Field
from typing import Any, Dict, List


class SchemaMarkupSchema(BaseModel):
    format: str
    raw: str = ""
    types: List[str] = Field(default_factory=list)
    context: str = ""
    attributes: Dict[str, Any] = Field(default_factory=dict)
