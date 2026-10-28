from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextvars import ContextVar

from harness.budget import Budget
from harness.context import compact_context
from harness.failures import failure, model_failure
from harness.guard import Guard
from harness.models import ToolCall, ToolResult, TurnOutcome
from harness.refs import transform
from harness.registry import Registry
from harness.session import Session
from harness.trace import Tracer

# Id of the tool call whose handler is running; task-local under asyncio.gather, so a handler
# that spawns a child session can link the child's trace to the exact parent call.
CURRENT_CALL_ID: ContextVar[str | None] = ContextVar("current_call_id", default=None)
OUTPUT_ALLOWANCE = 2048
REPEATED_FAILURE_LIMIT = 3
TIMEOUT_TEXT = "本轮超过请求时限，尚未形成通过校验的解读。已有计算保留，可以继续。"


def estimate_call(
    messages: list[dict], tools: list[dict], last_input: int | None, last_count: int
) -> int:
    """Admission estimate for one model call: input tokens plus an output allowance.

    After the first call the real input count of the previous call is known, so only the
    messages appended since then are estimated (two characters per token on average).
    """
    if last_input is None:
        text = json.dumps([messages, tools], ensure_ascii=False)
        return len(text) // 2 + OUTPUT_ALLOWANCE
    text = json.dumps(messages[last_count:], ensure_ascii=False)
    return last_input + len(text) // 2 + OUTPUT_ALLOWANCE


