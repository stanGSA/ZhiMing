from __future__ import annotations

import asyncio
import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

from agents.consult import ConsultService
from agents.demo import DemoModel
from agents.orchestrator import MULTI_SYSTEM_PROMPT, SYSTEM_PROMPT
from agents.reviewer import ReviewerService
from agents.specialists import build_specialists
from common.location import Gazetteer, location_tool
from common.safety import AMBIGUOUS_DISTRESS, CRISIS, SAFETY_PROMPT, support_text
from common.tools import common_tools
from harness.budget import Budget
from harness.llm import AnthropicModel, OpenAIModel
from harness.loop import TIMEOUT_TEXT, run_turn
from harness.models import TurnOutcome
from harness.registry import Registry
from harness.session import Session
from harness.trace import Tracer
from knowledge.kb import KnowledgeBase
from memory.store import Store
from plugins.astro import AstroPlugin
from plugins.bazi import BaziPlugin
from plugins.daily import DailyPlugin
from plugins.dream import DreamPlugin
from plugins.name import NamePlugin
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
    mode: str = "single"
    specialist_model: object | None = None
    request_timeout_s: float | None = None
    system_prompt: str = SYSTEM_PROMPT
    reviewer_model: object | None = None

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
        # One budget per user request, shared by the orchestrator and every specialist. The
        # wall-clock deadline guards multi-agent fan-out only; single mode keeps week 1-3 limits.
        deadline = (
            time.monotonic() + self.request_timeout_s
            if self.mode == "multi" and self.request_timeout_s
            else None
        )
        self.session.budget = Budget(self.token_budget, deadline=deadline)
        turn = run_turn(
            self.session,
            message,
            self.model,
            self.registry,
            self.tracer,
            self.max_steps,
            self.token_budget,
            admission=self.mode == "multi",
        )
        if deadline is None:
            return await turn
        try:
            # Hard wall clock for the whole request: cancels running specialists too. The loop
            # already stops at the deadline between and during model calls; this also bounds
            # tool execution such as waiting on specialists.
            return await asyncio.wait_for(turn, self.request_timeout_s)
        except TimeoutError:
            self.tracer.log(self.session, "request_timeout", timeout_s=self.request_timeout_s)
            return TurnOutcome(status="timeout", text=TIMEOUT_TEXT)

    def forget(self) -> None:
        self.store.forget(self.session.user_id)
        directory = self.tracer.user_dir(self.session.user_id).resolve()
        if directory.is_relative_to(self.tracer.root.resolve()) and directory.exists():
            shutil.rmtree(directory)
        self.session.profile = {"version": 0}
        self.session.messages = [{"role": "system", "content": self.system_prompt}]
        self.session.state.clear()
        self.session.cache.clear()
        self.session.user_messages.clear()
        self.session.total_tokens = 0

    def close(self):
        self.kb.close()
        self.store.close()

    async def close_model(self) -> None:
        models = [self.model]
        for extra in (self.specialist_model, self.reviewer_model):
            if extra is not None and all(extra is not m for m in models):
                models.append(extra)
        for model in models:
            close = getattr(model, "close", None)
            if close is not None:
                await close()


def build_model(provider: str, model_name: str | None, config: dict, spread: str | None):
    if provider == "demo":
        return DemoModel(spread)
    if provider in ("openai", "anthropic"):
        if not model_name:
            raise ValueError("真实模型接入必须通过 --model 或 config.yaml 指定模型名")
        adapter = OpenAIModel if provider == "openai" else AnthropicModel
        options = (
            {"system_role": config["llm"].get("system_role", "system")}
            if provider == "openai"
            else {}
        )
        return adapter(model_name, config["llm"].get("timeout_s", 30), **options)
    raise ValueError("provider 必须是 demo、openai 或 anthropic")


