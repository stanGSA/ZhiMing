"""Model cross-review of knowledge entries (项目完善计划书 4.3–4.8; stage 1, B2).

Two reviewers from two vendors, neither the runtime vendor, review the same batches blind:
each call sees one batch only, never the other reviewer's verdicts, and never which items
are planted errors. About 10% of the items of a run are planted copies of real entries with
one known defect (4.6); a copy never shares a batch with its original.

    plan    batches, planted errors and a token/cost estimate; no model call, nothing written
    run     the review calls; resumable, a finished call is cached in the run directory
    merge   the 4.8 metrics, merged verdicts, the revision queue and report.md
    revise  a separate model call proposes revisions for the queue; never an approval
    apply   write proposals into knowledge/sources; the entries stay drafts until re-reviewed
    ledger  approvals of a calibrated run → knowledge/reviews/<system>.yaml

A run directory under docs/verification/kb-model-review/ is bound to its manifest (sources,
rubric, reviewers, seed) and never overwritten. Service errors, unparsable outputs,
interruptions and retries go to errors.jsonl and are never counted as verdicts. API keys are
read from the environment variables named in config.yaml and never written anywhere.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
import subprocess
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv
from pydantic import Field

from harness.llm import RoleModelSpec, role_model
from knowledge import checks
from knowledge.build import build
from knowledge.review import approval, content_hash, load_ledgers, write_ledger
from knowledge.schema import SourceEntry
from plugins.tarot.catalogue import SPREADS
from scripts.kb_review_budget import BudgetExceeded, BudgetModel, ReviewBudget

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "docs/verification/kb-model-review"
SCHEMA = 1
REVIEWERS = ("reviewer_a", "reviewer_b")
VERDICTS = ("pass", "revise", "reject")
THEMES = ("self", "career", "relationship", "finance")
# 4.8. Thresholds are fixed here and never lowered to make a run pass.
GATES = dict(pass_rate=0.95, detection_merged=0.9, detection_single=0.8, rerun=0.9, kappa=0.6)
# Code findings that block an approval whatever the models say. A same-direction tarot pair
# is shown to the reviewers (with the other orientation) and judged by them.
BLOCKING_CHECKS = {"certainty"}

RUBRIC_VERSION = 1
RUBRIC = """你是知识库释义的审核员。项目是一个占卜/自我反思应用，释义是项目自写的草稿，面向普通用户。
请逐条独立判断，只依据条目本身与传统常识，不要猜测其他审核员的意见。

字段说明：kind/key 标明条目对象；text 是给用户看的释义；theme_map 是四个主题
（self 自我状态、career 事业、relationship 感情关系、finance 财务）的倾向值，范围 -1 到 1，
正数偏顺、负数偏阻，0 表示该主题没有方向。只审方向与相对大小是否与文字一致，不审具体数值。
counterpart（若有）是同一张塔罗牌另一方向的释义，只作对照，不需要给它结论。

通用维度：
1. tradition：核心含义符合主流传统，没有把对象写错（如牌名、十神、五行、行星、星座、宫位）。
2. theme_direction：theme_map 的正负方向与释义文字一致。
3. certainty：没有宿命化或确定性断言（必然、注定、一定会……）。否定式免责声明（如“不代表事件必然发生”）不算。
4. medical_legal_finance：没有医疗诊断、投资或法律方面的确定性结论。
5. plain_language：术语附带的白话解释准确，没有误导。
6. copying：不疑似照抄古籍整理版、现代书籍或网站原文（只能标“疑似”）。
7. consistency：与 key、同义词、关键词不矛盾，不与同类条目重复。
{system_rubric}

结论：
- pass：可以原样作为面向用户的草稿释义使用。
- revise：有可以修正的问题（方向与文字不一致、措辞宿命化、白话不准、同义词会误命中等）。
- reject：核心含义错误、文字与 key 不符、疑似抄录，或含医疗/投资/法律确定性结论。

只输出一个 JSON 对象，不要输出其他文字：
{{"items": [{{"item": "<条目编号>", "verdict": "pass|revise|reject",
  "issues": [{{"dimension": "<维度名>", "detail": "<问题>"}}], "reason": "<一句话理由>"}}]}}
每个条目编号恰好出现一次；verdict 为 pass 时 issues 为空列表。"""
SYSTEM_RUBRIC = {
    "tarot": "塔罗：正位、逆位含义区分清楚，倾向方向关系合理（结合 counterpart 判断）；"
    "牌位条目（kind=position）与 spread_positions 给出的牌阵定义一致。",
    "astro": "占星：行星、星座、宫位、相位的基本性质准确；行星落座、落宫的主题方向与文字一致。",
    "bazi": "八字：天干地支、十神、五行生克、冲合刑害描述准确，不把冲合说成灾祸；十神对感情、财运的方向合理。",
    "name": "姓名：81 数理与三才的吉凶写成民间约定，不作命运断言。",
    "dream": "解梦：同义词不会误命中其他意象；不写预兆；死亡、疾病、怀孕等敏感意象措辞平和。",
    "daily": "每日运势：五行配色、种子等约定写成约定，不暗示带来实际运气。",
}
REVISE_PROMPT = """你负责按审核意见修改一条知识库释义草稿。只修改 text、theme_map、synonyms、keywords；
不能改变条目对象（kind/key）。theme_map 只用 self、career、relationship、finance 四个主题，范围 -1 到 1，
0 表示没有方向。不写宿命化、确定性断言，不写医疗、投资、法律结论。修改结果会由两家审核模型重新审核。
只输出一个 JSON 对象：{"text": "...", "theme_map": {...}, "synonyms": [...], "keywords": [...],
"note": "<改了什么>"}"""

FATALISTIC = (
    "出现这一象征意味着必然破财，结局已经注定，无法避免。",
    "这预示着你注定会失去现在的感情，一定会发生。",
    "这说明你今年一定会遭遇重大失败。",
)
MEDICAL = (
    "这表明你已经患有焦虑症，应当尽快服用药物。",
    "出现它说明你的肝脏已有病变，需要立即治疗。",
    "这代表身体已有慢性疾病，不必就医也会自愈。",
)
GODS = ("比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印")
ELEMENTS = ("木", "火", "土", "金", "水")
PLANETS = ("太阳", "月亮", "水星", "金星", "火星", "木星", "土星", "天王星", "海王星", "冥王星")
SIGNS = (
    "白羊",
    "金牛",
    "双子",
    "巨蟹",
    "狮子",
    "处女",
    "天秤",
    "天蝎",
    "射手",
    "摩羯",
    "水瓶",
    "双鱼",
)


class RoleConfig(RoleModelSpec):
    """A configured role. Prices (per million tokens) only feed the estimate and report."""

    input_per_mtok: float | None = Field(default=None, ge=0)
    output_per_mtok: float | None = Field(default=None, ge=0)
    currency: str | None = None


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value) -> None:
    """Atomic write: an interrupted run never leaves a half-written cache file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---- configuration -----------------------------------------------------------------------


