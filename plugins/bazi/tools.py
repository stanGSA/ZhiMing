from pathlib import Path
from typing import Literal

from common.time_utils import NeedsInput
from harness.models import StrictInput, ToolResult
from harness.registry import Tool
from plugins.bazi.calculator import bazi_period, compute_bazi
from plugins.context import (
    BirthInput,
    MeaningPlugin,
    birth_provenance,
    birth_values,
    range_provenance,
)


class BaziInput(BirthInput):
    dayun_time_basis: Literal["civil", "physical"] = "civil"
    gender: Literal["male", "female"] | None = None
    true_solar_time: bool = False
    zishi_rule: Literal["next_day", "same_day"] = "next_day"
    calendar: Literal["solar", "lunar"] = "solar"
    lunar_date: str | None = None
    calendar_confirmed: bool = False
    leap_month: bool | None = None
    accept_uncertain: bool = False


class PeriodInput(StrictInput):
    bazi_id: str
    start: str
    end: str
    granularity: Literal["year", "month", "day"] = "month"
    tz: str = "Asia/Shanghai"


class BaziPlugin(MeaningPlugin):
    name = kb_partition = "bazi"
    eval_dir = Path(__file__).parent / "evals"

    def __init__(self, kb, store):
        self.kb, self.store = kb, store
        self.tools = [
            Tool(
                "compute_bazi",
                "排八字三/四柱、十神五行藏干纳音大运。缺时辰仅三柱、缺性别不排大运；农历须确认及闰月明确，MVP不判喜用神。needs_input须ask_user。",
                BaziInput,
                self.compute,
                partition="bazi",
                roles=frozenset({"orchestrator", "bazi"}),
                dependency="active_reading_id",
                validator=self.validate,
                model_result=self.project,
            ),
            Tool(
                "compute_bazi_period",
                "已有本次bazi_id算流年/节气流月/流日与原局冲合；保留精确边界。时机题必须调用，不以原局替代。",
                PeriodInput,
                self.period,
                partition="bazi",
                roles=frozenset({"orchestrator", "bazi"}),
                dependency="bazi_id",
                dependency_argument="bazi_id",
                validator=range_provenance,
                model_result=self.project,
            ),
        ]

    @staticmethod
    def project(data):
        if data.get("status") == "needs_input":
            return data
        result = {
            k: v
            for k, v in data.items()
            if k not in ("input", "hidden_ten_gods", "solar_correction_minutes")
        }
        result["interpretations"] = [
            dict(
                ref_id=i["ref_id"],
                fact=i["fact"],
                kind=i["kind"],
                key=i["key"],
                timeframe=i["timeframe"],
                meaning=dict(text=i["meaning"]["text"], reviewed=i["meaning"]["reviewed"]),
            )
            for i in data.get("interpretations", [])
            if i["kind"] not in ("stem", "branch") or ":day:" in i["fact"]
        ]
        # Keep at least one grounded atom for three-pillar charts with no ten-god facts.
        if not result["interpretations"] and data.get("interpretations"):
            i = data["interpretations"][0]
            result["interpretations"] = [
                dict(
                    ref_id=i["ref_id"],
                    fact=i["fact"],
                    meaning=dict(text=i["meaning"]["text"], reviewed=i["meaning"]["reviewed"]),
                )
            ]
        return result

    @staticmethod
    def validate(args, session):
        error = birth_provenance(args, session)
        if error:
            return error
        text = " ".join(session.user_messages)
        if args.dayun_time_basis == "physical" and not any(
            x in text for x in ("physical", "物理时刻起运")
        ):
            return "物理时刻起运口径须有用户确认"
        if (
            args.gender
            and args.gender != session.profile.get("gender")
            and not any(
                x in text
                for x in ({"male": ("男", "male"), "female": ("女", "female")}[args.gender])
            )
        ):
            return "性别必须来自用户原话或画像；未知不排大运"
        if (
            args.lunar_date
            and args.lunar_date not in text
            and args.lunar_date != session.profile.get("lunar_date")
        ):
            return "农历日期必须来自用户原话或画像"
        if (
            args.calendar == "lunar"
            and args.calendar_confirmed
            and "农历" not in text
            and session.profile.get("calendar_input") != "lunar"
        ):
            return "必须由用户确认农历输入"
        if args.accept_uncertain and not any(x in text for x in ("候选", "两种", "仍不知道")):
            return "节气当天时辰未知请先追问，不能擅自确认候选"
        if args.calendar == "lunar" and args.leap_month is not None:
            import re

            confirmed = (
                bool(re.search(r"闰[正冬腊一二三四五六七八九十]+月", text))
                if args.leap_month
                else bool(re.search(r"普通月|非闰|不是闰|不闰|regular", text))
            )
            if not confirmed:
                return "闰月开关须由用户确认，不能猜测"
        return None

    def compute(self, args, session):
        try:
            inputs = birth_values(args, session)
            inputs.pop("lat")
            fields = (
                "gender",
                "true_solar_time",
                "zishi_rule",
                "calendar",
                "lunar_date",
                "calendar_confirmed",
                "leap_month",
                "accept_uncertain",
                "dayun_time_basis",
            )
            inputs.update({k: getattr(args, k) for k in fields})
            for setting in ("true_solar_time", "zishi_rule"):
                if setting not in args.model_fields_set and setting in session.profile:
                    inputs[setting] = session.profile[setting]
            if not inputs["gender"]:
                inputs["gender"] = session.profile.get("gender")
            result, cached = self.store.cached_calculation(
                "bazi", session.user_id, inputs, lambda: compute_bazi(**inputs)
            )
        except NeedsInput as exc:
            return exc.result()
        session.state["bazi_id"] = result["bazi_id"]
        atoms = []
        atoms.append(
            (f"day_master:{result['day_master']}", "convention", "day_master", "long_term", None)
        )
        atoms.append(
            (
                f"zishi:{result['input']['zishi_rule']}",
                "convention",
                f"zishi_{result['input']['zishi_rule']}",
                "long_term",
                None,
            )
        )
        if result["dayun"]:
            atoms.append(
                (
                    f"dayun:{result['dayun']['start_solar']}:{result['dayun']['sequence'][0]['ganzhi']}",
                    "convention",
                    "dayun",
                    "long_term",
                    None,
                )
            )
        if result.get("alternatives"):
            atoms.append(
                ("unknown_time_candidates", "convention", "unknown_time", "long_term", None)
            )
            for i, candidate in enumerate(result["alternatives"]):
                for pillar, gz in candidate.items():
                    atoms.append((f"candidate{i}:{pillar}:{gz}", "stem", gz[0], "long_term", None))
        for pillar, gz in result["pillars"].items():
            if gz:
                atoms.extend(
                    [
                        (f"{pillar}:{gz}:gan", "stem", gz[0], "long_term", None),
                        (f"{pillar}:{gz}:zhi", "branch", gz[1], "long_term", None),
                    ]
                )
                if pillar != "day":
                    god = result["ten_gods_stems"][pillar]
                    atoms.append(
                        (f"{pillar}:{gz}:{god}", "god_pillar", f"{god}:{pillar}", "long_term", None)
                    )
        result = self.attach(result, atoms, session, "bazi_result")
        result["cache_reused"] = cached
        return result

    def period(self, args, session):
        chart = self.store.get_calculation("bazi", session.user_id, args.bazi_id)
        if not chart:
            return ToolResult.failure("ownership_denied", "bazi_id不属于当前用户")
        try:
            result = bazi_period(chart, args.start, args.end, args.granularity, args.tz)
        except NeedsInput as exc:
            return exc.result()
        atoms = []
        for p in result["periods"]:
            for pillar, gz in p["pillars"].items():
                god = p["ten_gods"][pillar]
                atoms.append(
                    (
                        f"period:{p['start_utc']}:{pillar}:{gz}:{god}",
                        "ten_god",
                        god,
                        "short_term",
                        f"{p['start_utc']}/{p['end_utc']}",
                    )
                )
                for relation in p["relations"][pillar]:
                    kind = relation["type"]
                    atoms.append(
                        (
                            f"period:{p['start_utc']}:{pillar}:{gz}:{kind}:{relation.get('natal_pillar', relation.get('branches'))}",
                            "relation",
                            kind,
                            "short_term",
                            f"{p['start_utc']}/{p['end_utc']}",
                        )
                    )
        session.state["timeframe"] = (args.start, args.end)
        return self.attach(result, atoms, session, "bazi_period_result")
