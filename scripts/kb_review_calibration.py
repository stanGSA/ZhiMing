"""A frozen, labelled calibration set for the knowledge review (stage 1, second campaign).

Each item is a complete entry, shown to the reviewers exactly like a real one, with a label
they never see: ``pass`` (usable as is under the rubric anchors) or ``fail`` (one stated
defect). About half of each system's items fail, so the two reviewers' agreement on this set
measures whether they tell defects apart, not how often entries happen to pass (the 2026-10-21
kappa collapsed when nine in ten real entries passed). The owner confirms every label;
``freeze`` then records the hash, and a campaign can use only the exact items it covers.

    python -m scripts.kb_review_calibration show   --calibration <file>  # 确认用表格
    python -m scripts.kb_review_calibration freeze --calibration <file> --confirmed-by <姓名>
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

from knowledge.schema import SourceEntry

SCHEMA = 1
LABELS = ("pass", "fail")


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def lock_path(path: Path) -> Path:
    return path.with_name(path.stem + ".lock.json")


def load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA:
        raise ValueError("不支持的校准集版本")
    seen = set()
    for item in data["items"]:
        if item["id"] in seen:
            raise ValueError(f"校准条目重复：{item['id']}")
        seen.add(item["id"])
        if item["label"] not in LABELS:
            raise ValueError(f"{item['id']} 的标签必须是 pass 或 fail")
        if (item["label"] == "fail") != bool(item.get("defect")):
            raise ValueError(f"{item['id']}：fail 必须写明缺陷，pass 不能带缺陷")
        if not str(item.get("rationale") or "").strip():
            raise ValueError(f"{item['id']} 缺少依据")
        entry = SourceEntry.model_validate(item["entry"]).model_dump()
        if entry["system"] != item["system"]:
            raise ValueError(f"{item['id']} 的体系与条目不一致")
    return data


def digest(data: dict) -> str:
    return hashlib.sha256(canonical(data["items"]).encode()).hexdigest()


def counts(data: dict) -> dict:
    found: dict = {}
    for item in data["items"]:
        found.setdefault(item["system"], Counter())[item["label"]] += 1
    return {system: dict(sorted(c.items())) for system, c in sorted(found.items())}


def frozen(path: Path) -> tuple[dict, dict]:
    """The set and its lock; refuses a set that was never frozen or changed afterwards."""
    data = load(path)
    lock = lock_path(path)
    if not lock.is_file():
        raise ValueError(f"校准集尚未经负责人确认冻结：{path.as_posix()}")
    record = json.loads(lock.read_text(encoding="utf-8"))
    if record["sha256"] != digest(data):
        raise ValueError("校准集在冻结后被修改，请重新确认并冻结")
    return data, record


def freeze(path: Path, confirmed_by: str, at: str | None = None) -> dict:
    if not confirmed_by.strip():
        raise ValueError("须写明确认人")
    data = load(path)
    record = dict(
        sha256=digest(data),
        items=len(data["items"]),
        by_system=counts(data),
        confirmed_by=confirmed_by.strip(),
        confirmed_at=at or datetime.now(UTC).isoformat(timespec="seconds"),
        statement="负责人已逐条确认校准条目的内容、标签与依据；冻结后任何修改都使本记录失效。",
    )
    lock_path(path).write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return record


def plan_items(data: dict, system: str) -> list[dict]:
    """Blind plan items: refs like planted copies; the label stays out of the prompt."""
    items = [i for i in data["items"] if i["system"] == system]
    return [
        dict(
            ref=f"calib-{number:03d}",
            id=item["id"],
            original=item.get("base") or item["entry"]["id"],
            label=item["label"],
            entry=SourceEntry.model_validate(item["entry"]).model_dump(),
        )
        for number, item in enumerate(items, 1)
    ]


def table(data: dict) -> str:
    """A Markdown table for the owner to check every label before freezing."""
    rows = [
        "| 编号 | 体系 | 对象 | 标签 | 缺陷 / 依据 | 改动 | 释义（审核员看到的全文） | 方向 | 同义词 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in data["items"]:
        entry = item["entry"]
        defect = item.get("defect") or {}
        why = (f"**{defect['type']}**：{defect['detail']}<br>" if defect else "") + item[
            "rationale"
        ]
        direction = "，".join(f"{k} {v:+g}" for k, v in entry["theme_map"].items() if v) or "全0"
        change = item.get("change")
        cells = [
            item["id"],
            item["system"],
            f"{entry['kind']}:{entry['key']}",
            item["label"],
            why,
            f"{change['field']}：{change['before']} → {change['after']}" if change else "—",
            entry["text"],
            direction,
            "、".join(entry["synonyms"]) or "—",
        ]
        rows.append(
            "| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in cells) + " |"
        )
    return "\n".join(rows) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("show", "freeze"):
        command = commands.add_parser(name)
        command.add_argument("--calibration", type=Path, required=True)
        if name == "freeze":
            command.add_argument("--confirmed-by", required=True)
    args = parser.parse_args(argv)
    if args.command == "show":
        print(table(load(args.calibration)))
    else:
        print(json.dumps(freeze(args.calibration, args.confirmed_by), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
