from typing import List

from pydantic import BaseModel, Field


class HeadingData(BaseModel):
    level: int
    text: str
    position: int = 0


class ParagraphData(BaseModel):
    text: str


class ListData(BaseModel):
    ordered: bool
    items: List[str] = Field(default_factory=list)


class TableData(BaseModel):
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)


class SemanticElement(BaseModel):
    tag: str
    text: str = ""


class ContentData(BaseModel):
    text: str = ""
    normalized_text: str = ""

    word_count: int = 0
    character_count: int = 0
    sentence_count: int = 0
    paragraph_count: int = 0
    text_html_ratio: float = 0.0

    paragraphs: List[ParagraphData] = Field(default_factory=list)
    headings: List[HeadingData] = Field(default_factory=list)
    lists: List[ListData] = Field(default_factory=list)
    tables: List[TableData] = Field(default_factory=list)

    semantic_elements: List[SemanticElement] = Field(default_factory=list)

    has_main: bool = False
    has_article: bool = False
    has_header: bool = False
    has_footer: bool = False
    has_nav: bool = False