def create_runtime(
    root: Path = ROOT,
    user_id: str = "local",
    provider: str | None = None,
    model_name: str | None = None,
    seed: int | None = None,
    spread: str | None = None,
    model=None,
    mode: str | None = None,
    specialist_model=None,
    reviewer_model=None,
    strictness: str | None = None,
) -> Runtime:
    load_dotenv(root / ".env")
    config = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    mode = mode or config.get("mode", "single")
    if mode not in ("single", "multi"):
        raise ValueError("mode 必须是 single 或 multi")
    review_config = dict(config.get("reviewer") or {})
    if strictness is not None:
        review_config["strictness"] = strictness
    if review_config.get("strictness", "lenient") not in ("lenient", "strict", "off"):
        raise ValueError("reviewer.strictness 必须是 lenient、strict 或 off")
    # The reviewer belongs to multi-agent mode; single mode stays the week 1-3 baseline.
    reviewing = (
        mode == "multi"
        and bool(review_config.get("enabled"))
        and review_config.get("strictness", "lenient") != "off"
    )
    if seed is not None and not 0 <= seed < 2**64:
        raise ValueError("seed 必须是 0 到 2^64-1 之间的整数")
    if spread is not None and spread not in ("single", "three_card", "decision"):
        raise ValueError("不支持的牌阵")
    provider = provider or config["llm"]["provider"]
    models = config.get("models") or {}
    model_name = model_name or models.get("orchestrator") or config["llm"].get("model")
    specialist_name = model_name if not models.get("specialist") else models["specialist"]
    reviewer_name = models.get("reviewer") or specialist_name
    injected = model is not None
    if model is None:
        model = build_model(provider, model_name, config, spread)
    if mode == "multi" and specialist_model is None:
        # An injected (scripted) or demo model also serves the specialists; it can route by
        # the session's role and tool table.
        if injected or provider == "demo" or specialist_name == model_name:
            specialist_model = model
        else:
            specialist_model = build_model(provider, specialist_name, config, spread)
    if reviewing and reviewer_model is None:
        if injected or provider == "demo" or reviewer_name == model_name:
            reviewer_model = model
        elif reviewer_name == specialist_name:
            reviewer_model = specialist_model
        else:
            reviewer_model = build_model(provider, reviewer_name, config, spread)
    kb = KnowledgeBase(root / config["kb"]["path"])
    store = Store(root / config["paths"]["app_db"])
    session = Session(user_id=user_id, default_seed=seed, profile=store.get_profile(user_id))
    session.calendar_anchor = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    recent = store.recent_readings(user_id)
    system_prompt = MULTI_SYSTEM_PROMPT if mode == "multi" else SYSTEM_PROMPT
    session.messages.append({"role": "system", "content": system_prompt})
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
    plugins = [
        TarotPlugin(kb),
        AstroPlugin(kb, store),
        BaziPlugin(kb, store),
        NamePlugin(kb, store),
        DreamPlugin(kb, config["kb"].get("dream_match_threshold")),
    ]
    # Daily fortune is a deterministic composition the orchestrator calls directly; its facts
    # are checked by the astro, bazi and tarot validators.
    daily = DailyPlugin(kb, store)
    session.output_validators = {plugin.name: plugin.validate_output for plugin in plugins}
    tracer = Tracer(root / config["paths"]["runs"])
    reviewer = (
        ReviewerService(reviewer_model, tracer, review_config, config["limits"])
        if reviewing
        else None
    )
    shared = common_tools(store, kb, mode, reviewer)
    tools = [*shared, location_tool(Gazetteer()), *daily.tools]
    if mode == "single":
        tools.extend(tool for plugin in plugins for tool in plugin.tools)
    else:
        # Computation tools exist only in the specialists' own registries.
        lookup = next(tool for tool in shared if tool.name == "lookup_meaning")
        specialists = build_specialists(plugins, lookup)
        tools.append(ConsultService(specialists, specialist_model, tracer, config["limits"]).tool())
    for tool in tools:
        registry.register(tool)
    return Runtime(
        session,
        registry,
        model,
        tracer,
        store,
        kb,
        config["limits"]["orchestrator_max_steps"],
        config["limits"]["request_token_budget"],
        config.get("safety", {}),
        mode=mode,
        specialist_model=specialist_model,
        request_timeout_s=config["limits"].get("request_timeout_s"),
        system_prompt=system_prompt,
        reviewer_model=reviewer_model if reviewing else None,
    )
