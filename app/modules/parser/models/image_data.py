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

    # New fields for performance rules
    fetchpriority: str = ""
    is_gif: bool = False

    attributes: dict[str, str] = Field(default_factory=dict)
