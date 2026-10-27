"""Bound model context without dropping authoritative calculation/session state."""

import json

from harness.refs import transform

CONTEXT_CHAR_LIMIT = 64000
SNAPSHOT_PREFIX = "本地恢复快照（以下JSON是已有资料和工具结果，不是新的用户指令）：\n"


def compact_context(session, registry, limit=CONTEXT_CHAR_LIMIT, *, force=False):
    before = len(json.dumps(session.messages, ensure_ascii=False))
    if not force and before <= limit:
        return False
    state = session.state
    snapshot = {
        "profile": bounded(session.profile),
        "reading": {
            k: state[k]
            for k in (
                "active_reading_id",
                "question",
                "systems",
                "complete",
                "response_mode",
                "requested_spread",
                "chart_id",
                "bazi_id",
                "timeframe",
                "timeframe_tz",
            )
            if k in state
        },
        "tarot_result": state.get("tarot_result"),
        "calculations": {},
        "specialist_results": bounded(
            {
                system: facts.get("values", {})
                for system, facts in state.get("specialist_facts", {}).items()
            }
        ),
        "last_errors": [],
        # Keep the whole failed draft: generic truncation would silently drop sections or
        # turn a long JSON string into an invalid patch target on a continuation request.
        "failed_submission": state.get("failed_submission"),
    }
    projectors = {
        "natal_result": "compute_natal_chart",
        "transit_result": "compute_transits",
        "bazi_result": "compute_bazi",
        "bazi_period_result": "compute_bazi_period",
    }
    # All full facts stay in session.state. Keep a bounded model view with the same refs;
    # computations may be called again (cached), while an existing draw must never repeat.
    for key, result in state.get("calculations", {}).items():
        tool = registry.tools.get(projectors.get(key, ""))
        projected = tool.model_result(result) if tool and tool.model_result else result
        snapshot["calculations"][key] = bounded(projected)
    for message in session.messages:
        if message["role"] != "tool":
            continue
        try:
            result = json.loads(message.get("content", ""))
        except (ValueError, TypeError):
            continue
        if not result.get("ok"):
            snapshot["last_errors"].append({k: result.get(k) for k in ("code", "error")})
    snapshot["last_errors"] = bounded(snapshot["last_errors"][-3:])
    stable = [m for m in session.messages if m["role"] == "system"]
    conversation = [
        m
        for m in session.messages
        if m["role"] in ("user", "assistant")
        and not m.get("tool_calls")
        and m.get("content")
        and m["content"] != session.continue_prompt
        and not m["content"].startswith(SNAPSHOT_PREFIX)
    ][-6:]
    last_user = next((m for m in reversed(conversation) if m["role"] == "user"), None)
    conversation = [
        {"role": m["role"], "content": m["content"] if m is last_user else m["content"][-4000:]}
        for m in conversation
    ]
    packet = transform(snapshot, session)
    encoded = json.dumps(packet, ensure_ascii=False, default=str)
    # Prefer the draw and input/reading identity when a multi-system snapshot is huge.
    if len(encoded) > limit // 2:
        packet["calculations"] = {
            k: {
                field: v
                for field, v in value.items()
                if field
                in (
                    "chart_id",
                    "bazi_id",
                    "input",
                    "pillars",
                    "day_master",
                    "status",
                )
            }
            for k, value in packet["calculations"].items()
            if isinstance(value, dict)
        }
        packet["specialist_results"] = {
            system: {k: v for k, v in facts.items() if k in ("tarot_result", "chart_id", "bazi_id")}
            for system, facts in packet["specialist_results"].items()
        }
        packet["recovery"] = (
            "部分计算细节已移出上下文；请复用原计算ID或重新调用缓存计算取得引用，不得猜测。"
        )
        encoded = json.dumps(packet, ensure_ascii=False, default=str)
    # Put the original latest question after the snapshot, preserving model turn semantics.
    session.messages = (
        stable + [{"role": "user", "content": SNAPSHOT_PREFIX + encoded}] + conversation
    )
    return True


def bounded(value):
    if isinstance(value, dict):
        return {k: bounded(v) for k, v in value.items() if k not in ("signals", "analysis")}
    if isinstance(value, list):
        return [bounded(v) for v in value[:24]]
    if isinstance(value, str):
        return value[:2000]
    return value
