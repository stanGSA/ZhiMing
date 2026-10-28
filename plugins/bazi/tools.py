from pathlib import Path
from typing import Literal

from pydantic import Field

from common.input_evidence import gender_evidence, normalized_gender, solar_time_choice
from common.time_utils import NeedsInput, date_range
from harness.models import StrictInput, ToolResult
from harness.registry import Tool
from plugins.base import meaning_view
from plugins.bazi.calculator import bazi_period, compute_bazi, period_max_days, ten_god
from plugins.bazi.intent import dayun_overview_state
from plugins.bazi.validation import validate_output
from plugins.context import (
    BirthInput,
    MeaningPlugin,
    birth_provenance,
    birth_values,
    period_timezone,
    range_provenance,
)


class BaziInput(BirthInput):
    birth_local: str | None = Field(
        default=None,
        description="用户提供的原始出生地当地钟表日期时间，或省略复用画像。不得先换算成北京时间、UTC或真太阳时再传入；内部计算器负责转换。",
    )
    tz: str | None = Field(
        default=None,
        description="原始出生钟表的IANA时区，通常由location_id取得；不是八字内部固定UTC+8口径，也不是咨询时区。",
    )
    dayun_time_basis: Literal["civil", "physical"] = "civil"
    gender: Literal["male", "female"] | None = None
    true_solar_time: bool = Field(
        default=False,
        description="默认false（固定UTC+8）；只有用户明确确认真太阳时才传true。海外出生须先确认口径。由排盘代码记录实际采用值，不要调用update_profile写入。",
    )
    zishi_rule: Literal["next_day", "same_day"] = Field(
        default="next_day",
        description="默认next_day（子初23点换日）；仅用户明确要求子正换日才传same_day。成功排盘后由代码记录，不要调用update_profile写入。",
    )
    calendar: Literal["solar", "lunar"] = Field(
        default="solar",
        description="默认公历；仅用户明确说农历时改为lunar并设置calendar_confirmed=true。成功计算后由代码保存实际采用口径。",
    )
    lunar_date: str | None = None
    calendar_confirmed: bool = False
    leap_month: bool | None = None
    accept_uncertain: bool = False


class PeriodInput(StrictInput):
    bazi_id: str
    start: str = Field(description="起始日期，须早于结束边界；公历日期含首尾。")
    end: str = Field(description="结束日期。year粒度最多3660天；month/day最多366天。")
    granularity: Literal["year", "month", "day"] = Field(
        default="month", description="year最多3660天，month/day最多366天。"
    )
    tz: str | None = None
    scope: Literal["primary", "dayun_first", "dayun_current"] = Field(
        default="primary",
        description="通常用primary并与咨询区间一致；仅大运说明的首运/当前大运历史比较可分别用dayun_first/dayun_current，不改变咨询主区间。",
    )


