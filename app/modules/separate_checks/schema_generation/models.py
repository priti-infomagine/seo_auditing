from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List

# Base structure shared by all schema types
class OrganizationSchema(BaseModel):
    name: str
    url: HttpUrl
    logo: HttpUrl
    sameAs: Optional[List[HttpUrl]] = Field(default=None, description="Social media links")

class ArticleSchema(BaseModel):
    title: str = Field(..., alias="headline")
    imageUrl: HttpUrl = Field(..., alias="image")
    datePublished: str
    authorName: str
    publisherName: str
    publisherLogo: HttpUrl
