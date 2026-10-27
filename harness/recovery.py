"""Bound repeated tool failures while retaining a terminal draft for the next attempt."""

from harness.failures import failure
from harness.refs import transform

MAX_SAME_FAILURES = 3
REPAIR_HINT = (
    "按error定位并修正出错字段后重新提交，保留其他有效内容与引用；"
    "已有计算和草稿仍在当前记录中，不要通过重开记录或重复计算解决提交错误。"
)


class ToolRecovery:
    def __init__(self):
        self.failures = {}

    def observe(self, call, result, tool, session):
        if result.ok:
            self.failures = {k: v for k, v in self.failures.items() if k[0] != call.name}
            if (session.state.get("failed_submission") or {}).get("tool") == call.name:
                session.state.pop("failed_submission", None)
            return result, None
        if result.code not in ("invalid_arguments", "validation_failed", "review_revise"):
            return result, None
        if tool and tool.terminal:
            session.state["failed_submission"] = {
                "tool": call.name,
                # Store canonical refs, just like calculations. A draft containing model
                # aliases (R1, …) must not receive a second alias when it is restored.
                "arguments": transform(call.arguments, session, restore=True),
                "code": result.code,
                "error": result.error,
                "user_message_index": len(session.user_messages) - 1,
            }
        key = (call.name, result.code, result.error)
        count = self.failures.get(key, 0) + 1
        self.failures[key] = count
        result = result.model_copy(
            update={
                "data": {
                    **result.data,
                    "recovery": {
                        "attempt": count,
                        "max_same_failure_attempts": MAX_SAME_FAILURES,
                        "instruction": REPAIR_HINT,
                    },
                }
            }
        )
        if count < MAX_SAME_FAILURES:
            return result, None
        return result, failure(
            session,
            "validation_stalled",
            "repeated_tool_failure",
            "解读连续核对未通过，本轮已停止重复尝试；可以继续当前问题，复用已有计算修正解读。",
        )
