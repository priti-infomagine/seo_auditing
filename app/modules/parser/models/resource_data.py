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

    attributes: dict[str, str] = Field(default_factory=dict)
