from typing import Dict, List

from pydantic import BaseModel, Field


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

    rel: List[str] = Field(default_factory=list)

    attributes: Dict[str, str] = Field(default_factory=dict)