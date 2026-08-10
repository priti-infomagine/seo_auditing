from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ParserIssue(BaseModel):
    level: str
    message: str


class DocumentInfo(BaseModel):
    url: str = ""
    doctype: str = ""
    language: str = ""
    charset: str = ""
    html_size: int = 0


class ParsedDocument(BaseModel):
    document: DocumentInfo = Field(default_factory=DocumentInfo)

    metadata: Optional[Any] = None
    content: Optional[Any] = None
    links: List[Any] = Field(default_factory=list)
    resources: List[Any] = Field(default_factory=list)
    structured_data: List[Any] = Field(default_factory=list)

    warnings: List[ParserIssue] = Field(default_factory=list)
    errors: List[ParserIssue] = Field(default_factory=list)

    parser_version: str = "1.0"