def load_roles(config: dict) -> dict[str, RoleConfig | None]:
    roles = ((config.get("kb_review") or {}).get("roles")) or {}
    return {
        name: None if roles.get(name) is None else RoleConfig.model_validate(roles[name])
        for name in (*REVIEWERS, "reviser")
    }


def runtime_vendor(config: dict) -> str:
    return str(config["llm"]["provider"]).strip().lower()


def drafter_vendors(config: dict) -> set[str]:
    drafters = (config.get("kb_review") or {}).get("drafter_vendors") or []
    if isinstance(drafters, str):
        drafters = [drafters]  # one vendor written without brackets, not a list of letters
    if not isinstance(drafters, list) or not all(
        isinstance(v, str) and v.strip() for v in drafters
    ):
        raise ValueError("kb_review.drafter_vendors 必须是厂商名列表")
    return {vendor.strip().lower() for vendor in drafters}


def check_roles(roles: dict, config: dict, needed: tuple[str, ...]) -> None:
    """4.3: two vendors, neither the runtime nor a drafting vendor; a reviser is a third party."""
    missing = [name for name in needed if roles.get(name) is None]
    if missing:
        raise ValueError(f"config.yaml 的 kb_review.roles 未配置：{'、'.join(missing)}")
    vendors = {name: roles[name].vendor.strip().lower() for name in needed}
    reviewers = [vendors[name] for name in REVIEWERS if name in vendors]
    if len(reviewers) == 2 and reviewers[0] == reviewers[1]:
        raise ValueError("两个审核模型必须来自不同厂商")
    if runtime_vendor(config) in reviewers:
        exception = (config.get("kb_review") or {}).get("runtime_vendor_exception") or {}
        for name in REVIEWERS:
            spec = roles.get(name)
            if (
                spec
                and spec.vendor.strip().lower() == runtime_vendor(config)
                and not (
                    exception.get("vendor") == spec.vendor.strip().lower()
                    and exception.get("model") == spec.model
                    and str(exception.get("reason") or "").strip()
                )
            ):
                raise ValueError("审核模型不能与运行时模型同一厂商")
    if drafter_vendors(config) & set(reviewers):
        raise ValueError("审核模型不能与起草条目的模型同一厂商，否则会审自己写的内容")
    if "reviser" in vendors and vendors["reviser"] in reviewers:
        raise ValueError("修改模型不能与审核模型同一厂商，否则会自审自改")


def public_spec(spec: RoleConfig) -> dict:
    """What a run is bound to about a role: identity and settings, never a key or a price."""
    data = spec.model_dump(exclude={"input_per_mtok", "output_per_mtok", "currency"})
    data["base_url_host"] = urlparse(spec.base_url).hostname if spec.base_url else None
    data.pop("base_url")
    return data


# ---- entries and planted errors -----------------------------------------------------------


def source_paths(sources_dir: Path, system: str) -> list[Path]:
    return sorted((sources_dir / system).glob("*.yaml"))


def load_entries(sources_dir: Path, system: str) -> list[dict]:
    entries = []
    for path in source_paths(sources_dir, system):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        entries.extend(SourceEntry.model_validate(e).model_dump() for e in data["entries"])
    return sorted(entries, key=lambda e: e["id"])


def counterpart_key(entry: dict) -> str | None:
    if entry["system"] == "tarot" and entry["kind"] == "card":
        card, orientation = entry["key"].rsplit(":", 1)
        return f"{card}:{'reversed' if orientation == 'upright' else 'upright'}"
    return None


def replace_term(text: str, terms: tuple[str, ...], rng: random.Random) -> str | None:
    present = [t for t in terms if t in text]
    if not present:
        return None
    term = rng.choice(present)
    other = rng.choice([t for t in terms if t != term and t not in text] or [None])
    return None if other is None else text.replace(term, other)


def mutations(entry: dict, by_id: dict[str, dict], rng: random.Random) -> dict[str, dict]:
    """Every planted variant applicable to one entry, each with exactly one defect."""
    found = {}
    if any(entry["theme_map"].values()):
        found["flip_signs"] = dict(entry, theme_map={t: -v for t, v in entry["theme_map"].items()})
    other_key = counterpart_key(entry)
    if other_key:
        other = by_id.get(f"kb:tarot:card:{other_key}")
        if other and other["text"] != entry["text"]:
            found["swap_orientation"] = dict(entry, text=other["text"])
    found["fatalistic"] = dict(entry, text=entry["text"] + rng.choice(FATALISTIC))
    found["medical"] = dict(entry, text=entry["text"] + rng.choice(MEDICAL))
    peers = [
        e
        for e in by_id.values()
        if e["id"] != entry["id"]
        and e["kind"] == entry["kind"]
        and e["text"] != entry["text"]
        and e["id"] != f"kb:tarot:card:{other_key}"
    ]
    if peers:
        found["foreign_text"] = dict(entry, text=rng.choice(peers)["text"])
    if entry["system"] == "dream" and entry["kind"] == "symbol":
        keys = sorted(
            e["key"] for e in by_id.values() if e["kind"] == "symbol" and e["key"] != entry["key"]
        )
        if keys:
            alias = rng.choice(keys)
            found["misleading_synonym"] = dict(entry, synonyms=[*entry["synonyms"], alias])
    terms = {"bazi": GODS + ELEMENTS, "astro": PLANETS + SIGNS}.get(entry["system"])
    if terms:
        text = replace_term(entry["text"], terms, rng)
        if text:
            found["wrong_term"] = dict(entry, text=text)
    return found


def plant(entries: list[dict], rate: float, rng: random.Random, minimum: int = 0) -> list[dict]:
    """~rate planted copies, at least ``minimum`` so a small system still has a detection
    rate; mutation types are balanced over what each original allows."""
    by_id = {e["id"]: e for e in entries}
    count = min(len(entries), max(minimum, round(rate * len(entries)))) if rate > 0 else 0
    used: Counter = Counter()
    planted = []
    for number, original in enumerate(rng.sample(entries, count), 1):
        options = mutations(original, by_id, rng)
        fewest = min(used[name] for name in options)
        name = rng.choice(sorted(n for n in options if used[n] == fewest))
        used[name] += 1
        planted.append(
            dict(
                ref=f"planted-{number:03d}",
                original=original["id"],
                mutation=name,
                entry=options[name],
            )
        )
    return planted


