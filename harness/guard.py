from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError

from harness.models import ToolCall, ToolResult
from harness.refs import transform
from harness.registry import Registry
from harness.session import Session


class Guard:
    def __init__(self, registry: Registry):
        self.registry = registry

    def check(
        self, call: ToolCall, session: Session
    ) -> tuple[BaseModel | None, ToolResult | None, str]:
        if session.birth_binding:
            session.profile.update(
                {
                    k: v
                    for k, v in session.birth_binding["profile"].items()
                    if session.role == "orchestrator" or k in session.profile
                }
            )
        if call.argument_error:
            try:
                json.loads(call.raw_arguments or "")
                detail = "须为 JSON 对象"
            except (json.JSONDecodeError, TypeError) as exc:
                detail = (
                    f"{exc.msg}，第 {exc.pos} 个字符附近"
                    if isinstance(exc, json.JSONDecodeError)
                    else "参数须为 JSON 字符串"
                )
            return (
                None,
                ToolResult.failure(
                    "invalid_arguments", f"工具参数必须是合法JSON对象（{detail}），请修正后重试"
                ),
                "",
            )
        tool = self.registry.tools.get(call.name)
        if tool is None:
            return None, ToolResult.failure("unknown_tool", "工具未注册"), ""
        if session.pinned_reading_id and call.name not in {
            "read_reading",
            "lookup_meaning",
            "submit_reading",
            "get_profile",
            "ask_user",
        }:
            return (
                None,
                ToolResult.failure(
                    "followup_only", "本次问题只解释所选历史记录；重新计算请开启新对话。"
                ),
                "",
            )
        if session.role not in tool.roles:
            return None, ToolResult.failure("permission_denied", "当前角色无权调用该工具"), ""
        if session.partition and tool.partition not in (None, session.partition):
            return None, ToolResult.failure("partition_denied", "不能访问其他体系的工具"), ""
        try:
            args = tool.input_model.model_validate(transform(call.arguments, session, restore=True))
        except ValidationError as exc:
            fields = "；".join(
                f"{'.'.join(map(str, e['loc']))}：{e['msg']}" for e in exc.errors()[:5]
            )
            return None, ToolResult.failure("invalid_arguments", f"参数不符合 schema：{fields}"), ""
        if session.partition and hasattr(args, "system") and args.system != session.partition:
            return None, ToolResult.failure("partition_denied", "不能查询其他知识分区"), ""
        missing = sorted(k for k in tool.required_profile if session.profile.get(k) is None)
        if missing:
            return (
                None,
                ToolResult.failure("missing_profile", f"需要追问：{', '.join(missing)}"),
                "",
            )
        if tool.dependency:
            expected = session.state.get(tool.dependency)
            actual = (
                getattr(args, tool.dependency_argument, None)
                if tool.dependency_argument
                else expected
            )
            if not expected or actual != expected:
                return (
                    None,
                    ToolResult.failure("missing_dependency", f"需要本次有效的 {tool.dependency}"),
                    "",
                )
        if tool.validator:
            error = tool.validator(args, session)
            if error:
                return None, ToolResult.failure("validation_failed", error), ""
        context = [session.state.get(field) for field in tool.cache_state_keys]
        if tool.cache_user_input:
            context.append(len(session.user_messages))
            context.append(sorted(args.model_fields_set))
        profile_version = (
            None if call.name == "update_profile" else session.profile.get("version", 0)
        )
        key = (
            f"{session.state.get('active_reading_id', '')}:{profile_version}:{context}:{call.name}:"
            + json.dumps(
                args.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        # Permission, provenance and validation always run before returning cached data.
        if tool.idempotent and key in session.cache:
            return args, session.cache[key].model_copy(update={"cached": True}), key
        if tool.exclusive_key and session.state.get(tool.exclusive_key):
            return (
                None,
                ToolResult.failure(
                    "duplicate_operation", "本次占卜已执行；重抽需用户明确要求并开启新记录"
                ),
                key,
            )
        return args, None, key
