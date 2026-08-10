from typing import List

from pydantic import BaseModel, Field


class LinkData(BaseModel):
    href: str = ""
    text: str = ""

    rel: List[str] = Field(default_factory=list)

    target: str = ""
    title: str = ""

    download: str = ""

    absolute_url: str = ""

    attributes: dict = Field(default_factory=dict)