def make_batches(
    entries: list[dict], planted: list[dict], size: int, rng: random.Random
) -> list[dict]:
    """Batches by kind; a planted copy never shares a batch with its original."""
    batches = []
    for kind in sorted({e["kind"] for e in entries}):
        members = [e["id"] for e in entries if e["kind"] == kind]
        for start in range(0, len(members), size):
            batches.append(dict(kind=kind, refs=members[start : start + size]))
    for item in planted:
        kind = item["entry"]["kind"]
        allowed = [b for b in batches if item["original"] not in b["refs"]]
        if not allowed:
            # A small re-review fits in one batch: the copy goes to a batch of its own.
            allowed = [dict(kind=kind, refs=[])]
            batches.append(allowed[0])
        same_kind = [b for b in allowed if b["kind"] == kind] or allowed
        smallest = min(len(b["refs"]) for b in same_kind)
        rng.choice([b for b in same_kind if len(b["refs"]) == smallest])["refs"].append(item["ref"])
    result = []
    for index, batch in enumerate(batches, 1):
        refs = list(batch["refs"])
        rng.shuffle(refs)
        result.append(
            dict(
                batch=f"b{index:03d}",
                kind=batch["kind"],
                items=[dict(item=f"i{n:02d}", ref=ref) for n, ref in enumerate(refs, 1)],
            )
        )
    return result


def shown_entry(entry: dict, item: str, by_id: dict[str, dict]) -> dict:
    """What a reviewer sees: no id, version or review state, so copies look like entries."""
    view = dict(
        item=item,
        kind=entry["kind"],
        key=entry["key"],
        synonyms=entry["synonyms"],
        keywords=entry["keywords"],
        theme_map=entry["theme_map"],
        text=entry["text"],
        source=entry["source"],
    )
    other_key = counterpart_key(entry)
    other = by_id.get(f"kb:tarot:card:{other_key}") if other_key else None
    if other:
        view["counterpart"] = dict(
            key=other["key"], text=other["text"], theme_map=other["theme_map"]
        )
    if entry["system"] == "tarot" and entry["kind"] == "position":
        spread, position = entry["key"].split(":")
        view["spread_positions"] = SPREADS[spread]
        view["position"] = int(position)
    return view


def batch_messages(system: str, batch: dict, contents: dict[str, dict], by_id) -> list[dict]:
    items = [shown_entry(contents[i["ref"]], i["item"], by_id) for i in batch["items"]]
    rubric = RUBRIC.format(system_rubric=SYSTEM_RUBRIC.get(system, ""))
    payload = dict(system=system, items=items)
    return [
        dict(role="system", content=rubric),
        dict(role="user", content=json.dumps(payload, ensure_ascii=False, indent=1)),
    ]


# ---- run directory ------------------------------------------------------------------------


