from pydantic import BaseModel, Field


class ImageData(BaseModel):
    resource_type: str = "image"
    url: str = ""
    tag: str = ""

    alt: str = ""
    title: str = ""

    width: str = ""
    height: str = ""

    loading: str = ""
    decoding: str = ""

    srcset: str = ""
    sizes: str = ""

    fetchpriority: str = ""
    is_gif: bool = False

    # ── New fields for extended image SEO rules ──────────────────────
    is_decorative: bool = False       # alt="" (empty string)
    has_srcset: bool = False          # pre-computed flag
    has_sizes: bool = False           # pre-computed flag
    has_picture_parent: bool = False  # wrapped in <picture>
    is_background_image: bool = False # extracted from CSS background-image
    parent_tag: str = ""              # tag name of the parent element
    natural_width: int = 0            # intrinsic pixel width (from response)
    natural_height: int = 0           # intrinsic pixel height (from response)
    content_type: str = ""            # MIME type from HTTP response
    file_size_bytes: int = 0          # Content-Length from HTTP response
    http_status: int = 0              # HTTP status code of the image URL

    attributes: dict[str, str] = Field(default_factory=dict)