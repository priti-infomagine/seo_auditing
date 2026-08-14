from pydantic import BaseModel, Field


class MetaTag(BaseModel):
    name: str = ""
    property: str = ""
    content: str = ""
    http_equiv: str = ""


class HreflangLink(BaseModel):
    href: str = ""
    hreflang: str = ""
    rel: list[str] = Field(default_factory=list)


class PageMetadata(BaseModel):
    title: str = ""
    title_length: int = 0
    meta_description: str = ""
    meta_description_length: int = 0

    robots: list[MetaTag] = Field(default_factory=list)
    googlebot: str = ""

    viewport: str = ""
    charset: str = ""
    language: str = ""

    canonical: str = ""

    hreflang: list[HreflangLink] = Field(default_factory=list)

    open_graph: dict[str, list[str]] = Field(default_factory=dict)
    twitter: dict[str, list[str]] = Field(default_factory=dict)

    meta_tags: list[MetaTag] = Field(default_factory=list)

    favicon_urls: list[str] = Field(default_factory=list)
