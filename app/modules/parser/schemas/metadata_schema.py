from typing import Dict, List

from pydantic import BaseModel, Field


class MetaTag(BaseModel):
    name: str = ""
    property: str = ""
    content: str = ""
    http_equiv: str = ""


class HreflangLink(BaseModel):
    href: str = ""
    hreflang: str = ""
    rel: List[str] = Field(default_factory=list)


class MetadataData(BaseModel):
    title: str = ""
    title_length: int = 0
    meta_description: str = ""
    meta_description_length: int = 0

    robots: List[MetaTag] = Field(default_factory=list)
    googlebot: str = ""

    viewport: str = ""
    charset: str = ""
    language: str = ""

    canonical: str = ""

    hreflang: List[HreflangLink] = Field(default_factory=list)

    open_graph: Dict[str, List[str]] = Field(default_factory=dict)
    twitter: Dict[str, List[str]] = Field(default_factory=dict)

    meta_tags: List[MetaTag] = Field(default_factory=list)

    favicon_urls: List[str] = Field(default_factory=list)
