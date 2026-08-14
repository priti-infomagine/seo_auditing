from pydantic import BaseModel, Field


class LinkData(BaseModel):
    href: str = ""
    text: str = ""

    rel: list[str] = Field(default_factory=list)

    target: str = ""
    title: str = ""

    download: str = ""

    absolute_url: str = ""

    attributes: dict[str, str] = Field(default_factory=dict)
