"""Probe the model service before a campaign: no credential, endpoint or headers in output.

Three requests, each answerable in a few tokens when the service runs without thinking:

- the runtime model replying “OK”;
- the runtime model calling a tool that takes no arguments;
- the rubric judge (``eval_judges`` in config.yaml) replying “OK” with its own request options.

Bazi pilot r14 and r15 (docs/verification/p3/bazi-pilot-r14/review-claude.md §2.1): the relay
ignored thinking=disabled. Judge replies grew from about 340 to 5,300 output tokens, one above
max_tokens; the runtime returned its reasoning as the answer instead of calling tools and added
a ``_placeholder`` argument to a tool without parameters. A plain “OK” probe still passed with
16 output tokens, so the threshold here counts tokens a two-letter reply cannot need, and the
tool and judge paths are probed as well. Exits 1 when any probe fails.

    python -m scripts.service_probe --judge pro
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from app import ROOT, build_model
from harness.llm import RoleModelSpec, role_model

PROMPT = "连接测试，请仅回复OK。"
TOOL_PROMPT = "连接测试：请调用 get_profile 工具，不要输出任何文字。"
TOOL = {
    "type": "function",
    "function": {
        "name": "get_profile",
        "description": "读取当前用户的资料。",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}
# A reply of “OK” is one or two tokens; a tool call with no arguments a few dozen at most.
MAX_REPLY_TOKENS = 3
MAX_CALL_TOKENS = 40


def problems_of(kind: str, response) -> list[str]:
    found = []
    if response.reasoning_tokens:
        found.append(f"reasoning_tokens={response.reasoning_tokens}")
    if response.reasoning_content:
        found.append(f"reasoning_content 有 {len(response.reasoning_content)} 字")
    if not response.usage_available:
        found.append("没有 usage")
    if kind == "reply":
        if response.text.strip().rstrip("。.!！").upper() != "OK":
            found.append(f"回复不是 OK（{len(response.text)} 字）")
        if response.output_tokens > MAX_REPLY_TOKENS:
            found.append(f"output_tokens={response.output_tokens} > {MAX_REPLY_TOKENS}")
        if response.tool_calls:
            found.append("回复里调用了工具")
    else:
        calls = response.tool_calls
        if len(calls) != 1 or calls[0].name != "get_profile":
            found.append(f"没有恰好一次 get_profile 调用（{[c.name for c in calls]}）")
        elif calls[0].argument_error or calls[0].arguments:
            found.append(f"参数不是空对象：{sorted((calls[0].arguments or {}).keys())}")
        if response.text.strip():
            found.append(f"工具调用之外还返回了 {len(response.text)} 字正文")
        if response.output_tokens > MAX_CALL_TOKENS:
            found.append(f"output_tokens={response.output_tokens} > {MAX_CALL_TOKENS}")
    return found


async def probe(name: str, model, kind: str) -> dict:
    messages = [dict(role="user", content=PROMPT if kind == "reply" else TOOL_PROMPT)]
    started = time.perf_counter()
    try:
        response = await model.chat(messages, [] if kind == "reply" else [TOOL])
    except Exception as exc:  # the record names the error, never the endpoint or key
        return dict(
            probe=name,
            ok=False,
            error_type=type(exc).__name__,
            status_code=getattr(exc, "status_code", None),
        )
    finally:
        latency = round(time.perf_counter() - started, 3)
    found = problems_of(kind, response)
    return dict(
        probe=name,
        ok=not found,
        problems=found,
        requested_model=getattr(model, "model", None),
        returned_model=response.model,
        output_tokens=response.output_tokens if response.usage_available else None,
        reasoning_tokens=response.reasoning_tokens,
        finish_reason=response.finish_reason,
        tool_calls=[c.name for c in response.tool_calls],
        latency_s=latency,
    )


async def main(judge: str | None, output: Path) -> int:
    load_dotenv(ROOT / ".env")
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    runtime = build_model(
        config["llm"]["provider"],
        (config.get("models") or {}).get("orchestrator") or config["llm"]["model"],
        config,
        None,
    )
    models = [runtime]
    records = []
    try:
        records.append(await probe("runtime_reply", runtime, "reply"))
        records.append(await probe("runtime_tool_call", runtime, "tool"))
        if judge:
            judge_model = role_model(RoleModelSpec(**config["eval_judges"][judge]), 120)
            models.append(judge_model)
            records.append(await probe(f"judge_{judge}_reply", judge_model, "reply"))
    finally:
        for model in models:
            await model.close()
    report = dict(
        ok=all(r["ok"] for r in records),
        thresholds=dict(reply_tokens=MAX_REPLY_TOKENS, tool_call_tokens=MAX_CALL_TOKENS),
        probes=records,
        note="Returned model names are service metadata, not independent identity evidence.",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--judge", help="config.yaml 中 eval_judges 的名字，例如 pro")
    parser.add_argument(
        "--output", type=Path, default=Path("reports/connectivity/service-probe.json")
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.judge, args.output)))
