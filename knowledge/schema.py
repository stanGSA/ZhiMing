from pydantic import BaseModel, ConfigDict, Field, model_validator

from knowledge.review import ModelReview, ReviewStatus


class SourceEntry(BaseModel):
    """An entry as authored in knowledge/sources; review fields are not authored."""

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
    # A person reviewed this entry. Only a person sets it; model review never does.
    reviewed: bool
    version: int = Field(ge=1)


class Entry(SourceEntry):
    """A built entry: review fields derived by knowledge.build from ``reviewed`` and the ledger."""

    review_status: ReviewStatus = "draft"
    model_review: ModelReview | None = None

    @model_validator(mode="after")
    def consistent_review(self):
        if self.reviewed != (self.review_status == "human_reviewed"):
            raise ValueError(f"reviewed 只表示人工审核，与 review_status 不一致：{self.id}")
        if self.review_status == "model_reviewed" and self.model_review is None:
            raise ValueError(f"模型交叉审核缺少审核记录：{self.id}")
        return self
