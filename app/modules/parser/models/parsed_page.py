from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.parser.models.content_data import ContentData, HeadingData
from app.modules.parser.models.hreflang_data import HreflangData
from app.modules.parser.models.image_data import ImageData
from app.modules.parser.models.link_data import LinkData
from app.modules.parser.models.page_metadata import PageMetadata
from app.modules.parser.models.resource_data import ResourceData
from app.modules.parser.models.schema_data import SchemaData
from app.modules.parser.models.social_data import SocialData
from app.modules.parser.models.technical_data import TechnicalData


class PageIdentity(BaseModel):
    url: str = ""
    doctype: str = ""
    language: str = ""
    charset: str = ""
    html_size: int = 0


class ParserMetadata(BaseModel):
    parser_version: str = "1.0"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ParsedPage(BaseModel):
    document: PageIdentity = Field(default_factory=PageIdentity)
    metadata: PageMetadata | None = None
    content: ContentData | None = None
    headings: list[HeadingData] = Field(default_factory=list)
    links: list[LinkData] = Field(default_factory=list)
    images: list[ImageData] = Field(default_factory=list)
    schemas: list[SchemaData] = Field(default_factory=list)
    hreflang: list[HreflangData] = Field(default_factory=list)
    social: SocialData | None = None
    resources: list[ResourceData] = Field(default_factory=list)
    technical: TechnicalData | None = None
    parser_metadata: ParserMetadata = Field(default_factory=ParserMetadata)

    @property
    def structured_data(self) -> list[SchemaData]:
        return self.schemas

    @property
    def warnings(self) -> list[str]:
        return self.parser_metadata.warnings

    @property
    def errors(self) -> list[str]:
        return self.parser_metadata.errors
