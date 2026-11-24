from pydantic import BaseModel, Field


class LinkData(BaseModel):
    href: str = ""
    text: str = ""
    # Accessible name per WCAG 2.1 (aria-label > aria-labelledby > title > link text)
    accessible_name: str = ""
    aria_label: str = ""
    aria_labelledby: str = ""
    # Internal/external classification
    is_internal: bool = True
    is_external: bool = False

    rel: list[str] = Field(default_factory=list)

    target: str = ""
    title: str = ""

    download: str = ""

    absolute_url: str = ""

    attributes: dict[str, str] = Field(default_factory=dict)

    # Raw/unmodified values for rules that need original HTML
    raw_href: str = ""
    raw_attributes: dict[str, str] = Field(default_factory=dict)
