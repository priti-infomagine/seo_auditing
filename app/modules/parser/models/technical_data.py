from pydantic import BaseModel, Field


class IframeData(BaseModel):
    src: str = ""
    title: str = ""
    name: str = ""
    id: str = ""
    sandbox: str = ""
    allow: str = ""
    has_title: bool = False


class TechnicalData(BaseModel):
    doctype: str = ""
    html_lang: str = ""
    charset: str = ""
    viewport: str = ""

    base_tag: str = ""

    meta_refresh: str = ""

    iframe_count: int = 0
    script_count: int = 0
    style_count: int = 0

    inline_scripts: int = 0
    inline_styles: int = 0

    external_resource_count: int = 0

    # New field for DOM size rule
    dom_elements: int = 0

    # New fields for accessibility
    iframes: list[IframeData] = Field(default_factory=list)
    viewport_zoom_allows: bool = True