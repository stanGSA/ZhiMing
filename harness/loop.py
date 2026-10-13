from __future__ import annotations

import asyncio
import json

from harness.guard import Guard
from harness.models import ToolResult, TurnOutcome
from harness.registry import Registry
from harness.session import Session
from harness.trace import Tracer


async def run_turn(
    session: Session,
    user_msg: str,
    model,
    registry: Registry,
    tracer: Tracer,
    max_steps: int = 12,
    token_budget: int = 60000,
) -> TurnOutcome:
    session.append_user(user_msg)
    guard = Guard(registry)
    turn_tokens = 0
    for step in range(max_steps):
        if turn_tokens >= token_budget:
            break
        try:
            response = await model.chat(session.messages, registry.schemas(session))
        except Exception as exc:
            # API exceptions can contain request headers or credentials: never log their text.
            tracer.log(session, "model_error", error_type=type(exc).__name__, step=step)
            return TurnOutcome(
                status="model_error", text="模型调用失败，请检查模型配置、网络及密钥。"
            )
        used = response.input_tokens + response.output_tokens
        turn_tokens += used
        session.total_tokens += used
        tracer.log(
            session,
            "model_response",
            step=step,
            input_tokens=response.input_tokens if response.usage_available else None,
            output_tokens=response.output_tokens if response.usage_available else None,
            usage_available=response.usage_available,
            cached_input_tokens=response.cached_input_tokens,
            requested_model=getattr(model, "model", None),
            returned_model=response.model,
            tool_names=[c.name for c in response.tool_calls],
        )
        if not response.usage_available:
            tracer.log(session, "usage_unavailable", step=step)
            return TurnOutcome(
                status="usage_unavailable",
                text="模型服务未返回用量，本轮暂停以避免越过预算；请稍后重试。",
            )
        if turn_tokens > token_budget:
            break  # Do not execute side effects from an over-budget response.
        if not response.tool_calls:
            if session.state.get("active_reading_id") and not session.state.get("complete"):
                session.messages.append({"role": "assistant", "content": response.text})
                session.messages.append(
                    {
                        "role": "user",
                        "content": "本轮尚未完成。计算已完成则请使用 submit_reading 提交带有效引用的结果；资料或地点需要确认则必须使用 ask_user 追问结束本轮。",
                    }
                )
                continue
            session.messages.append({"role": "assistant", "content": response.text})
            return TurnOutcome(status="text", text=response.text)
        session.messages.append(
            {
                "role": "assistant",
                "content": response.text or None,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {
                            "name": c.name,
                            "arguments": c.raw_arguments
                            if c.argument_error
                            else json.dumps(c.arguments, ensure_ascii=False),
                        },
                    }
                    for c in response.tool_calls
                ],
            }
        )
        terminal = None
        for call in response.tool_calls:
            started = tracer.clock()
            args, pre_result, key = guard.check(call, session)
            if terminal is not None:
                result = ToolResult.failure("turn_finished", "本轮已结束，此调用未执行")
            elif pre_result is not None:
                result = pre_result
            else:
                try:
                    result = await registry.run(call.name, args, session)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    result = ToolResult.failure(
                        "tool_error", f"工具执行失败（{type(exc).__name__}）"
                    )
                tool = registry.tools[call.name]
                if result.ok:
                    if tool.idempotent:
                        session.cache[key] = result
                    if tool.exclusive_key:
                        session.state[tool.exclusive_key] = True
            tool = registry.tools.get(call.name)
            projected = result
            if result.ok and tool and tool.model_result:
                projected = result.model_copy(update={"data": tool.model_result(result.data)})
            session.messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": projected.model_dump_json()}
            )
            tracer.log(
                session,
                "tool_result",
                step=step,
                call=call.model_dump(),
                result=result.model_dump(),
                latency_ms=round((tracer.clock() - started) * 1000, 3),
            )
            tool = registry.tools.get(call.name)
            if terminal is None and result.ok and tool and tool.terminal:
                terminal = TurnOutcome(
                    status=call.name, text=result.data.get("text", ""), data=result.data
                )
        if terminal:
            session.messages.append({"role": "assistant", "content": terminal.text})
            return terminal
    tracer.log(session, "limit_reached", tokens=turn_tokens, max_steps=max_steps)
    return TurnOutcome(
        status="limit_reached",
        text="本轮达到步数或 token 上限，尚未形成通过校验的解读。已有抽牌保留，可以继续。",
    )
