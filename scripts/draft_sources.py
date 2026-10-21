"""Keep source edits made during review when an authoring helper is rerun."""

from pathlib import Path

import yaml

from knowledge.schema import SourceEntry


def write_drafts(target: Path, entries: list[dict]) -> None:
    if target.exists():
        current = yaml.safe_load(target.read_text(encoding="utf-8"))
        normalize = lambda rows: {  # noqa: E731
            row.id: row.model_dump() for row in map(SourceEntry.model_validate, rows)
        }
        if normalize(current["entries"]) != normalize(entries):
            raise ValueError(f"拒绝覆盖已编辑的知识源：{target}；请将修订保留在源文件中")
        return  # Identical regeneration also preserves the original YAML bytes.
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(
            dict(status="draft_needs_human_review", entries=entries),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
