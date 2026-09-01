from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User question about the SEO audit")


class ChatReference(BaseModel):
    type: str = Field(..., description="Reference type: rule, page, or category")
    rule_id: str | None = Field(None, description="Rule identifier when type is rule")
    page_url: str | None = Field(None, description="Page URL when type is page")
    category: str | None = Field(None, description="Category id when type is category")


class ChatResponse(BaseModel):
    project_id: str
    audit_id: str | None = None
    answer: str
    references: list[ChatReference] = Field(default_factory=list)
