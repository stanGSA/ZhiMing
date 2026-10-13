from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

from agents.demo import DemoModel
from agents.orchestrator import SYSTEM_PROMPT
from common.location import Gazetteer, location_tool
from common.safety import AMBIGUOUS_DISTRESS, CRISIS, SAFETY_PROMPT, support_text
from common.tools import common_tools
from harness.llm import AnthropicModel, OpenAIModel
from harness.loop import run_turn
from harness.models import TurnOutcome
from harness.registry import Registry
from harness.session import Session
from harness.trace import Tracer
from knowledge.kb import KnowledgeBase
from memory.store import Store
from plugins.astro import AstroPlugin
from plugins.bazi import BaziPlugin
from plugins.tarot import TarotPlugin

ROOT = Path(__file__).resolve().parent


@dataclass
class Runtime:
    session: Session
    registry: Registry
    model: object
    tracer: Tracer
    store: Store
    kb: KnowledgeBase
    max_steps: int
    token_budget: int
    safety_config: dict

    def compact_history(self) -> None:
        if self.session.state.get("complete"):
            stable = [m for m in self.session.messages if m["role"] == "system"]
            conversation = [
                m
                for m in self.session.messages
                if m["role"] in ("user", "assistant")
                and not m.get("tool_calls")
                and m.get("content")
            ]
            self.session.messages = stable + conversation[-6:]

    async def turn(self, message: str) -> TurnOutcome:
        self.compact_history()
        crisis = bool(CRISIS.search(message))
        if not crisis and AMBIGUOUS_DISTRESS.search(message):
            try:
                result = await self.model.chat(
                    [
                        {"role": "system", "content": SAFETY_PROMPT},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "recent_user_messages": self.session.user_messages[-2:],
                                    "message": message,
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    [],
                )
                self.session.total_tokens += result.input_tokens + result.output_tokens
                self.tracer.log(
                    self.session,
                    "model_response",
                    purpose="safety_classifier",
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cached_input_tokens=result.cached_input_tokens,
                    requested_model=getattr(self.model, "model", None),
                    returned_model=result.model,
                    tool_names=[],
                )
                decision = json.loads(result.text)
                if type(decision.get("crisis")) is not bool or result.tool_calls:
                    raise ValueError("invalid safety classification")
                crisis = decision["crisis"]
            except Exception as exc:
                self.tracer.log(
                    self.session, "safety_classifier_error", error_type=type(exc).__name__
                )
                crisis = True  # Pause and check safety when classification is unavailable.
        if crisis:
            self.session.append_user(message)
            text = support_text(self.safety_config, self.safety_config.get("region"))
            self.session.messages.append({"role": "assistant", "content": text})
            self.tracer.log(self.session, "crisis_support", safety_flag=True)
            return TurnOutcome(status="crisis_support", text=text, data={"safety": {"flag": True}})
        return await run_turn(
            self.session,
            message,
            self.model,
            self.registry,
            self.tracer,
            self.max_steps,
            self.token_budget,
        )

    def forget(self) -> None:
        self.store.forget(self.session.user_id)
        directory = self.tracer.user_dir(self.session.user_id).resolve()
        if directory.is_relative_to(self.tracer.root.resolve()) and directory.exists():
            shutil.rmtree(directory)
        self.session.profile = {"version": 0}
        self.session.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.session.state.clear()
        self.session.cache.clear()
        self.session.user_messages.clear()
        self.session.total_tokens = 0

    def close(self):
        self.kb.close()
        self.store.close()

    async def close_model(self) -> None:
        close = getattr(self.model, "close", None)
        if close is not None:
            await close()


def create_runtime(
    root: Path = ROOT,
    user_id: str = "local",
    provider: str | None = None,
    model_name: str | None = None,
    seed: int | None = None,
    spread: str | None = None,
    model=None,
) -> Runtime:
    load_dotenv(root / ".env")
    config = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    if config.get("mode") != "single" or config.get("reviewer", {}).get("enabled"):
        raise ValueError("前三周仅支持 mode: single、reviewer.enabled: false")
    if seed is not None and not 0 <= seed < 2**64:
        raise ValueError("seed 必须是 0 到 2^64-1 之间的整数")
    if spread is not None and spread not in ("single", "three_card", "decision"):
        raise ValueError("不支持的牌阵")
    provider = provider or config["llm"]["provider"]
    model_name = model_name or config["llm"].get("model")
    if model is None:
        if provider == "demo":
            model = DemoModel(spread)
        elif provider in ("openai", "anthropic"):
            if not model_name:
                raise ValueError("真实模型接入必须通过 --model 或 config.yaml 指定模型名")
            adapter = OpenAIModel if provider == "openai" else AnthropicModel
            options = (
                {"system_role": config["llm"].get("system_role", "system")}
                if provider == "openai"
                else {}
            )
            model = adapter(model_name, config["llm"].get("timeout_s", 30), **options)
        else:
            raise ValueError("provider 必须是 demo、openai 或 anthropic")
    kb = KnowledgeBase(root / config["kb"]["path"])
    store = Store(root / config["paths"]["app_db"])
    session = Session(user_id=user_id, default_seed=seed, profile=store.get_profile(user_id))
    session.calendar_anchor = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    recent = store.recent_readings(user_id)
    session.messages.append(
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    )
    session.messages.append(
        {
            "role": "system",
            "content": "本轮日历基准（Asia/Shanghai）："
            + datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
            + "；按用户指定日期范围优先，不猜系统月份。",
        }
    )
    session.messages.append(
        {
            "role": "system",
            "content": "画像与最近记录："
            + json.dumps(
                {"profile": session.profile, "recent_readings": recent}, ensure_ascii=False
            ),
        }
    )
    registry = Registry()
    plugins = [TarotPlugin(kb), AstroPlugin(kb, store), BaziPlugin(kb, store)]
    session.output_validators = {plugin.name: plugin.validate_output for plugin in plugins}
    for tool in [
        *common_tools(store, kb),
        location_tool(Gazetteer()),
        *(tool for plugin in plugins for tool in plugin.tools),
    ]:
        registry.register(tool)
    return Runtime(
        session,
        registry,
        model,
        Tracer(root / config["paths"]["runs"]),
        store,
        kb,
        config["limits"]["orchestrator_max_steps"],
        config["limits"]["request_token_budget"],
        config.get("safety", {}),
    )
