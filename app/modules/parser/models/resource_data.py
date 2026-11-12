from pydantic import BaseModel, Field
from typing import Any


class ResourceData(BaseModel):
    resource_type: str
    url: str = ""

    tag: str = ""

    alt: str = ""
    title: str = ""

    width: str = ""
    height: str = ""

    loading: str = ""
    decoding: str = ""

    srcset: str = ""
    sizes: str = ""

    rel: list[str] = Field(default_factory=list)

    # New fields for performance rules
    async_attr: bool = False
    defer_attr: bool = False
    module_attr: bool = False
    fetchpriority: str = ""
    media: str = ""
    size_kb: float = 0.0

    attributes: dict[str, str] = Field(default_factory=dict)
