from pydantic import BaseModel, Field


class HeadingData(BaseModel):
    level: int
    text: str = ""
    position: int = 0


class ParagraphData(BaseModel):
    text: str = ""


class ListData(BaseModel):
    ordered: bool = False
    items: list[str] = Field(default_factory=list)


class TableData(BaseModel):
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class SemanticElement(BaseModel):
    tag: str = ""
    text: str = ""


class FormFieldData(BaseModel):
    tag: str = ""
    type: str = ""
    name: str = ""
    id: str = ""
    label_text: str = ""
    has_label_for: bool = False
    has_wrapping_label: bool = False
    aria_label: str = ""
    aria_labelledby: str = ""
    aria_describedby: str = ""
    required: bool = False
    disabled: bool = False
    readonly: bool = False
    placeholder: str = ""
    title: str = ""
    accessible_name: str = ""
    accessible_name_source: str = ""


class FormData(BaseModel):
    action: str = ""
    method: str = ""
    id: str = ""
    name: str = ""
    fields: list[FormFieldData] = Field(default_factory=list)
    fieldsets: list[dict] = Field(default_factory=list)


class ButtonData(BaseModel):
    tag: str = ""
    type: str = ""
    id: str = ""
    name: str = ""
    text_content: str = ""
    value: str = ""
    aria_label: str = ""
    aria_labelledby: str = ""
    title: str = ""
    accessible_name: str = ""
    accessible_name_source: str = ""
    has_accessible_name: bool = False


class SkipLinkData(BaseModel):
    href: str = ""
    text: str = ""
    is_first_focusable: bool = False
    position: int = 0


class LandmarkData(BaseModel):
    type: str = ""
    element: str = ""
    role: str = ""
    aria_label: str = ""
    aria_labelledby: str = ""
    has_accessible_name: bool = False


class ContentData(BaseModel):
    text: str = ""
    normalized_text: str = ""

    word_count: int = 0
    character_count: int = 0
    sentence_count: int = 0
    paragraph_count: int = 0
    text_html_ratio: float = 0.0

    paragraphs: list[ParagraphData] = Field(default_factory=list)
    headings: list[HeadingData] = Field(default_factory=list)
    lists: list[ListData] = Field(default_factory=list)
    tables: list[TableData] = Field(default_factory=list)

    semantic_elements: list[SemanticElement] = Field(default_factory=list)

    has_main: bool = False
    has_article: bool = False
    has_header: bool = False
    has_footer: bool = False
    has_nav: bool = False

    forms: list[FormData] = Field(default_factory=list)
    buttons: list[ButtonData] = Field(default_factory=list)
    skip_links: list[SkipLinkData] = Field(default_factory=list)
    landmarks: list[LandmarkData] = Field(default_factory=list)
    aria_attributes: dict = Field(default_factory=dict)