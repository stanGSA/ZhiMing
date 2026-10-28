from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from harness.models import ToolResult
from harness.refs import constrain
from harness.session import Session


@dataclass
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[..., Any]
    roles: frozenset[str] = frozenset({"orchestrator"})
    partition: str | None = None
    required_profile: frozenset[str] = frozenset()
    dependency: str | None = None
    dependency_argument: str | None = None
    idempotent: bool = True
    terminal: bool = False
    exclusive_key: str | None = None
    cache_state_keys: tuple[str, ...] = ()
    cache_user_input: bool = False
    validator: Callable[[BaseModel, Session], str | None] | None = None
    model_result: Callable[[dict], dict] | None = None
    # Calls of a parallel_safe tool in one model step run concurrently; commit then applies
    # each result to the session one at a time, in the order the model issued the calls.
    parallel_safe: bool = False
    commit: Callable[[ToolResult, Session], ToolResult] | None = None

    available: Callable[[Session], bool] | None = None

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_model.model_json_schema(),
            },
        }


@dataclass
class Registry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"Duplicate tool: {tool.name}")
        self.tools[tool.name] = tool

    def schemas(self, session: Session) -> list[dict[str, Any]]:
        return [
            constrain(t.schema(), session)
            for t in self.tools.values()
            if session.role in t.roles
            and (session.partition is None or t.partition in (None, session.partition))
            and (t.available is None or t.available(session))
        ]

    async def run(self, name: str, arguments: BaseModel, session: Session) -> ToolResult:
        value = self.tools[name].handler(arguments, session)
        if inspect.isawaitable(value):
            value = await value
        return value if isinstance(value, ToolResult) else ToolResult(data=value)
