from pydantic import BaseModel, Field
class ImageData(BaseModel):
    resource_type: str = "image"
    url: str = ""
    tag: str = "img"

    alt: str = ""
    title: str = ""

    width: str = ""
    height: str = ""

    loading: str = ""
    decoding: str = ""

    srcset: str = ""
    sizes: str = ""

    attributes: dict[str, str] = Field(default_factory=dict)
