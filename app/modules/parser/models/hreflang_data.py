from pydantic import BaseModel, Field, model_validator


class HreflangData(BaseModel):
    href: str = ""
    hreflang: str = ""
    rel: list[str] = Field(default_factory=list)

    is_x_default: bool = False

    @model_validator(mode="after")
    def _compute_x_default(self):
        self.is_x_default = self.hreflang.lower() == "x-default"
        return self