async def run_turn(
    session: Session,
    user_msg: str,
    model,
    registry: Registry,
    tracer: Tracer,
    max_steps: int = 12,
    token_budget: int = 60000,
    *,
    as_evidence: bool = True,
    admission: bool = False,
    on_tool_result: Callable[[ToolCall, ToolResult], TurnOutcome | None] | None = None,
) -> TurnOutcome:
    if as_evidence:
        session.append_user(user_msg)
    else:
        # Text written by another agent is context for the model, never evidence of what
        # the user said; provenance checks only ever read session.user_messages.
        session.messages.append({"role": "user", "content": user_msg})
    guard = Guard(registry)
    budget = Budget(token_budget, parent=session.budget)
    session.turn_budget = budget
    # With admission the estimated cost of each call is held before it is made, so concurrent
    # child sessions cannot overcommit a shared budget. Without it (single mode) a call is
    # allowed while any budget is left, exactly as in weeks 1-3.

    async def execute(call: ToolCall, args) -> ToolResult:
        token = CURRENT_CALL_ID.set(call.id)
        try:
            return await registry.run(call.name, args, session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return ToolResult.failure("tool_error", f"工具执行失败（{type(exc).__name__}）")
        finally:
            CURRENT_CALL_ID.reset(token)

    def timed_out(step: int) -> TurnOutcome:
        tracer.log(session, "timeout", step=step)
        return failure(
            session, "timeout", "request_timeout", "本轮达到请求时限，请稍后继续或缩小问题范围。"
        )

    last_input, last_count = None, 0
    failed_attempts: dict[tuple, int] = {}
    limit_reason = "step_limit"
    for step in range(max_steps):
        if budget.expired():
            return timed_out(step)
        if compact_context(session, registry):
            last_input, last_count = None, 0
            tracer.log(session, "context_compacted", step=step)
        tools = registry.schemas(session)
        estimate = (
            estimate_call(session.messages, tools, last_input, last_count) if admission else 0
        )
        if not budget.admit(estimate):
            limit_reason = "token_budget"
            tracer.log(
                session, "budget_denied", step=step, estimate=estimate, remaining=budget.remaining()
            )
            break
        try:
            left = budget.time_left()
            call = model.chat(session.messages, tools)
            response = await (call if left is None else asyncio.wait_for(call, left))
        except Exception as exc:
            budget.release(estimate)
            if isinstance(exc, TimeoutError) and budget.expired():
                return timed_out(step)
            # API exceptions can contain request headers or credentials: never log their text.
            tracer.log(session, "model_error", error_type=type(exc).__name__, step=step)
            return model_failure(session, exc)
        except asyncio.CancelledError:
            budget.release(estimate)
            raise
        if not response.planned:
            session.model_calls += 1
        used = response.input_tokens + response.output_tokens
        budget.settle(estimate, used)
        if admission and used > estimate:
            tracer.log(session, "budget_overrun", step=step, estimate=estimate, actual=used)
        if not response.planned:
            last_input, last_count = response.input_tokens, len(session.messages)
        session.total_tokens += used
        tracer.log(
            session,
            "tool_plan" if response.planned else "model_response",
            step=step,
            input_tokens=response.input_tokens if response.usage_available else None,
            output_tokens=response.output_tokens if response.usage_available else None,
            usage_available=response.usage_available,
            cached_input_tokens=response.cached_input_tokens,
            reasoning_tokens=response.reasoning_tokens,
            finish_reason=response.finish_reason,
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
        if budget.expired():
            return timed_out(step)  # A response that arrives after the deadline is not acted on.
        if budget.overdrawn():
            limit_reason = "token_budget"
            break  # Do not execute side effects from an over-budget response.
        if response.finish_reason == "length":
            tracer.log(session, "output_truncated", step=step)
            return failure(
                session,
                "output_truncated",
                "output_limit",
                "模型输出达到单次上限；请缩小问题范围或调整单次输出上限。",
            )
        if not response.tool_calls:
            if session.state.get("active_reading_id") and not session.state.get("complete"):
                session.messages.append(response.assistant_message())
                session.messages.append({"role": "user", "content": session.continue_prompt})
                continue
            session.messages.append(response.assistant_message())
            return TurnOutcome(status="text", text=response.text)
        session.messages.append(response.assistant_message())
        terminal = None
        calls = response.tool_calls
        answered = 0
        try:
            index = 0
            while index < len(calls):
                # Consecutive parallel-safe calls form one concurrent group; everything else runs
                # alone so that earlier calls can change the state later guard checks rely on.
                group = [calls[index]]
                index += 1
                if is_parallel(registry, group[0]):
                    while index < len(calls) and is_parallel(registry, calls[index]):
                        group.append(calls[index])
                        index += 1
                prepared = []
                for call in group:
                    started = tracer.clock()
                    if call.arguments_repaired:
                        tracer.log(session, "arguments_repaired", step=step, tool=call.name)
                    args, pre_result, key = guard.check(call, session)
                    if terminal is not None:
                        pre_result = ToolResult.failure("turn_finished", "本轮已结束，此调用未执行")
                    prepared.append((call, args, pre_result, key, started))
                runnable = [i for i, item in enumerate(prepared) if item[2] is None]
                if len(runnable) == 1:
                    outputs = [await execute(prepared[runnable[0]][0], prepared[runnable[0]][1])]
                else:
                    # A task group, not gather: on cancellation it waits until every call has
                    # finished cleaning up, so no child outlives the request that started it.
                    async with asyncio.TaskGroup() as group:
                        tasks = [
                            group.create_task(execute(prepared[i][0], prepared[i][1]))
                            for i in runnable
                        ]
                    outputs = [task.result() for task in tasks]
                executed = dict(zip(runnable, outputs, strict=True))
                for position, (call, _args, pre_result, key, started) in enumerate(prepared):
                    tool = registry.tools.get(call.name)
                    result = pre_result if pre_result is not None else executed[position]
                    if pre_result is None and result.ok:
                        if tool.commit:
                            result = tool.commit(result, session)
                        if tool.idempotent and result.data.get("status") != "needs_input":
                            session.cache[key] = result
                        if tool.exclusive_key:
                            session.state[tool.exclusive_key] = True
                    projected = result
                    if result.ok and tool and tool.model_result:
                        projected = result.model_copy(
                            update={"data": tool.model_result(result.data)}
                        )
                    projected = projected.model_copy(
                        update={"data": transform(projected.data, session)}
                    )
                    session.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": projected.model_dump_json(),
                        }
                    )
                    answered += 1
                    tracer.log(
                        session,
                        "tool_result",
                        step=step,
                        call=call.model_dump(),
                        result=result.model_dump(),
                        latency_ms=round((tracer.clock() - started) * 1000, 3),
                    )
                    if result.ok:
                        failed_attempts = {
                            signature: count
                            for signature, count in failed_attempts.items()
                            if signature[0] != call.name
                        }
                    elif terminal is None:
                        # Submission drafts may change without repairing the error. Other
                        # tools may legitimately fail for different inputs (e.g. KB keys).
                        arguments = (
                            None
                            if tool and tool.terminal
                            else json.dumps(call.arguments, sort_keys=True, ensure_ascii=False)
                        )
                        signature = (
                            call.name,
                            result.code,
                            result.retry_key or result.error,
                            arguments,
                        )
                        count = failed_attempts.get(signature, 0) + 1
                        failed_attempts[signature] = count
                        if count >= REPEATED_FAILURE_LIMIT:
                            tracer.log(
                                session,
                                "repeated_failure_limit",
                                step=step,
                                tool=call.name,
                                code=result.code,
                                attempts=count,
                            )
                            terminal = failure(
                                session,
                                "retry_limit",
                                "repeated_tool_failure",
                                "同一处理错误重复出现3次，本轮已停止自动重试，尚未完成解读；可稍后继续。",
                            )
                    if terminal is None:
                        if result.ok and tool and tool.terminal:
                            terminal = TurnOutcome(
                                status=call.name, text=result.data.get("text", ""), data=result.data
                            )
                        elif on_tool_result is not None:
                            terminal = on_tool_result(call, result)
        except asyncio.CancelledError:
            # Keep the tool-call protocol complete for the next request, then propagate.
            for call in calls[answered:]:
                session.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": ToolResult.failure(
                            "cancelled", "请求已取消或超过时限，此调用未完成"
                        ).model_dump_json(),
                    }
                )
            raise
        if terminal:
            session.messages.append({"role": "assistant", "content": terminal.text})
            return terminal
    tracer.log(
        session, "limit_reached", reason=limit_reason, tokens=budget.used, max_steps=max_steps
    )
    text = (
        f"本轮达到执行步数上限（{max_steps}步），尚未完成解读；可继续当前问题或缩小范围。"
        if limit_reason == "step_limit"
        else "本轮达到请求token预算，尚未完成解读；可缩小问题范围后继续，下一轮预算会重置。"
    )
    return failure(session, "limit_reached", limit_reason, text)


def is_parallel(registry: Registry, call: ToolCall) -> bool:
    tool = registry.tools.get(call.name)
    return bool(tool and tool.parallel_safe and not call.argument_error)
