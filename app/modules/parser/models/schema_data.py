from pydantic import BaseModel, Field
from typing import Any


class SchemaData(BaseModel):
    format: str

    raw: str = ""

    parsed: Any = None

    types: list[str] = Field(default_factory=list)

    context: str = ""

    attributes: dict[str, Any] = Field(default_factory=dict)
