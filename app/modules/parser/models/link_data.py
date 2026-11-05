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
    
    # Raw/unmodified values for rules that need original HTML
    raw_href: str = ""
    raw_attributes: dict[str, str] = Field(default_factory=dict)
