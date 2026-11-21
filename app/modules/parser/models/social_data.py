from pydantic import BaseModel, Field
from typing import List, Optional


class OpenGraphData(BaseModel):
    tags: dict[str, list[str]] = Field(default_factory=dict)


class TwitterCardData(BaseModel):
    tags: dict[str, list[str]] = Field(default_factory=dict)


class SocialLink(BaseModel):
    platform: str = Field(..., description="Social platform name (e.g., facebook, twitter)")
    url: str = Field(..., description="URL to the social profile")
    text: Optional[str] = Field(None, description="Link text/anchor")


class SharingButton(BaseModel):
    platform: str = Field(..., description="Social platform for sharing")
    selector: str = Field(..., description="CSS selector or identifier for the button")
    url: Optional[str] = Field(None, description="Share URL if present in button")
    text: Optional[str] = Field(None, description="Button text")


class SocialData(BaseModel):
    open_graph: OpenGraphData = Field(default_factory=OpenGraphData)
    twitter: TwitterCardData = Field(default_factory=TwitterCardData)
    social_links: List[SocialLink] = Field(default_factory=list)
    sharing_buttons: List[SharingButton] = Field(default_factory=list)