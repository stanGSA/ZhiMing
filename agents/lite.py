"""Deterministic specialist plan followed by at most two real report attempts.

All planned calls still travel through run_turn, Guard and the normal trace.
"""

import json
import re
import uuid

from common.input_evidence import gender_evidence, solar_time_choice
from common.time_utils import NeedsInput
from harness.models import ModelResponse, ToolCall
from plugins.astro.tools import BirthInput
from plugins.bazi.tools import BaziInput
from plugins.context import birth_provenance, period_timezone


class LiteModel:
    def __init__(self, model, session, system, request):
        self.backend = model
        self.model = getattr(model, "model", None)
        self.session = session
        self.system = system
        self.request = request
        self.report_attempts = 0

    def call(self, name, **arguments):
        return ModelResponse(
            planned=True, tool_calls=[ToolCall(id=uuid.uuid4().hex, name=name, arguments=arguments)]
        )

    async def chat(self, messages, tools):
        state = self.session.state
        # A rejected planned call must not loop: let one real model correct it, within
        # the same two-attempt cap used for reports.
        last = json.loads(messages[-1]["content"]) if messages[-1]["role"] == "tool" else {}
        rejected = last and not last.get("ok")
        if not rejected:
            if self.system == "tarot" and not state.get("tarot_result"):
                return self.call(
                    "draw_tarot",
                    spread=state.get("requested_spread") or "three_card",
                    question=self.request.sub_question,
                )
            if self.system in ("astro", "bazi"):
                result_key = "natal_result" if self.system == "astro" else "bazi_result"
                if not state.get(result_key):
                    args = (
                        BirthInput(location_id=self.request.location_id)
                        if self.system == "astro"
                        else BaziInput(location_id=self.request.location_id)
                    )
                    text = " ".join(self.session.user_messages)
                    if self.session.profile.get("time_known") is False or re.search(
                        r"(?:不知道|不知|未知|不确定|查不到).{0,6}(?:出生时间|时间|时辰|几点)"
                        r"|(?:出生时间|时辰).{0,6}(?:不知道|未知|不知|不确定|不详|查不到)",
                        text,
                    ):
                        args.time_known = False
                    birth_provenance(args, self.session)
                    if self.system == "bazi":
                        args.gender = self.session.profile.get("gender")
                        genders = gender_evidence(text)
                        if len(genders) == 1:
                            args.gender = genders.pop()
                        args.true_solar_time = self.session.profile.get("true_solar_time", False)
                        choice = solar_time_choice(text)
                        if choice is not None:
                            args.true_solar_time = choice
                        args.zishi_rule = self.session.profile.get("zishi_rule", "next_day")
                        if re.search(r"(?:0|零|子正)点?换日|same_day", text):
                            args.zishi_rule = "same_day"
                        if "physical" in text or "物理时刻起运" in text:
                            args.dayun_time_basis = "physical"
                        if "农历" in text or self.session.profile.get("calendar_input") == "lunar":
                            args.calendar = "lunar"
                            args.calendar_confirmed = True
                            args.lunar_date = args.birth_local[:10] if args.birth_local else None

                    return self.call(
                        "compute_natal_chart" if self.system == "astro" else "compute_bazi",
                        **args.model_dump(exclude_unset=True),
                    )
                period = "transit_result" if self.system == "astro" else "bazi_period_result"
                if self.request.timeframe and not state.get(period):
                    chart = state[result_key]
                    try:
                        tz = period_timezone(self.request.timeframe, self.session, chart)
                    except NeedsInput:
                        tz = self.request.timeframe.tz
                    key = "chart_id" if self.system == "astro" else "bazi_id"
                    return self.call(
                        "compute_transits" if self.system == "astro" else "compute_bazi_period",
                        **{
                            key: state[key],
                            "start": self.request.timeframe.start,
                            "end": self.request.timeframe.end,
                            "tz": tz,
                        },
                    )
        if self.report_attempts >= 2:
            return ModelResponse(text="专家报告两次提交仍未通过校验")
        self.report_attempts += 1
        # A failed calculation needs its calculation tools to remain available;
        # report-only schemas apply only after a successful deterministic plan.
        return await self.backend.chat(
            messages,
            tools if rejected else [t for t in tools if t["function"]["name"] == "submit_report"],
        )