class BaziPlugin(MeaningPlugin):
    validate_output = staticmethod(validate_output)

    name = kb_partition = "bazi"
    eval_dir = Path(__file__).parent / "evals"

    def __init__(self, kb, store):
        self.kb, self.store = kb, store
        self.tools = [
            Tool(
                "compute_bazi",
                "排八字三/四柱、十神五行藏干纳音大运。起运/首运/当前大运说明直接用dayun和已附释义，不必补算流年流月或猜查询key。缺时辰仅三柱、缺性别不排大运；农历须确认及闰月明确。needs_input须ask_user。",
                BaziInput,
                self.compute,
                partition="bazi",
                roles=frozenset({"orchestrator", "bazi"}),
                dependency="active_reading_id",
                validator=self.validate,
                cache_user_input=True,
                model_result=self.project,
            ),
            Tool(
                "compute_bazi_period",
                "已有本次bazi_id算流年/节气流月/流日与原局冲合。指定日期运势/行动时机须调用；仅说明起运及大运用compute_bazi已有结果即可。year最多3660天，month/day最多366天；不要为修复文字重算。",
                PeriodInput,
                self.period,
                partition="bazi",
                roles=frozenset({"orchestrator", "bazi"}),
                dependency="bazi_id",
                dependency_argument="bazi_id",
                validator=self.validate_period,
                cache_user_input=True,
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
                meaning=meaning_view(i["meaning"]),
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
                    meaning=meaning_view(i["meaning"]),
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
            and args.gender != normalized_gender(session.profile.get("gender"))
            and args.gender not in gender_evidence(text)
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
                inputs["gender"] = normalized_gender(session.profile.get("gender"))
            choice = session.profile.get("true_solar_time")
            for message in session.user_messages[session.state.get("question_message_index", 0) :]:
                current = solar_time_choice(message)
                if current is not None:
                    choice = current
            overseas = inputs["tz"] not in ("Asia/Shanghai", "Asia/Urumqi", "Etc/GMT-8")
            if overseas and choice is None:
                raise NeedsInput(
                    "confirm_bazi_clock",
                    "海外出生请确认日时柱按真太阳时，还是固定UTC+8口径（不用真太阳时）；两者可能不同。",
                )
            if choice is not None:
                if "true_solar_time" in args.model_fields_set and args.true_solar_time != choice:
                    return ToolResult.failure(
                        "validation_failed", "真太阳时参数与用户确认的口径不一致"
                    )
                inputs["true_solar_time"] = choice
            elif args.true_solar_time:
                raise NeedsInput("confirm_bazi_clock", "请确认是否使用真太阳时，不能自行开启。")
            result, cached = self.store.cached_calculation(
                "bazi", session.user_id, inputs, lambda: compute_bazi(**inputs)
            )
            # Freeze the conventions this calculation actually used (zishi_rule may have come
            # from the profile, not the arguments). The solar-time choice is kept only when
            # the user made one: an unconfirmed default must never later stand in for the
            # confirmation an overseas birth requires.
            derived = {"calendar_input": args.calendar, "zishi_rule": inputs["zishi_rule"]}
            if choice is not None:
                derived["true_solar_time"] = inputs["true_solar_time"]
            for field, value in derived.items():
                if session.profile.get(field) != value:
                    self.store.update_derived_profile(session.user_id, field, value)
                    # Only this field changes in memory, so a specialist keeps its restricted
                    # view; the orchestrator adopts the value when the report is committed.
                    session.profile = {**session.profile, field: value}
                    session.state.setdefault("derived_profile", {})[field] = value
        except NeedsInput as exc:
            return exc.result()
        session.state["bazi_id"] = result["bazi_id"]
        # Enrich cached and new charts alike; the persistent birth calculation is timeless.
        result = dict(result)
        if result.get("dayun"):
            sequence = []
            for stage in result["dayun"]["sequence"]:
                stage = dict(stage)
                stage["next_start_year"] = stage["start_year"] + 10
                stage["stem_ten_god"] = ten_god(result["day_master"][0], stage["ganzhi"][0])
                sequence.append(stage)
            result["dayun"] = {**result["dayun"], "sequence": sequence}
            if session.calendar_anchor:
                year = int(session.calendar_anchor[:4])
                candidates = [
                    i
                    for i, s in enumerate(sequence)
                    if s["start_year"] <= year < s["next_start_year"]
                ]
                # The library exposes year labels, not exact dates for each later handoff.
                if candidates and candidates[0] and sequence[candidates[0]]["start_year"] == year:
                    candidates.insert(0, candidates[0] - 1)
                result["dayun"]["as_of"] = session.calendar_anchor
                result["dayun"]["current_candidates"] = [sequence[i] for i in candidates]
                if len(candidates) == 1:
                    result["dayun"]["next_transition_year"] = sequence[candidates[0]][
                        "next_start_year"
                    ]
            result["dayun"]["note"] = (
                "start_age为传统岁数标记，不等于周岁；start_year/next_start_year为前后交运年份标记，不是精确起止日。"
                "交运年可能有前后两运，未给后续精确交运日时不得断言年初已交运。"
                "下一交运年以next_transition_year为准，不要提前一年说成已经交运或交运带。"
                "起运与首运/当前大运的事实及释义已附在interpretations，无需逐个猜key查询。"
            )
        result = self.attach(
            result,
            chart_atoms(result, include_dayun_stages=dayun_overview_state(session.state)),
            session,
            "bazi_result",
        )
        result["cache_reused"] = cached
        return result

    @staticmethod
    def validate_period(args, session):
        tz = (
            args.tz
            or session.profile.get("consultation_tz")
            or session.state.get("timeframe_tz")
            or "Asia/Shanghai"
        )
        try:
            actual = date_range(args.start, args.end, tz, period_max_days(args.granularity))
        except NeedsInput as exc:
            return exc.question + "请修正本次工具参数；不要拼接不同区间的端点。"
        if args.scope == "primary":
            return range_provenance(args, session)
        state = session.state
        if not dayun_overview_state(state) or state.get("timeframe_required"):
            return "大运比较范围仅用于起运/首运/当前大运说明，指定日期的时机问题必须使用primary。"
        dayun = (state.get("bazi_result") or {}).get("dayun") or {}
        stages = (
            dayun.get("sequence", [])[:1]
            if args.scope == "dayun_first"
            else dayun.get("current_candidates", [])
        )
        if not any(
            date_range(f"{s['start_year']}-01-01", f"{s['start_year'] + 9}-12-31", tz, 3660)[0]
            <= actual[0]
            and actual[1]
            <= date_range(f"{s['start_year']}-01-01", f"{s['start_year'] + 9}-12-31", tz, 3660)[1]
            for s in stages
        ):
            return "比较区间必须位于已计算的对应大运年份内；首运用dayun_first，当前大运用dayun_current。"
        return None

    def period(self, args, session):
        chart = self.store.get_calculation("bazi", session.user_id, args.bazi_id)
        if not chart:
            return ToolResult.failure("ownership_denied", "bazi_id不属于当前用户")
        try:
            result = bazi_period(
                chart, args.start, args.end, args.granularity, period_timezone(args, session, chart)
            )
        except NeedsInput as exc:
            if exc.code in (
                "invalid_range",
                "invalid_granularity",
                "invalid_datetime",
                "offset_timezone_mismatch",
            ):
                return ToolResult.failure("invalid_arguments", exc.question)
            return exc.result()
        if args.scope != "primary":
            result["scope"] = args.scope
            session.state.setdefault("bazi_comparison_results", {})[args.scope] = result
            atoms = [
                (f"comparison:{args.scope}:{fact}", kind, key, "trait", timeframe)
                for fact, kind, key, _, timeframe in period_atoms(result)
            ]
            return self.attach(result, atoms, session, f"bazi_period_{args.scope}")
        session.state["timeframe"] = (args.start, args.end)
        session.state["timeframe_tz"] = result["tz"]
        return self.attach(result, period_atoms(result), session, "bazi_period_result")


# Calculated facts that get a knowledge entry: (fact, kind, key, horizon, timeframe).
def chart_atoms(result, *, include_dayun_stages=False):
    atoms = []
    atoms.append((f"day_master:{result['day_master']}", "convention", "day_master", "trait", None))
    atoms.append(
        (
            f"zishi:{result['input']['zishi_rule']}",
            "convention",
            f"zishi_{result['input']['zishi_rule']}",
            "trait",
            None,
        )
    )
    if result["dayun"]:
        atoms.append(
            (
                f"dayun:{result['dayun']['start_solar']}:{result['dayun']['sequence'][0]['ganzhi']}",
                "convention",
                "dayun",
                "trait",
                None,
            )
        )
        for index, stage in enumerate(result["dayun"]["sequence"]):
            if not include_dayun_stages:
                break
            gz = stage["ganzhi"]
            if index != 0 and stage not in result["dayun"].get("current_candidates", []):
                continue
            atoms.append(
                (
                    f"dayun_stage:{index + 1}:{gz}:{stage['start_year']}至{stage['start_year'] + 10}交运年份标记",
                    "convention",
                    "dayun",
                    "trait",
                    None,
                )
            )
            atoms.append(
                (
                    f"dayun_stem:{index + 1}:{gz}:{ten_god(result['day_master'][0], gz[0])}",
                    "ten_god",
                    ten_god(result["day_master"][0], gz[0]),
                    "trait",
                    None,
                )
            )
    if result.get("alternatives"):
        atoms.append(("unknown_time_candidates", "convention", "unknown_time", "trait", None))
        for i, candidate in enumerate(result["alternatives"]):
            for pillar, gz in candidate.items():
                atoms.append((f"candidate{i}:{pillar}:{gz}", "stem", gz[0], "trait", None))
    for pillar, gz in result["pillars"].items():
        if gz:
            atoms.extend(
                [
                    (f"{pillar}:{gz}:gan", "stem", gz[0], "trait", None),
                    (f"{pillar}:{gz}:zhi", "branch", gz[1], "trait", None),
                ]
            )
            if pillar != "day":
                god = result["ten_gods_stems"][pillar]
                atoms.append(
                    (f"{pillar}:{gz}:{god}", "god_pillar", f"{god}:{pillar}", "trait", None)
                )
    return atoms


def period_atoms(result):
    atoms = []
    for p in result["periods"]:
        for pillar, gz in p["pillars"].items():
            god = p["ten_gods"][pillar]
            atoms.append(
                (
                    f"period:{p['start_utc']}:{pillar}:{gz}:{god}",
                    "ten_god",
                    god,
                    "timing",
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
                        "timing",
                        f"{p['start_utc']}/{p['end_utc']}",
                    )
                )
    return atoms
