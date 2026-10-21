"""Review levels of knowledge entries and the model-review ledger.

``reviewed`` in a source entry keeps its old meaning: a person reviewed it, and only a person
sets it. Model cross-review is recorded separately, in ``knowledge/reviews/<system>.yaml``:
one approval per entry id, bound to the SHA256 of the entry's reviewable content. Editing an
entry, or regenerating it with ``scripts/draft_*.py``, changes the hash, so the approval no
longer applies and the entry is a draft again; the ledger itself is never rewritten by the
draft scripts.

``review_status`` is derived once, at build time, and copied into every meaning and signal.
Readers go through ``review_status()`` so that editions and saved readings from before the
three levels existed (``reviewed`` only) keep working.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ReviewStatus = Literal["draft", "model_reviewed", "human_reviewed"]
# Lowest first: a combination is only as reviewed as its least reviewed part.
LEVELS: tuple[str, ...] = ("draft", "model_reviewed", "human_reviewed")
# The fields a reviewer judges. ``reviewed`` and the derived review fields are not content.
CONTENT_FIELDS = (
    "id",
    "system",
    "kind",
    "key",
    "synonyms",
    "keywords",
    "theme_map",
    "text",
    "source",
    "license",
    "version",
)
LEDGER_SCHEMA = 1


def review_status(item: dict) -> str:
    """Review level of an entry, meaning, signal or merge side; tolerant of older data."""
    value = item.get("review_status")
    if value in LEVELS:
        return value
    return "human_reviewed" if item.get("reviewed") is True else "draft"


def lowest(levels) -> str:
    """The least reviewed level; like ``all()``, nothing to combine is no restriction."""
    return min(levels, key=LEVELS.index, default="human_reviewed")


def normalize_entry(entry: dict) -> dict:
    """Fill ``review_status`` for an entry read from an edition built before it existed."""
    entry["review_status"] = review_status(entry)
    return entry


def content_hash(entry: dict) -> str:
    """SHA256 of the reviewable content: any edit, numbers included, voids an approval."""
    content = {field: entry[field] for field in CONTENT_FIELDS}
    payload = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


class ReviewerVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vendor: str = Field(min_length=1)
    model: str = Field(min_length=1)
    returned_model: str | None = None
    verdict: Literal["pass"]
    issues: list[str] = Field(default_factory=list)


class ModelReview(BaseModel):
    """What a meaning carries about its model cross-review (never a human review)."""

    model_config = ConfigDict(extra="forbid")
    reviewers: list[ReviewerVerdict] = Field(min_length=2, max_length=2)
    date: str
    report: str = Field(min_length=1)

    @field_validator("date")
    @classmethod
    def iso_date(cls, value):
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def two_vendors(self):
        vendors = {r.vendor.strip().lower() for r in self.reviewers}
        if len(vendors) != 2:
            raise ValueError("模型交叉审核须由两家不同厂商完成")
        return self


class LedgerRecord(ModelReview):
    id: str
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Ledger(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    system: str
    records: list[LedgerRecord] = Field(default_factory=list)


def load_ledgers(reviews_dir: Path) -> dict[str, LedgerRecord]:
    """Approvals by entry id. One record per id; the ledger never holds human reviews."""
    approvals: dict[str, LedgerRecord] = {}
    for path in sorted(reviews_dir.glob("*.yaml")) if reviews_dir.is_dir() else []:
        ledger = Ledger.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if path.stem != ledger.system:
            raise ValueError(f"审核账本文件名与体系不一致：{path.name}")
        for record in ledger.records:
            if not record.id.startswith(f"kb:{ledger.system}:"):
                raise ValueError(f"审核账本记录不属于该体系：{record.id}")
            if record.id in approvals:
                raise ValueError(f"审核账本记录重复：{record.id}")
            approvals[record.id] = record
    return approvals


def approval(entry: dict, reviewers: list[dict], day: str, report: str) -> dict:
    """A ledger record for an entry both reviewers passed, bound to its current content."""
    record = LedgerRecord(
        id=entry["id"],
        content_sha256=content_hash(entry),
        reviewers=reviewers,
        date=day,
        report=report,
    )
    return record.model_dump()


def write_ledger(reviews_dir: Path, system: str, records: list[dict]) -> Path:
    """Replace one system's ledger; records are validated and kept in id order."""
    ledger = Ledger(schema_version=LEDGER_SCHEMA, system=system, records=records)
    path = reviews_dir / f"{system}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = ledger.model_dump()
    data["records"] = sorted(data["records"], key=lambda r: r["id"])
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    temporary.replace(path)
    return path


def resolve(entry: dict, approvals: dict[str, LedgerRecord]) -> tuple[str, dict | None, str]:
    """(review_status, model_review, ledger state) of one source entry.

    The ledger state is ``none``, ``current`` or ``stale`` (an approval of other content).
    """
    record = approvals.get(entry["id"])
    state = "none" if record is None else "stale"
    if record is not None and record.content_sha256 == content_hash(entry):
        state = "current"
    model_review = (
        record.model_dump(exclude={"id", "content_sha256"}) if state == "current" else None
    )
    if entry["reviewed"]:
        return "human_reviewed", model_review, state
    if model_review:
        return "model_reviewed", model_review, state
    return "draft", None, state
