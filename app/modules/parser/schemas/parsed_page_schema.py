from pydantic import BaseModel, Field
from typing import Optional


class ParsedPageResponse(BaseModel):
    url: str = ""
    doctype: str = ""
    language: str = ""
    charset: str = ""
    html_size: int = 0

    title: str = ""
    title_length: int = 0
    meta_description: str = ""
    meta_description_length: int = 0
    canonical: str = ""
    viewport: str = ""
    robots: list[dict] = Field(default_factory=list)

    word_count: int = 0
    character_count: int = 0
    sentence_count: int = 0
    paragraph_count: int = 0
    headings: list[dict] = Field(default_factory=list)

    total_links: int = 0
    total_resources: int = 0
    structured_data_items: int = 0
