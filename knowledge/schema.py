from pydantic import BaseModel, ConfigDict, Field


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    system: str
    kind: str
    key: str
    synonyms: list[str] = Field(default_factory=list)
    keywords: list[str]
    theme_map: dict[str, float]
    text: str = Field(min_length=10)
    source: str
    license: str
    reviewed: bool
    version: int = Field(ge=1)
