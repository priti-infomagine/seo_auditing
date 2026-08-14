from pydantic import BaseModel, Field


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
