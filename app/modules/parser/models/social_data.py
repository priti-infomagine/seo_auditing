from pydantic import BaseModel, Field


class OpenGraphData(BaseModel):
    tags: dict[str, list[str]] = Field(default_factory=dict)


class TwitterCardData(BaseModel):
    tags: dict[str, list[str]] = Field(default_factory=dict)


class SocialData(BaseModel):
    open_graph: OpenGraphData = Field(default_factory=OpenGraphData)
    twitter: TwitterCardData = Field(default_factory=TwitterCardData)
