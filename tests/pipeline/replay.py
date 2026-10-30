"""Failure replays as data (P0.4 of docs/根因整改实施计划.md).

Each file under ``replays/`` is one failure chain recorded in a live run: the user's turns, the
calls the model made, and what the current agent answered at each step. Every phase of the
pipeline refactor runs the same chains, so a fix is checked against the failures it is meant to
remove rather than against new, easier examples.

A ``legacy`` section replays the model's calls through ``Runtime.turn`` with a scripted model.
Strings in call arguments may hold placeholders, resolved when the model "writes" the call:

- ``{{ref:month:庚申&劫财}}``: the R-number the model was shown for the one citable reference
  whose identifier contains every ``&``-separated part; ``{{ref:transit:2026-11#0}}`` takes the
  first of several, in the order the model was shown them;
- ``{{result:resolve_location.location.location_id}}``: a value from the latest result of that
  tool as the model saw it.

A ``submit_reading`` step may give a short ``draft`` instead of ``args``; the fields a model
always writes the same way are filled in by ``reading_args``.

The ``pipeline`` section states what the pipeline must do with the same turns: the final
status and ``max_model_calls_per_turn``, counted per user message like the plan's limit of three
(intent, compose, at most one repair). Once a phase routes a system through the pipeline, its
chains also name the writer ``drafts`` (tests/pipeline/drafts.py) that repeat the recorded
failure, with the expected ``repairs`` and ``degraded``; tests/pipeline/test_replays.py runs them
through the pipeline. Until then the section is data only.

Some chains replace the recorded input (a different place, a fixed seed) so that they still
fail on current code. They are deterministic regression samples, not a measure of how often a
real model succeeds.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from harness.models import ModelResponse, ToolCall

DIRECTORY = Path(__file__).with_name("replays")
PLACEHOLDER = re.compile(r"\{\{(ref|result):([^}]+)\}\}")
CATEGORIES = ("B", "C", "D", "E", "I", "Z", "L")
LOW = dict(level="low", reason="释义为未人工审核草稿")


def load_all() -> list[dict]:
    cases = []
    for path in sorted(DIRECTORY.glob("*.yaml")):
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        case["file"] = path.name
        check_case(case)
        cases.append(case)
    return cases


def check_case(case: dict) -> None:
    """The fields every replay must carry, so a later phase can rely on them."""
    for key in ("id", "source", "category", "systems", "turns", "legacy"):
        assert key in case, f"{case.get('file')}: missing {key}"
    assert case["category"][0] in CATEGORIES, case["category"]
    assert case["id"] == case["file"].removesuffix(".yaml"), "file name must match id"
    legacy = case["legacy"]
    assert legacy["steps"] and "outcome" in legacy
    for step in legacy["steps"]:
        assert ("args" in step) != ("draft" in step) or step["call"] != "submit_reading"
        expect = step.get("expect", "ok")
        assert expect == "ok" or set(expect) <= {"error", "code", "needs_input"}, expect


def reading_args(draft: dict, state: dict) -> dict:
    sections = [
        dict(title=s["title"], body=s["body"], ref_ids=list(s.get("refs", [])))
        for s in draft.get("sections", [])
    ]
    refs = list(dict.fromkeys(r for s in sections for r in s["ref_ids"])) or draft["evidence"]
    return dict(
        question_type=draft["question_type"],
        systems_used=draft.get("systems_used")
        or sorted({s["system"] for s in state.get("signals", [])}),
        summary=draft["summary"],
        sections=sections,
        evidence=[dict(ref_id=r) for r in draft.get("evidence", refs)],
        advice=draft.get("advice", ["先做小范围尝试：确认条件后再推进。"]),
        confidence=LOW,
        safety=draft.get("safety", dict(flag=False, note="")),
        **({"verdict": draft["verdict"]} if "verdict" in draft else {}),
    )


class ScriptedReplay:
    """Returns the recorded calls one per model turn, resolving placeholders on the way."""

    def __init__(self, steps: list[dict], session):
        self.steps = list(steps)
        self.session = session
        self.calls = 0
        self.issued: list[tuple[str, dict]] = []

    def resolve(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        if not isinstance(value, str):
            return value
        whole = PLACEHOLDER.fullmatch(value)
        if whole:
            return self.lookup(*whole.groups())
        return PLACEHOLDER.sub(lambda m: str(self.lookup(*m.groups())), value)

    def lookup(self, kind: str, spec: str):
        if kind == "ref":
            spec, _, index = spec.partition("#")
            parts = spec.split("&")
            aliases = self.session.state.get("ref_alias", {})
            found = [a for a, full in aliases.items() if all(p in full for p in parts)]
            if index:
                return sorted(found, key=lambda alias: int(alias[1:]))[int(index)]
            assert len(found) == 1, f"{{{{ref:{spec}}}}} matches {found}"
            return found[0]
        tool, *path = spec.split(".")
        value = latest_result(self.session, tool)["data"]
        for key in path:
            value = value[int(key)] if isinstance(value, list) else value[key]
        return value

    async def chat(self, messages, tools):
        self.calls += 1
        if not self.steps:
            return ModelResponse(text="（回放结束）", input_tokens=10, output_tokens=1)
        step = self.steps.pop(0)
        if step["call"] == "submit_reading" and "draft" in step:
            arguments = reading_args(self.resolve(step["draft"]), self.session.state)
            # A recorded malformed field (e.g. sections sent as a string) replaces the draft's.
            arguments.update(self.resolve(step.get("override", {})))
        else:
            arguments = self.resolve(step.get("args", {}))
        call_id = f"replay-{len(self.issued)}"
        self.issued.append((call_id, step))
        return ModelResponse(
            input_tokens=100,
            output_tokens=10,
            tool_calls=[ToolCall(id=call_id, name=step["call"], arguments=arguments)],
        )


def tool_results(session) -> dict[str, dict]:
    """Model-visible tool results by call id."""
    results = {}
    for message in session.messages:
        if message["role"] == "tool":
            results[message["tool_call_id"]] = json.loads(message["content"])
    return results


def latest_result(session, tool: str) -> dict:
    names = {
        call["id"]: call["function"]["name"]
        for message in session.messages
        if message["role"] == "assistant"
        for call in message.get("tool_calls") or []
    }
    matching = [r for cid, r in tool_results(session).items() if names.get(cid) == tool]
    assert matching, f"no result of {tool} yet"
    return matching[-1]


def mismatches(model: ScriptedReplay, session) -> list[str]:
    """Steps whose result differs from what the replay recorded."""
    results = tool_results(session)
    problems = []
    for call_id, step in model.issued:
        result = results.get(call_id)
        expect = step.get("expect", "ok")
        label = f"{call_id} {step['call']}"
        if result is None:
            problems.append(f"{label}: no result")
        elif expect == "ok":
            needs = (result.get("data") or {}).get("status") == "needs_input"
            if not result.get("ok") or needs:
                problems.append(f"{label}: expected ok, got {json.dumps(result)[:200]}")
        elif "needs_input" in expect:
            data = result.get("data") or {}
            if data.get("status") != "needs_input" or data.get("code") != expect["needs_input"]:
                problems.append(f"{label}: expected needs_input, got {json.dumps(result)[:200]}")
        else:
            if result.get("ok"):
                problems.append(f"{label}: expected an error, got ok")
            elif "error" in expect and expect["error"] not in (result.get("error") or ""):
                problems.append(f"{label}: error was {result.get('error')!r}")
            elif "code" in expect and expect["code"] != result.get("code"):
                problems.append(f"{label}: code was {result.get('code')!r}")
    if model.steps:
        problems.append(f"{len(model.steps)} recorded calls were never requested")
    return problems