def git_state(root: Path) -> dict:
    def git(*args):
        try:
            return subprocess.run(
                ["git", *args], cwd=root, capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    status = git("status", "--porcelain", "--untracked-files=no")
    return dict(head=git("rev-parse", "HEAD"), dirty=None if status is None else bool(status))


def kb_version(sources_dir: Path, rules_dir: Path, reviews_dir: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="kb-review-") as temporary:
        return build(sources_dir, Path(temporary) / "kb.sqlite", rules_dir, reviews_dir)[
            "kb_version"
        ]


class Workspace:
    """Where sources, rules and the ledger live; tests point it at a copy."""

    def __init__(self, root: Path = ROOT):
        self.root = root
        self.sources = root / "knowledge/sources"
        self.rules = root / "knowledge/rules"
        self.reviews = root / "knowledge/reviews"


def prepare(
    workspace: Workspace,
    config: dict,
    system: str,
    *,
    batch_size: int = 10,
    plant_rate: float = 0.1,
    min_planted: int = 5,
    passes: int = 2,
    seed: int = 1,
    only_ids: list[str] | None = None,
    calibrated_by: str | None = None,
) -> dict:
    """The full, deterministic plan of a run: entries, planted copies, batches, prompts."""
    entries = load_entries(workspace.sources, system)
    if not entries:
        raise ValueError(f"没有{system}条目")
    by_id = {e["id"]: e for e in entries}
    selected = entries
    if only_ids:
        unknown = sorted(set(only_ids) - set(by_id))
        if unknown:
            raise ValueError(f"条目不存在：{unknown}")
        selected = [by_id[i] for i in sorted(set(only_ids))]
    rng = random.Random(seed)
    planted = plant(selected, plant_rate, rng, min_planted)
    batches = make_batches(selected, planted, batch_size, rng)
    contents = {**{e["id"]: e for e in selected}, **{p["ref"]: p["entry"] for p in planted}}
    prompts = {b["batch"]: batch_messages(system, b, contents, by_id) for b in batches}
    roles = load_roles(config)
    paths = source_paths(workspace.sources, system)
    found = [f for f in checks.findings(entries) if f["id"] in {e["id"] for e in selected}]
    manifest = dict(
        schema=SCHEMA,
        system=system,
        seed=seed,
        batch_size=batch_size,
        plant_rate=plant_rate,
        min_planted=min_planted,
        passes=passes,
        only_ids=sorted(set(only_ids)) if only_ids else None,
        calibrated_by=calibrated_by,
        rubric_version=RUBRIC_VERSION,
        rubric_sha256=sha256_bytes((RUBRIC + canonical(SYSTEM_RUBRIC) + REVISE_PROMPT).encode()),
        script_sha256=sha256_bytes(Path(__file__).read_bytes()),
        runtime_vendor=runtime_vendor(config),
        runtime_vendor_exception=(config.get("kb_review") or {}).get("runtime_vendor_exception"),
        pricing={
            name: (
                roles[name].model_dump(include={"input_per_mtok", "output_per_mtok", "currency"})
                if roles[name]
                else None
            )
            for name in REVIEWERS
        },
        reviewers={name: public_spec(roles[name]) if roles[name] else None for name in REVIEWERS},
        source_files={
            p.relative_to(workspace.root).as_posix(): sha256_bytes(
                p.read_bytes().replace(b"\r\n", b"\n")
            )
            for p in paths
        },
        entry_hashes={e["id"]: content_hash(e) for e in selected},
        planted_count=len(planted),
        batch_count=len(batches),
        prompt_sha256={k: sha256_bytes(canonical(v).encode()) for k, v in prompts.items()},
    )
    return dict(
        manifest=manifest,
        entries=selected,
        planted=planted,
        batches=batches,
        prompts=prompts,
        checks=found,
    )


def estimate(plan: dict, roles: dict) -> dict:
    """Rough token count (1 per CJK character, 1 per 4 other characters) and cost."""

    def tokens(text: str) -> int:
        cjk = sum(1 for c in text if "㐀" <= c <= "鿿" or "＀" <= c <= "￯")
        return cjk + (len(text) - cjk) // 4

    calls = len(plan["batches"]) * plan["manifest"]["passes"]
    prompt = sum(tokens(m["content"]) for v in plan["prompts"].values() for m in v)
    items = sum(len(b["items"]) for b in plan["batches"])
    per_role = dict(
        calls=calls,
        input_tokens=prompt * plan["manifest"]["passes"],
        output_tokens=items * 120 * plan["manifest"]["passes"],
    )
    result = {}
    for name in REVIEWERS:
        spec = roles.get(name)
        cost = None
        if spec and spec.input_per_mtok is not None and spec.output_per_mtok is not None:
            cost = round(
                per_role["input_tokens"] / 1e6 * spec.input_per_mtok
                + per_role["output_tokens"] / 1e6 * spec.output_per_mtok,
                4,
            )
        result[name] = dict(per_role, cost=cost, currency=spec.currency if spec else None)
    return result


class RunDir:
    def __init__(self, path: Path):
        self.path = path

    def call_path(self, batch: str, role: str, number: int) -> Path:
        return self.path / "calls" / f"{batch}.{role}.p{number}.json"

    def log_error(self, record: dict) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        with (self.path / "errors.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def errors(self) -> list[dict]:
        path = self.path / "errors.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def calls(self) -> list[dict]:
        return [read_json(p) for p in sorted((self.path / "calls").glob("*.json"))]


# Recorded when a run starts; not part of what binds a directory to its plan.
RUN_FACTS = ("created_at", "git", "kb_version")
PLAN_FILES = dict(
    entries="entries.json",
    batches="batches.json",
    planted="planted.json",
    prompts="inputs.json",
    checks="checks.json",
)


def open_run(path: Path, plan: dict, facts: dict | None = None) -> RunDir:
    """A new directory gets the plan; an existing one must hold exactly this plan.

    The manifest is written first, so a crash leaves a directory that resumes, not one that
    refuses to open. The run keeps its own copy of the plan: merging never depends on later
    source edits.
    """
    manifest_path = path / "manifest.json"
    if manifest_path.is_file():
        stored = read_json(manifest_path)
        if {k: v for k, v in stored.items() if k not in RUN_FACTS} != plan["manifest"]:
            raise ValueError("运行目录已属于另一份审核计划；每次审核请使用新目录，不覆盖历史")
    elif path.exists() and any(path.iterdir()):
        raise ValueError("运行目录非空且没有manifest.json，拒绝覆盖")
    else:
        write_json(manifest_path, dict(plan["manifest"], **(facts or {})))
    for key, name in PLAN_FILES.items():
        if not (path / name).is_file():
            write_json(path / name, plan[key])
    for source in (Path(__file__), ROOT / "harness/llm.py", ROOT / "scripts/kb_review_budget.py"):
        target = path / "runner_source" / source.name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    return RunDir(path)


def load_plan(path: Path) -> dict:
    manifest = read_json(path / "manifest.json")
    plan = {key: read_json(path / name) for key, name in PLAN_FILES.items()}
    return dict(plan, manifest={k: v for k, v in manifest.items() if k not in RUN_FACTS})


# ---- review calls -------------------------------------------------------------------------


def parse_json_object(text: str) -> dict:
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("输出不是JSON对象")
    value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("输出不是JSON对象")
    return value


def parse_verdicts(text: str, batch: dict) -> dict[str, dict]:
    """Verdicts by item; the output must cover exactly the batch's items."""
    value = parse_json_object(text)
    items = value.get("items")
    if not isinstance(items, list):
        raise ValueError("缺少items列表")
    verdicts = {}
    for item in items:
        if not isinstance(item, dict) or item.get("verdict") not in VERDICTS:
            raise ValueError("条目结论不合法")
        key = str(item.get("item"))
        if key in verdicts:
            raise ValueError(f"条目编号重复：{key}")
        issues = item.get("issues") or []
        if not isinstance(issues, list):
            raise ValueError("issues必须是列表")
        if item["verdict"] == "pass" and issues:
            # A listed problem must never become an approval.
            raise ValueError(f"条目{key}判pass却列出问题，结论自相矛盾")
        verdicts[key] = dict(
            verdict=item["verdict"],
            issues=[i if isinstance(i, dict) else dict(detail=str(i)) for i in issues],
            reason=str(item.get("reason") or ""),
        )
    expected = {i["item"] for i in batch["items"]}
    if set(verdicts) != expected:
        raise ValueError(f"条目编号不一致：缺{sorted(expected - set(verdicts))}")
    return verdicts


def describe_error(exc: BaseException) -> dict:
    # Like the runtime trace: the class and status only, SDK error text may echo credentials.
    return dict(error_type=type(exc).__name__, status_code=getattr(exc, "status_code", None))


async def review_call(model, spec, messages, batch, role, number, attempts) -> dict | None:
    """One review call with up to ``attempts`` tries; failures are logged, not verdicts."""
    failures = []
    for attempt in range(1, attempts + 1):
        started, began = now(), time.perf_counter()
        before = getattr(model, "request_attempts", 0)
        base = dict(batch=batch["batch"], reviewer=role, run_pass=number, attempt=attempt)
        try:
            response = await model.chat(messages, [])
        except BudgetExceeded:
            raise
        except Exception as exc:  # noqa: BLE001 - any service failure is logged, not a verdict
            # Transient errors were already retried by the adapter; resume later.
            failures.append(
                dict(
                    base,
                    kind="service_error",
                    at=now(),
                    http_attempts=getattr(model, "request_attempts", 0) - before,
                    **describe_error(exc),
                )
            )
            break
        usage = dict(
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cached_input_tokens=response.cached_input_tokens,
            usage_available=response.usage_available,
        )
        try:
            verdicts = parse_verdicts(response.text, batch)
        except (ValueError, TypeError) as exc:
            failures.append(
                dict(
                    base,
                    kind="parse_error",
                    at=now(),
                    message=str(exc)[:300],
                    returned_model=response.model,
                    raw_text=response.text,
                    latency_s=round(time.perf_counter() - began, 3),
                    http_attempts=getattr(model, "request_attempts", 0) - before,
                    **usage,
                )
            )
            continue
        return dict(
            record=dict(
                batch=batch["batch"],
                reviewer=role,
                run_pass=number,
                attempt=attempt,
                vendor=spec.vendor,
                requested_model=spec.model,
                returned_model=response.model,
                api=spec.api,
                started_at=started,
                finished_at=now(),
                latency_s=round(time.perf_counter() - began, 3),
                http_attempts=getattr(model, "request_attempts", 0) - before,
                finish_reason=response.finish_reason,
                prompt_sha256=sha256_bytes(canonical(messages).encode()),
                **usage,
                raw_text=response.text,
                verdicts=verdicts,
            ),
            failures=failures,
        )
    return dict(record=None, failures=failures)


async def execute(
    run: RunDir,
    plan: dict,
    roles: dict,
    *,
    make_model=None,
    timeout: float = 120,
    attempts: int = 2,
    concurrency: int = 2,
    batches: list[str] | None = None,
) -> dict:
    """Run every missing (batch, reviewer, pass) call; finished calls are never repeated."""
    make_model = make_model or (lambda role, spec: role_model(spec, timeout))
    models = {name: make_model(name, roles[name]) for name in REVIEWERS}
    wanted = [b for b in plan["batches"] if batches is None or b["batch"] in batches]
    jobs = [
        (batch, role, number)
        for number in range(1, plan["manifest"]["passes"] + 1)
        for role in REVIEWERS
        for batch in wanted
        if not run.call_path(batch["batch"], role, number).is_file()
    ]
    gate = asyncio.Semaphore(concurrency)
    done, failed = [], []

    async def one(batch, role, number):
        async with gate:
            try:
                result = await review_call(
                    models[role],
                    roles[role],
                    plan["prompts"][batch["batch"]],
                    batch,
                    role,
                    number,
                    attempts,
                )
            except (asyncio.CancelledError, KeyboardInterrupt):
                where = dict(batch=batch["batch"], reviewer=role, run_pass=number)
                run.log_error(dict(where, kind="interrupted", at=now()))
                raise
        for failure in result["failures"]:
            run.log_error(failure)
        if result["record"] is None:
            failed.append((batch["batch"], role, number))
            return
        write_json(run.call_path(batch["batch"], role, number), result["record"])
        done.append((batch["batch"], role, number))

    tasks = [asyncio.ensure_future(one(*job)) for job in jobs]
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        # An interruption stops every call in flight; each logs itself and resumes later.
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        for model in models.values():
            close = getattr(model, "close", None)
            if close:
                await close()
    total = len(plan["batches"]) * len(REVIEWERS) * plan["manifest"]["passes"]
    return dict(completed=len(done), failed=sorted(failed), cached=len(run.calls()), expected=total)


# ---- metrics and merge --------------------------------------------------------------------


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa over categorical pairs; None when chance agreement is total."""
    if not pairs:
        return None
    total = len(pairs)
    observed = sum(a == b for a, b in pairs) / total
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(left[c] * right[c] for c in VERDICTS) / total**2
    if expected >= 1:
        return None
    return round((observed - expected) / (1 - expected), 4)


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def collect(run: RunDir, plan: dict) -> dict:
    """verdicts[(reviewer, pass)][ref] from the cached calls of this run."""
    refs = {(b["batch"], i["item"]): i["ref"] for b in plan["batches"] for i in b["items"]}
    verdicts: dict[tuple[str, int], dict[str, dict]] = {}
    for call in run.calls():
        table = verdicts.setdefault((call["reviewer"], call["run_pass"]), {})
        for item, verdict in call["verdicts"].items():
            table[refs[(call["batch"], item)]] = verdict
    return verdicts


def metrics(plan: dict, verdicts: dict) -> dict:
    real = [e["id"] for e in plan["entries"]]
    planted = [p["ref"] for p in plan["planted"]]
    passes = plan["manifest"]["passes"]
    first = {role: verdicts.get((role, 1), {}) for role in REVIEWERS}
    blocked = {f["id"] for f in plan["checks"] if f["check"] in BLOCKING_CHECKS}

    def flagged(role, ref):
        return first[role].get(ref, {}).get("verdict") not in (None, "pass")

    approved, queued, incomplete = [], [], []
    for ref in real:
        recorded = [
            verdicts[(role, n)][ref]["verdict"]
            for role in REVIEWERS
            for n in range(1, passes + 1)
            if ref in verdicts.get((role, n), {})
        ]
        if any(
            ref not in verdicts.get((role, n), {})
            for role in REVIEWERS
            for n in range(1, passes + 1)
        ):
            incomplete.append(ref)
        elif all(v == "pass" for v in recorded) and ref not in blocked:
            approved.append(ref)
        else:
            queued.append(ref)
    seen = [p for p in planted if all(p in first[role] for role in REVIEWERS)]
    detection = {role: ratio(sum(flagged(role, p) for p in seen), len(seen)) for role in REVIEWERS}
    merged_detection = ratio(sum(any(flagged(r, p) for r in REVIEWERS) for p in seen), len(seen))
    rerun = {}
    for role in REVIEWERS:
        again = verdicts.get((role, 2), {})
        common = [ref for ref in first[role] if ref in again]
        rerun[role] = (
            ratio(
                sum(first[role][r]["verdict"] == again[r]["verdict"] for r in common), len(common)
            )
            if passes >= 2
            else None
        )
    pairs = [
        (first["reviewer_a"][ref]["verdict"], first["reviewer_b"][ref]["verdict"])
        for ref in real
        if ref in first["reviewer_a"] and ref in first["reviewer_b"]
    ]
    values = dict(
        pass_rate=ratio(len(approved), len(real)),
        detection=detection,
        detection_merged=merged_detection,
        rerun=rerun,
        kappa=cohen_kappa(pairs),
        observed_agreement=ratio(sum(a == b for a, b in pairs), len(pairs)),
        verdict_counts={
            role: dict(Counter(first[role][ref]["verdict"] for ref in real if ref in first[role]))
            for role in REVIEWERS
        },
    )

    def at_least(value, target):
        return value is not None and value >= target

    gates = dict(
        pass_rate=at_least(values["pass_rate"], GATES["pass_rate"]),
        detection_merged=at_least(merged_detection, GATES["detection_merged"]),
        detection_single=all(at_least(v, GATES["detection_single"]) for v in detection.values()),
        rerun=all(at_least(v, GATES["rerun"]) for v in rerun.values()),
        kappa=at_least(values["kappa"], GATES["kappa"]),
        complete=not incomplete and len(seen) == len(planted),
    )
    calibrated = all(gates[k] for k in ("detection_merged", "detection_single", "rerun", "kappa"))
    return dict(
        values=values,
        gates=gates,
        calibrated=calibrated and gates["complete"],
        passed=all(gates.values()),
        approved=approved,
        queued=queued,
        incomplete=incomplete,
        planted_seen=len(seen),
    )


def usage_summary(run: RunDir, roles: dict) -> dict:
    summary = {}
    calls = run.calls()
    errors = run.errors()
    if (run.path / "revisions.json").exists():
        for proposal in read_json(run.path / "revisions.json"):
            calls.extend(
                dict(p, reviewer="reviser", attempt=1)
                for p in [*proposal.get("previous_invalid", []), proposal]
            )
    manifest = read_json(run.path / "manifest.json")
    for role in (*REVIEWERS, "reviser"):
        own = [c for c in calls if c["reviewer"] == role]
        failed = [e for e in errors if e["reviewer"] == role]
        if role == "reviser" and not own and not failed:
            continue
        tokens_in = sum(c["input_tokens"] for c in own) + sum(
            e.get("input_tokens", 0) for e in failed
        )
        tokens_out = sum(c["output_tokens"] for c in own) + sum(
            e.get("output_tokens", 0) for e in failed
        )
        spec = roles.get(role)
        prices = (manifest.get("pricing") or {}).get(role)
        if prices is None and spec:
            prices = spec.model_dump(include={"input_per_mtok", "output_per_mtok", "currency"})
        cost = None
        if prices and all(prices.get(k) is not None for k in ("input_per_mtok", "output_per_mtok")):
            cost = round(
                tokens_in / 1e6 * prices["input_per_mtok"]
                + tokens_out / 1e6 * prices["output_per_mtok"],
                6,
            )
        complete_usage = all(c.get("usage_available", True) for c in own) and all(
            e.get("usage_available", False) for e in failed
        )
        summary[role] = dict(
            calls=len(own),
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            latency_s=round(
                sum(c["latency_s"] for c in own) + sum(e.get("latency_s", 0) for e in failed), 3
            ),
            returned_models=sorted({c["returned_model"] for c in own if c["returned_model"]}),
            errors=dict(Counter(e["kind"] for e in failed)),
            retried_calls=sum(c["attempt"] > 1 for c in own),
            http_retries=sum(max(0, c.get("http_attempts", 1) - 1) for c in own),
            cost=cost if complete_usage else None,
            known_cost_estimate=cost,
            usage_complete=complete_usage,
            cost_basis="配置单价估算，非账单；服务失败的用量可能未知",
            currency=prices.get("currency") if prices else None,
        )
    return summary


def merge(run: RunDir, plan: dict, roles: dict) -> dict:
    verdicts = collect(run, plan)
    result = metrics(plan, verdicts)
    first = {role: verdicts.get((role, 1), {}) for role in REVIEWERS}
    by_id = {e["id"]: e for e in plan["entries"]}
    findings: dict[str, list[dict]] = {}
    for finding in plan["checks"]:
        findings.setdefault(finding["id"], []).append(finding)
    queue = []
    for ref in result["queued"]:
        queue.append(
            dict(
                id=ref,
                content_sha256=content_hash(by_id[ref]),
                verdicts={
                    f"{role}.p{n}": verdicts[(role, n)][ref]
                    for role in REVIEWERS
                    for n in range(1, plan["manifest"]["passes"] + 1)
                    if ref in verdicts.get((role, n), {})
                },
                code_findings=findings.get(ref, []),
            )
        )
    planted = [
        dict(
            ref=p["ref"],
            original=p["original"],
            mutation=p["mutation"],
            **{role: first[role].get(p["ref"], {}).get("verdict") for role in REVIEWERS},
        )
        for p in plan["planted"]
    ]
    by_mutation = {}
    for item in planted:
        stats = by_mutation.setdefault(
            item["mutation"], dict(total=0, **dict.fromkeys(REVIEWERS, 0))
        )
        stats["total"] += 1
        for role in REVIEWERS:
            stats[role] += item[role] not in (None, "pass")
    summary = dict(
        system=plan["manifest"]["system"],
        entries=len(plan["entries"]),
        planted=len(plan["planted"]),
        metrics=result["values"],
        gates=result["gates"],
        thresholds=GATES,
        calibrated=result["calibrated"],
        passed=result["passed"],
        approved=len(result["approved"]),
        queued=len(result["queued"]),
        incomplete=result["incomplete"],
        planted_detail=planted,
        detection_by_mutation=by_mutation,
        usage=usage_summary(run, roles),
        code_findings=plan["checks"],
        human_reviewed_rate=0.0,
    )
    write_json(run.path / "merged.json", dict(summary, approved_ids=result["approved"]))
    write_json(run.path / "revision_queue.json", queue)
    (run.path / "report.md").write_text(render_report(summary, run), encoding="utf-8")
    return summary


def cost_text(usage: dict) -> str:
    if usage["cost"] is None:
        return "未配置单价"
    return f"{usage['cost']} {usage['currency'] or ''}".strip()


def render_report(summary: dict, run: RunDir) -> str:
    def show(value):
        return "未测" if value is None else f"{value:.2%}" if isinstance(value, float) else value

    m, g = summary["metrics"], summary["gates"]
    manifest = read_json(run.path / "manifest.json")
    rows = [
        ("双模型交叉审核通过率", show(m["pass_rate"]), "≥ 95%", g["pass_rate"]),
        ("埋错检出率（合并）", show(m["detection_merged"]), "≥ 90%", g["detection_merged"]),
        *[
            (f"埋错检出率（{role}）", show(m["detection"][role]), "≥ 80%", None)
            for role in REVIEWERS
        ],
        *[(f"重跑一致率（{role}）", show(m["rerun"][role]), "≥ 90%", None) for role in REVIEWERS],
        (
            "模型间一致率 kappa",
            "无法计算" if m["kappa"] is None else m["kappa"],
            "≥ 0.6",
            g["kappa"],
        ),
    ]
    lines = [
        f"# 模型交叉审核：{summary['system']}",
        "",
        "结论只表示“经模型交叉审核”，不是人工审核；人工审核率仍为 0%。",
        f"运行时厂商例外：{json.dumps(manifest.get('runtime_vendor_exception'), ensure_ascii=False)}。",
        "",
        f"- 条目 {summary['entries']}，埋错 {summary['planted']}；两家都通过 {summary['approved']}，"
        f"进入修改队列 {summary['queued']}，未完成 {len(summary['incomplete'])}",
        f"- 校准（埋错、重跑、kappa）是否达标：{'是' if summary['calibrated'] else '否'}；"
        f"4.8 全部指标是否达标：{'是' if summary['passed'] else '否'}",
        "",
        "| 指标 | 结果 | 目标 | 达标 |",
        "| --- | --- | --- | --- |",
        *[
            f"| {name} | {value} | {target} | {'—' if met is None else '是' if met else '否'} |"
            for name, value, target, met in rows
        ],
        "",
        "| 审核方 | 调用 | 输入 token | 输出 token | 耗时 s | 返回模型 | 错误 | 费用 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        *[
            f"| {role} | {u['calls']} | {u['input_tokens']} | {u['output_tokens']} | "
            f"{u['latency_s']} | {'、'.join(u['returned_models']) or '—'} | "
            f"{json.dumps(u['errors'], ensure_ascii=False)} | "
            f"{cost_text(u)} |"
            for role, u in summary["usage"].items()
        ],
        "",
        "## 埋错检出（按改法）",
        "",
        "| 改法 | 数量 | reviewer_a 检出 | reviewer_b 检出 |",
        "| --- | --- | --- | --- |",
        *[
            f"| {name} | {s['total']} | {s['reviewer_a']} | {s['reviewer_b']} |"
            for name, s in sorted(summary["detection_by_mutation"].items())
        ],
        "",
        f"代码检查发现 {len(summary['code_findings'])} 条（见 checks.json）；"
        f"阻止通过的类型：{'、'.join(sorted(BLOCKING_CHECKS))}。",
        f"错误与重试明细见 errors.jsonl（{len(run.errors())} 条），不计入审核结论。",
    ]
    return "\n".join(lines) + "\n"


# ---- revision, apply, ledger --------------------------------------------------------------


def valid_proposal(entry: dict, proposal: dict) -> str | None:
    themes = proposal.get("theme_map")
    if not isinstance(proposal.get("text"), str) or len(proposal["text"]) < 10:
        return "text过短或缺失"
    if not isinstance(themes, dict) or any(
        t not in THEMES or not isinstance(v, int | float) or not -1 <= v <= 1
        for t, v in themes.items()
    ):
        return "theme_map主题或数值不合法"
    for field in ("synonyms", "keywords"):
        if not isinstance(proposal.get(field), list) or not all(
            isinstance(v, str) and v for v in proposal[field]
        ):
            return f"{field}必须是字符串列表"
    if not proposal["keywords"]:
        return "keywords不能为空"
    word = checks.certainty_finding(proposal["text"])
    if word:
        return f"修改稿含确定性说法“{word}”"
    return None


async def revise(
    run: RunDir,
    plan: dict,
    roles: dict,
    *,
    make_model=None,
    timeout: float = 120,
    vendor_exception: dict | None = None,
) -> list[dict]:
    """Proposals from a third model; saved for review, never applied or approved here."""
    make_model = make_model or (lambda role, spec: role_model(spec, timeout))
    spec = roles["reviser"]
    if spec is None:
        raise ValueError("config.yaml 的 kb_review.roles 未配置：reviser")
    # Historical runs keep their reviewers even when today's configuration changes.
    reviewers = plan["manifest"]["reviewers"]
    exception = vendor_exception or {}
    identity = {name: {k: r[k] for k in ("vendor", "model")} for name, r in reviewers.items()}
    allowed = (
        exception.get("vendor") == spec.vendor.strip().lower()
        and exception.get("model") == spec.model
        and exception.get("reviewers") == identity
        and str(exception.get("reason") or "").strip()
    )
    if (
        any(spec.vendor.strip().lower() == r["vendor"].strip().lower() for r in reviewers.values())
        and not allowed
    ):
        raise ValueError("修改模型不能与本批审核模型同一厂商，否则会自审自改")
    model = make_model("reviser", spec)
    queue = read_json(run.path / "revision_queue.json")
    by_id = {e["id"]: e for e in plan["entries"]}
    path = run.path / "revisions.json"
    proposals = {p["id"]: p for p in (read_json(path) if path.is_file() else [])}
    try:
        for item in queue:
            earlier = proposals.get(item["id"])
            # A valid proposal is kept; an invalid one is asked for again on the next run.
            if earlier is not None and earlier["invalid"] is None:
                continue
            entry = by_id[item["id"]]
            issues = [
                dict(reviewer=k, verdict=v["verdict"], issues=v["issues"], reason=v["reason"])
                for k, v in item["verdicts"].items()
                if v["verdict"] != "pass"
            ] + [dict(code_check=f["check"], detail=f["detail"]) for f in item["code_findings"]]
            shown = {k: entry[k] for k in ("kind", "key", "synonyms", "keywords", "theme_map")}
            messages = [
                dict(role="system", content=REVISE_PROMPT),
                dict(
                    role="user",
                    content=json.dumps(
                        dict(entry=dict(shown, text=entry["text"]), issues=issues),
                        ensure_ascii=False,
                        indent=1,
                    ),
                ),
            ]
            started = time.perf_counter()
            before = getattr(model, "request_attempts", 0)
            response = None
            try:
                response = await model.chat(messages, [])
                proposal = parse_json_object(response.text)
            except BudgetExceeded:
                raise
            except Exception as exc:  # noqa: BLE001 - logged and retried on the next invocation
                run.log_error(
                    dict(reviewer="reviser", batch=item["id"], kind="revise_error", at=now())
                    | dict(
                        vendor=spec.vendor,
                        requested_model=spec.model,
                        returned_model=response.model if response else None,
                        raw_text=response.text if response else None,
                        input_tokens=response.input_tokens if response else 0,
                        output_tokens=response.output_tokens if response else 0,
                        usage_available=response.usage_available if response else False,
                        latency_s=round(time.perf_counter() - started, 3),
                        http_attempts=getattr(model, "request_attempts", 0) - before,
                    )
                    | describe_error(exc)
                )
                continue
            proposals[item["id"]] = dict(
                id=item["id"],
                before_sha256=content_hash(entry),
                proposal={
                    k: proposal.get(k) for k in ("text", "theme_map", "synonyms", "keywords")
                },
                note=str(proposal.get("note") or ""),
                invalid=valid_proposal(entry, proposal),
                vendor=spec.vendor,
                vendor_exception=exception if allowed else None,
                requested_model=spec.model,
                returned_model=response.model,
                raw_text=response.text,
                prompt_sha256=sha256_bytes(canonical(messages).encode()),
                pricing=spec.model_dump(include={"input_per_mtok", "output_per_mtok", "currency"}),
                usage_available=response.usage_available,
                cached_input_tokens=response.cached_input_tokens,
                finish_reason=response.finish_reason,
                http_attempts=getattr(model, "request_attempts", 0) - before,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_s=round(time.perf_counter() - started, 3),
                at=now(),
                # Earlier invalid attempts stay on record (and in the token count).
                previous_invalid=(
                    [*earlier.pop("previous_invalid", []), earlier] if earlier else []
                ),
            )
            write_json(path, sorted(proposals.values(), key=lambda p: p["id"]))
    finally:
        close = getattr(model, "close", None)
        if close:
            await close()
    return sorted(proposals.values(), key=lambda p: p["id"])


def apply_revisions(workspace: Workspace, run: RunDir, ids: list[str] | None = None) -> list[str]:
    """Write valid proposals into the sources. Entries stay drafts; re-review is a new run."""
    proposals = [
        p
        for p in read_json(run.path / "revisions.json")
        if not p["invalid"] and (ids is None or p["id"] in ids)
    ]
    wanted = {p["id"]: p for p in proposals}
    applied = []
    system = read_json(run.path / "manifest.json")["system"]
    for path in source_paths(workspace.sources, system):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        changed = False
        for entry in data["entries"]:
            proposal = wanted.get(entry["id"])
            if proposal is None:
                continue
            if (
                content_hash(SourceEntry.model_validate(entry).model_dump())
                != proposal["before_sha256"]
            ):
                raise ValueError(f"条目已在修改建议之后变化：{entry['id']}")
            entry.update(proposal["proposal"])
            entry["version"] += 1
            entry["reviewed"] = False
            applied.append(entry["id"])
            changed = True
        if changed:
            path.write_text(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
    return sorted(applied)


def calibration_of(run_path: Path, root: Path) -> tuple[dict, dict]:
    merged = read_json(run_path / "merged.json")
    manifest = read_json(run_path / "manifest.json")
    if manifest.get("calibrated_by"):
        source = root / manifest["calibrated_by"]
        other = read_json(source / "manifest.json")
        same = all(other[k] == manifest[k] for k in ("reviewers", "rubric_sha256", "system"))
        if not same:
            raise ValueError("校准来源的审核模型、rubric或体系与本次不同")
        if not read_json(source / "merged.json")["calibrated"]:
            raise ValueError("校准来源未达到埋错、重跑与kappa指标")
        # Borrowed rates do not excuse this run's own misses: every planted copy in it must
        # have been flagged by at least one reviewer (so none of them would have passed).
        planted = merged["planted_detail"]
        if not planted or not all(
            all(item[role] is not None for role in REVIEWERS)
            and any(item[role] != "pass" for role in REVIEWERS)
            for item in planted
        ):
            raise ValueError("借用校准的批次须检出本批全部埋错，不能记为模型交叉审核")
    elif not merged["calibrated"]:
        raise ValueError("本次审核未达到埋错、重跑与kappa指标，不能记为模型交叉审核")
    return manifest, merged


def record_ledger(workspace: Workspace, run_paths: list[Path], root: Path = ROOT) -> dict:
    """Update approvals and revoke rejected content, preserving unrelated versions."""
    written: dict[str, list[str]] = {}
    stale = []
    for run_path in run_paths:
        manifest = read_json(run_path / "manifest.json")
        system = manifest["system"]
        existing = {
            record.id: record.model_dump()
            for record in load_ledgers(workspace.reviews).values()
            if record.id.startswith(f"kb:{system}:")
        }
        before = existing.copy()
        run = RunDir(run_path)
        plan = load_plan(run_path)
        verdicts = collect(run, plan)
        rejected = {
            ref
            for table in verdicts.values()
            for ref, verdict in table.items()
            if verdict["verdict"] != "pass"
        }
        rejected.update(f["id"] for f in plan["checks"] if f["check"] in BLOCKING_CHECKS)
        for entry_id in rejected:
            record = existing.get(entry_id)
            # A rejection of older content cannot revoke a newer content approval.
            if record and record["content_sha256"] == manifest["entry_hashes"].get(entry_id):
                del existing[entry_id]
        # Revocation is conservative: it must survive failed calibration, incomplete
        # service calls and undefined kappa. Calibration only authorizes NEW approvals.
        if existing != before:
            write_ledger(workspace.reviews, system, list(existing.values()))
            write_json(
                run_path / "ledger_revocations.json",
                dict(
                    at=now(), records=[before[i] for i in sorted(before.keys() - existing.keys())]
                ),
            )
        manifest, merged = calibration_of(run_path, root)
        if merged["approved_ids"]:
            current = {e["id"]: e for e in load_entries(workspace.sources, system)}
            calls = run.calls()
            reviewers = []
            for role in REVIEWERS:
                spec = manifest["reviewers"][role]
                returned = sorted(
                    {c["returned_model"] for c in calls if c["reviewer"] == role} - {None}
                )
                reviewers.append(
                    dict(
                        vendor=spec["vendor"],
                        model=spec["model"],
                        returned_model="、".join(returned) or None,
                        verdict="pass",
                    )
                )
            day = min(c["started_at"] for c in calls)[:10]
            report = run_path / "report.md"
            report = (
                report.relative_to(root).as_posix() if report.is_relative_to(root) else str(report)
            )
            for entry_id in merged["approved_ids"]:
                entry = current.get(entry_id)
                if entry is None or content_hash(entry) != manifest["entry_hashes"][entry_id]:
                    stale.append(entry_id)
                    continue
                existing[entry_id] = approval(entry, reviewers, day, report)
                written.setdefault(system, []).append(entry_id)
        if existing != before:
            write_ledger(workspace.reviews, system, list(existing.values()))
    return dict(written={k: len(v) for k, v in written.items()}, stale=sorted(stale))


# ---- command line -------------------------------------------------------------------------


def load_config(root: Path) -> dict:
    return yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> Any:
    parser = argparse.ArgumentParser(description="知识库模型交叉审核（不是人工审核）")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        command = commands.add_parser(name)
        command.add_argument("--system", required=True)
        command.add_argument("--batch-size", type=int, default=10)
        command.add_argument("--plant-rate", type=float, default=0.1)
        command.add_argument("--min-planted", type=int, default=5)
        command.add_argument("--passes", type=int, default=2, choices=(1, 2))
        command.add_argument("--seed", type=int, default=1)
        command.add_argument("--only-ids", nargs="*")
        command.add_argument("--calibrated-by")
        if name == "run":
            command.add_argument("--run-dir", type=Path, required=True)
            command.add_argument("--batches", nargs="*")
            command.add_argument("--attempts", type=int, default=2)
            command.add_argument("--concurrency", type=int, default=2)
    for name in ("merge", "revise", "apply"):
        command = commands.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
        if name == "apply":
            command.add_argument("--ids", nargs="*")
    ledger = commands.add_parser("ledger")
    ledger.add_argument("--run-dir", type=Path, nargs="+", required=True)
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")
    workspace = Workspace()
    config = load_config(ROOT)
    roles = load_roles(config)
    timeout = float((config.get("kb_review") or {}).get("timeout_s", 120))

    def paid_model(role, spec):
        return BudgetModel(
            None,
            role,
            spec,
            ReviewBudget(config, ROOT),
            make_model=lambda: role_model(spec, timeout),
        )

    if args.command in ("plan", "run"):
        plan = prepare(
            workspace,
            config,
            args.system,
            batch_size=args.batch_size,
            plant_rate=args.plant_rate,
            min_planted=args.min_planted,
            passes=args.passes,
            seed=args.seed,
            only_ids=args.only_ids,
            calibrated_by=args.calibrated_by,
        )
        if args.command == "plan":
            output = dict(
                system=args.system,
                entries=len(plan["entries"]),
                planted=len(plan["planted"]),
                mutations=dict(Counter(p["mutation"] for p in plan["planted"])),
                batches=[
                    dict(batch=b["batch"], kind=b["kind"], items=len(b["items"]))
                    for b in plan["batches"]
                ],
                code_findings=checks.summary(plan["checks"]),
                estimate=estimate(plan, roles),
                note="估算按每个汉字约1 token、每条输出约120 token；以小批次实测为准。",
            )
        else:
            check_roles(roles, config, REVIEWERS)
            facts = dict(
                created_at=now(),
                git=git_state(ROOT),
                kb_version=kb_version(workspace.sources, workspace.rules, workspace.reviews),
            )
            run = open_run(args.run_dir, plan, facts)
            output = asyncio.run(
                execute(
                    run,
                    plan,
                    roles,
                    timeout=timeout,
                    attempts=args.attempts,
                    concurrency=args.concurrency,
                    batches=args.batches,
                    make_model=paid_model,
                )
            )
    elif args.command == "merge":
        output = merge(RunDir(args.run_dir), load_plan(args.run_dir), roles)
        output = {k: v for k, v in output.items() if k not in ("planted_detail", "code_findings")}
    elif args.command == "revise":
        check_roles(roles, config, ("reviser",))
        plan = load_plan(args.run_dir)
        output = asyncio.run(
            revise(
                RunDir(args.run_dir),
                plan,
                roles,
                timeout=timeout,
                make_model=paid_model,
                vendor_exception=(config.get("kb_review") or {}).get("reviser_vendor_exception"),
            )
        )
    elif args.command == "apply":
        output = apply_revisions(workspace, RunDir(args.run_dir), args.ids)
    else:
        output = record_ledger(workspace, args.run_dir)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


if __name__ == "__main__":
    main()
