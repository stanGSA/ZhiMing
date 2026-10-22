"""Review, one by one, the dream aliases the 2026-10-21 revisions removed; restore confirmed ones.

The matcher hits an alias only when the dream phrase is that alias, or ends with it
(plugins/dream/match.py): ``理发`` never fires on ``理发店``. So the test for each alias is the
rubric's dream anchor — does a dreamer who says this word mean the same image? — and not
whether some longer phrase contains it. Drafted by Anthropic Claude on 2026-10-22; groups:

- restore: the same image in other words; restored unless the owner overrides;
- owner:   a judgement call, with Claude's lean; the owner must decide before ``apply``;
- keep:    a different thing, a hypernym, another common sense, or only a scene or an event.

    python -m scripts.dream_alias_review draft --output <复核表.yaml>
    python -m scripts.dream_alias_review show  --review <复核表.yaml>
    python -m scripts.dream_alias_review apply --review <复核表.yaml>   # 负责人确认后、登记前

Restored entries are drafts with a new version, so the second campaign reviews them again.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from knowledge.schema import SourceEntry
from scripts import model_review_kb as review

CHANGES = review.ROOT / "docs/verification/kb-model-review/20261021-live/content-changes.json"
REGRESSION = (
    review.ROOT / "docs/verification/stage1/20261022-acceptance/dream-alias-regression.json"
)

RESTORE = {
    "理发": "剪头发的常用说法，同一动作；“理发店”不会命中（匹配只看整词或词尾）",
    "抱在一起": "拥抱的口语说法，同一动作",
    "地动山摇": "描述地震晃动的成语，梦中所指即地震",
    "花海": "成片的花，程度不同但意象相同",
}
# alias -> (lean, reason); lean is Claude's suggestion, the owner decides.
OWNER = {
    "雪花": ("restore", "飘雪花即在下雪；也可能只是看到一片雪花"),
    "雪地": ("keep", "积雪的场景，不一定在下雪"),
    "白茫茫的雪": ("keep", "雪景，不一定在下雪"),
    "雷电": ("restore", "打雷与闪电并称，通常包含打雷"),
    "闪电": ("keep", "闪电是光，打雷是声，二者可分"),
    "打闪": ("keep", "同“闪电”"),
    "追我": ("restore", "梦中多指被追赶；条目已写明不指感情追求"),
    "追着跑": ("restore", "梦中多指被追赶，但未说明谁追谁"),
    "眼看着车开走": ("restore", "通常是没赶上车；也可能是送别"),
    "迷失方向": ("restore", "空间上的迷路；也可指目标迷失，与“迷失”条目重叠"),
    "不知道自己在哪": ("keep", "空间迷路与身份迷失都可能，与两个条目重叠"),
    "钻石": ("keep", "宝石的一种，但有独立的承诺、恒久联想"),
    "翡翠": ("keep", "玉的一种，文化联想不同于宝石"),
    "玉石": ("keep", "玉不等同于宝石"),
    "大巴": ("keep", "多指长途或旅游客车，不是日常公交"),
    "电动车": ("restore", "与摩托车同为两轮机动车，日常说法；拦截表里的“电动车”会被别名取代"),
    "电瓶车": ("restore", "同“电动车”"),
    "地铁": ("restore", "同属轨道交通；项目解梦标注集也把“地铁”标为火车"),
    "办公室": ("restore", "梦中的工作场所，联想与公司一致"),
    "单位": ("restore", "口语中的工作单位；另有计量义，但描述梦境时少见"),
    "工位": ("restore", "工作位置，联想与公司一致"),
    "海边": ("keep", "岸边场所，不等同于大海本身"),
    "大海边": ("keep", "同“海边”"),
    "海水": ("restore", "海水即大海的意象"),
    "涨水": ("keep", "水位上涨不一定是洪水"),
    "逛街": ("keep", "可能只是闲逛，不一定购物"),
    "骑车": ("restore", "口语里“骑车”通常就是骑自行车；也可能是骑电动车"),
    "涂口红": ("restore", "化妆的一个动作，联想一致"),
    "小强": ("keep", "蟑螂的俗称，但也常是人名"),
    "海龟": ("keep", "与乌龟是不同动物"),
    "脱发": ("keep", "掉头发是独立情节，不是头发本身"),
    "喊不出声": ("keep", "失声的情节，条目是“声音”"),
    "说不出话": ("keep", "同“喊不出声”"),
    "失声": ("keep", "同“喊不出声”"),
    "拼命跑": ("keep", "也可能是比赛或赶路，不一定在逃跑"),
}
KEEP_DEFAULT = "不同事物、上位泛称、常见其他义项，或只是场景、事件；审核理由见 reviewer_reason"
# Restored in R2, then removed again (PR #18 review): without the dreamer as subject they
# end phrases about something else, which the matcher then reads as this image.
KEEP = {
    "往下掉": "没有主语，“杯子往下掉”“牙齿往下掉”也以它结尾，会被当成自己坠落",
    "掉下去": "没有主语，“手机掉下去”也以它结尾，会被当成自己坠落",
    "走丢": "没有主语，“孩子走丢了”会被当成自己迷路；条目侧重自己在具体地点找不到路",
}


def removed() -> list[dict]:
    changes = json.loads(CHANGES.read_text(encoding="utf-8"))
    regression = {
        row["alias"]: row
        for row in json.loads(REGRESSION.read_text(encoding="utf-8"))["removed_aliases"]["rows"]
    }
    reasons = {}
    for path in (review.ROOT / "docs/verification/kb-model-review/20261021-live").glob(
        "dream-*/revision_queue.json"
    ):
        for item in review.read_json(path):
            for verdict in item["verdicts"].values():
                for issue in verdict["issues"]:
                    reasons.setdefault(item["id"], []).append(str(issue.get("detail", "")))
    rows = []
    for change in changes:
        before, after = change["before"], change["after"]
        if before["system"] != "dream" or before["kind"] != "symbol":
            continue
        for alias in sorted(set(before["synonyms"]) - set(after["synonyms"])):
            hit = regression.get(alias, {})
            said = next((r for r in reasons.get(before["id"], []) if alias in r), "")
            rows.append(
                dict(
                    id=before["id"],
                    key=before["key"],
                    alias=alias,
                    now=hit.get("now"),
                    reviewer_reason=said or "（审核意见未单独提及）",
                )
            )
    return rows


def draft() -> dict:
    items = []
    for row in removed():
        alias = row["alias"]
        if row["now"] == row["key"]:
            group, reason, lean = "matched", "现在仍命中原条目，无需恢复", None
        elif alias in RESTORE:
            group, reason, lean = "restore", RESTORE[alias], None
        elif alias in OWNER:
            group, (lean, reason) = "owner", OWNER[alias]
        else:
            group, reason, lean = "keep", KEEP.get(alias, KEEP_DEFAULT), None
        items.append(
            dict(
                row,
                group=group,
                lean=lean,
                reason=reason,
                decision={"restore": "restore", "owner": "undecided"}.get(group, "keep"),
            )
        )
    return dict(
        schema_version=1,
        drafted_by="Anthropic Claude，2026-10-22；负责人确认，把每条 owner 组的 decision 改为 restore 或 keep",
        items=items,
    )


def load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for item in data["items"]:
        if item["decision"] not in ("restore", "keep", "undecided"):
            raise ValueError(f"{item['alias']} 的 decision 只能是 restore 或 keep")
    return data


def apply(workspace, path: Path) -> dict:
    """Write every restore decision into the dream sources, validated across all entries."""
    data = load(path)
    open_items = [i["alias"] for i in data["items"] if i["decision"] == "undecided"]
    if open_items:
        raise ValueError(f"还有 {len(open_items)} 条未决定：{'、'.join(open_items[:10])}")
    wanted: dict[str, list[str]] = {}
    for item in data["items"]:
        if item["decision"] == "restore":
            wanted.setdefault(item["id"], []).append(item["alias"])
    sources = review.source_paths(workspace.sources, "dream")
    documents = [(p, yaml.safe_load(p.read_text(encoding="utf-8"))) for p in sources]
    restored = []
    for _, document in documents:
        for entry in document["entries"]:
            new = [a for a in wanted.get(entry["id"], []) if a not in entry["synonyms"]]
            if new:
                entry["synonyms"] = [*entry["synonyms"], *new]
                entry["version"] += 1
                entry["reviewed"] = False
                restored += [f"{entry['key']}←{a}" for a in new]
    owners: dict[tuple[str, str], str] = {}
    for _, document in documents:
        for entry in map(SourceEntry.model_validate, document["entries"]):
            for alias in (entry.key, *entry.synonyms):
                if owners.setdefault((entry.kind, alias), entry.id) != entry.id:
                    raise ValueError(
                        f"别名冲突：{alias}（{owners[(entry.kind, alias)]}、{entry.id}）；未写入"
                    )
    for source, document in documents:
        source.write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    return dict(restored=restored, count=len(restored))


GROUPS = dict(restore="恢复", owner="需你判断", keep="保持删除", matched="已能命中")


def table(data: dict) -> str:
    rows = [
        "| 条目 | 被删别名 | 分组 | 倾向 | 理由 | 当时的审核意见 | 现在命中 | decision |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    order = dict(restore=0, owner=1, keep=2, matched=3)
    for item in sorted(data["items"], key=lambda i: (order[i["group"]], i["key"], i["alias"])):
        lean = {"restore": "倾向恢复", "keep": "倾向删除"}.get(item["lean"], "—")
        cells = [
            item["key"],
            item["alias"],
            GROUPS[item["group"]],
            lean,
            item["reason"],
            item["reviewer_reason"][:80],
            item["now"] or "未命中",
            item["decision"],
        ]
        rows.append("| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |")
    return "\n".join(rows) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("draft").add_argument("--output", type=Path, required=True)
    for name in ("show", "apply"):
        commands.add_parser(name).add_argument("--review", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "draft":
        data = draft()
        args.output.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8"
        )
        counts = {}
        for item in data["items"]:
            counts[item["group"]] = counts.get(item["group"], 0) + 1
        print(json.dumps(counts, ensure_ascii=False))
    elif args.command == "show":
        print(table(load(args.review)))
    else:
        print(json.dumps(apply(review.Workspace(), args.review), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
