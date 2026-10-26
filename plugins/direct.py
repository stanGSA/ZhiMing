"""Session-free entry to the deterministic plugins, for callers that state their own inputs.

The runtime tools read birth data from a conversation, and the Guard's provenance checks hold
every value to what the user actually said, so that a model cannot invent a birth date. A
direct caller (the MCP server, like the web page's chart panel) passes structured inputs itself
and there is no utterance to check them against. This module therefore never builds a Session,
never runs the runtime tool handlers and never touches the Guard, whose behaviour stays exactly
as it is. It shares the calculators and the knowledge-entry assembly with the runtime tools, so
the facts and meanings are the same.

Results are deterministic: identifiers are hashes of the inputs, and a tarot draw or a daily
card repeats when its seed or key is passed again.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from common.location import Gazetteer, LocationInput
from common.output_policy import REVIEW_CAP, REVIEW_NOTE
from common.time_utils import NeedsInput
from knowledge.kb import KnowledgeBase
from knowledge.review import LEVELS, lowest
from plugins.astro.calculator import natal_chart, transits
from plugins.astro.tools import AstroPlugin, natal_atoms, transit_atoms
from plugins.bazi.calculator import bazi_period, compute_bazi
from plugins.bazi.tools import BaziPlugin, chart_atoms, period_atoms
from plugins.daily.tools import DailyPlugin
from plugins.dream.tools import DreamPlugin
from plugins.name.strokes import UnihanMissing
from plugins.name.tools import HAN, NamePlugin, name_atoms
from plugins.name.validation import ambiguity_prompt
from plugins.name.wuge import analyze
from plugins.tarot.draw import draw_tarot
from plugins.tarot.tools import TarotPlugin

ALGORITHM = "direct-v1"
# Birth clocks on fixed UTC+8 need no solar-time decision; elsewhere the two can differ.
DOMESTIC_CLOCKS = ("Asia/Shanghai", "Asia/Urumqi", "Etc/GMT-8")


class DirectError(ValueError):
    """A request the calculators cannot serve; callers report it as a structured error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Birth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    birth_local: str | None = Field(
        default=None,
        description="出生地当地钟表时间，YYYY-MM-DD HH:MM；时辰未知时只写日期并设 time_known=false。"
        "八字按农历输入时可省略，改填 lunar_date。",
    )
    time_known: bool = True
    location_id: str | None = Field(
        default=None, description="resolve_location 返回的地点编号；与 tz/lat/lon 二选一"
    )
    clock_tz: Literal["Asia/Shanghai", "Asia/Urumqi"] | None = Field(
        default=None, description="仅新疆出生地：出生钟表用北京时间还是新疆时间"
    )
    tz: str | None = Field(default=None, description="不用 location_id 时：出生钟表的 IANA 时区")
    lat: float | None = Field(
        default=None, gt=-90, lt=90, description="不用 location_id 时：纬度，星盘需要，八字不用"
    )
    lon: float | None = Field(
        default=None, ge=-180, le=180, description="不用 location_id 时：经度"
    )
    fold: Literal[0, 1] | None = Field(
        default=None, description="夏令时回拨造成重复时刻时：0 为回拨前，1 为回拨后"
    )

    @model_validator(mode="after")
    def one_place(self):
        if self.location_id:
            if any(value is not None for value in (self.tz, self.lat, self.lon)):
                raise ValueError("location_id 与 tz/lat/lon 只能二选一")
        elif self.tz is None or self.lon is None:
            raise ValueError(
                "请提供 resolve_location 返回的 location_id，或直接提供 tz 与 lon（星盘另需 lat）"
            )
        if self.clock_tz and not self.location_id:
            raise ValueError("clock_tz 只配合新疆出生地的 location_id 使用；直接给出时区请填 tz")
        return self


def birth_inputs(birth_local, time_known, location, clock_tz=None) -> dict:
    """Calculator inputs from a resolved place, shared with the web page's chart panel.

    A Xinjiang birth clock may be Beijing or Xinjiang time; only the person can say which.
    """
    if clock_tz and location["tz"] != "Asia/Urumqi":
        raise ValueError("此地点无需指定新疆钟表时间制")
    if location["tz"] == "Asia/Urumqi" and not clock_tz:
        raise NeedsInput("confirm_clock_timezone", "请确认出生钟表使用北京时间还是新疆时间。")
    return dict(
        birth_local=birth_local,
        time_known=time_known,
        tz=clock_tz or location["tz"],
        lat=location["lat"],
        lon=location["lon"],
    )


def identity(prefix: str, *parts) -> str:
    payload = json.dumps([ALGORITHM, *parts], sort_keys=True, ensure_ascii=False)
    return prefix + hashlib.sha256(payload.encode()).hexdigest()[:12]


def review_summary(levels: list[str]) -> dict | None:
    """The least reviewed meaning sets the confidence cap, as in the runtime's answers."""
    if not levels:
        return None
    level = lowest(levels)
    return dict(
        lowest=level,
        counts={name: levels.count(name) for name in LEVELS if name in levels},
        confidence_cap=REVIEW_CAP[level],
        note=REVIEW_NOTE.get(level, "释义经人工审核"),
    )


class Calculator:
    def __init__(self, kb: KnowledgeBase, gazetteer: Gazetteer | None = None):
        self.kb = kb
        self.gazetteer = gazetteer or Gazetteer()
        # Plugins are used for their knowledge lookups only; none gets a store or a session.
        self.astro = AstroPlugin(kb, None)
        self.bazi = BaziPlugin(kb, None)
        self.names = NamePlugin(kb, None)
        self.dreams = DreamPlugin(kb)
        self.daily = DailyPlugin(kb, None)
        self.tarot = TarotPlugin(kb)

    def finish(self, result: dict, meanings: list[dict]) -> dict:
        result["kb_version"] = self.kb.version
        result["review"] = review_summary([m["review_status"] for m in meanings])
        return {"status": "ok", **result}

    def interpreted(self, result: dict) -> dict:
        return self.finish(result, [i["meaning"] for i in result["interpretations"]])

    def resolve_location(self, query, country=None, admin1=None, candidate_id=None) -> dict:
        return self.gazetteer.resolve(
            LocationInput(query=query, country=country, admin1=admin1, candidate_id=candidate_id)
        )

    def place(self, birth: Birth) -> dict:
        if birth.location_id is None:
            inputs = dict(
                birth_local=birth.birth_local,
                time_known=birth.time_known,
                tz=birth.tz,
                lat=birth.lat,
                lon=birth.lon,
            )
        else:
            self.gazetteer.load()
            location = self.gazetteer.records.get(birth.location_id)
            if location is None:
                raise DirectError(
                    "unknown_location", "location_id 不存在，请先用 resolve_location 解析出生地"
                )
            inputs = birth_inputs(birth.birth_local, birth.time_known, location, birth.clock_tz)
        return {**inputs, "fold": birth.fold}

    def chart(self, birth: Birth) -> dict:
        inputs = self.place(birth)
        if not inputs["birth_local"]:
            raise NeedsInput("missing_birth_date", "请提供出生日期与出生时间（不知道请说明）。")
        if inputs["lat"] is None:
            raise NeedsInput(
                "missing_latitude", "星盘需要出生地纬度，请提供 lat 或改用 location_id。"
            )
        result = natal_chart(**inputs)
        result["chart_id"] = identity("ch", inputs)
        return result

    def natal_chart(self, birth: Birth) -> dict:
        result = self.chart(birth)
        result["interpretations"] = self.astro.interpret(result, natal_atoms(result))
        return self.interpreted(result)

    def transits(self, birth: Birth, start, end, tz, orb=1.0, bodies=None) -> dict:
        result = transits(self.chart(birth), start, end, tz, orb, bodies)
        result["interpretations"] = self.astro.interpret(result, transit_atoms(result, start, end))
        return self.interpreted(result)

    def bazi_inputs(self, birth: Birth, options: dict) -> dict:
        inputs = self.place(birth)
        inputs.pop("lat")
        solar = options.pop("true_solar_time", None)
        if solar is None:
            if inputs["tz"] not in DOMESTIC_CLOCKS:
                raise NeedsInput(
                    "confirm_bazi_clock",
                    "海外出生请确认日时柱按真太阳时，还是固定UTC+8口径（不用真太阳时）；两者可能不同。",
                )
            solar = False
        calendar = options.get("calendar", "solar")
        return {
            **inputs,
            **options,
            "true_solar_time": solar,
            # A direct caller states the calendar itself; nothing is left to confirm.
            "calendar_confirmed": calendar == "lunar",
        }

    def bazi_chart(self, birth: Birth, **options) -> dict:
        inputs = self.bazi_inputs(birth, options)
        result = compute_bazi(**inputs)
        result["bazi_id"] = identity("bz", inputs)
        return result

    def compute_bazi(self, birth: Birth, **options) -> dict:
        result = self.bazi_chart(birth, **options)
        result["interpretations"] = self.bazi.interpret(result, chart_atoms(result))
        return self.interpreted(result)

    def bazi_period(self, birth: Birth, start, end, granularity, tz, **options) -> dict:
        result = bazi_period(self.bazi_chart(birth, **options), start, end, granularity, tz)
        result["interpretations"] = self.bazi.interpret(result, period_atoms(result))
        return self.interpreted(result)

    def draw_tarot(self, spread, question, seed=None, picks=None) -> dict:
        # Without a seed the draw is new each time; the seed returned repeats it exactly. It
        # stays below 2**53 so that JSON clients that read numbers as doubles return it intact.
        seed = secrets.randbelow(2**53) if seed is None else seed
        result = draw_tarot(spread, question, seed, picks)
        result["reading_id"] = identity("td", spread, question, seed, picks)
        self.tarot.annotate(result)
        result["draw_id"] = result.pop("reading_id")
        return self.finish(result, [card["meaning"] for card in result["cards"]])

    def analyze_name(self, surname, given, forms=None) -> dict:
        forms = forms or {}
        full = surname + given
        if not re.fullmatch(f"{HAN}+", full):
            raise DirectError("invalid_arguments", "姓名只能包含汉字")
        for char, form in forms.items():
            if char not in full or not re.fullmatch(HAN, form):
                raise DirectError("invalid_arguments", "写法确认只能针对本名中的字，且为单个汉字")
        try:
            result = analyze(surname, given, forms)
        except UnihanMissing as exc:
            raise DirectError("data_missing", str(exc)) from exc
        if result["status"] != "ok":
            chars = "、".join(f"“{c}”" for c in result["unknown"])
            raise NeedsInput(
                "unknown_name_char",
                f"无法确定{chars}的康熙笔画，请确认这个字的写法（可提供繁体或常用异体）；不会猜测笔画。",
                result["unknown"],
            )
        result["confirmation_prompts"] = [
            ambiguity_prompt(result, item) for item in result["ambiguities"]
        ]
        result["interpretations"] = self.names.interpret(result, name_atoms(result))
        return self.interpreted(result)

    def dream_symbols(self, symbols: list[str]) -> dict:
        # The caller names the symbols; each one stands in for its own source phrase.
        return self.interpreted(self.dreams.match_symbols([(s, s) for s in symbols]))

    def daily_fortune(
        self,
        birth: Birth,
        date,
        tz,
        true_solar_time=None,
        zishi_rule="next_day",
        user_key=None,
    ) -> dict:
        chart = self.chart(birth)
        bazi = self.bazi_chart(
            birth, gender=None, true_solar_time=true_solar_time, zishi_rule=zishi_rule
        )
        if not bazi["day_master"]:
            raise NeedsInput("uncertain_day_master", "日柱无法确定，请补充出生时间。")
        # The runtime seeds the daily card with its user id; here the caller's key, or else
        # the birth data, so the same person on the same day draws the same card.
        key = user_key or identity("bk", chart["chart_id"])
        result = self.daily.compute(key, date, tz, chart, bazi)
        result.pop("signals")  # Cross-system merge input; the interpretations carry the facts.
        result["user_key"] = key
        return self.interpreted(result)

    def lookup_meaning(self, system, kind, key) -> dict:
        entry = self.kb.lookup(system, kind, key)
        if entry is None:
            raise DirectError("missing_entry", "缺条目：精确 key 或同义词未命中")
        entry = {k: v for k, v in entry.items() if k != "model_review"}
        return self.finish(dict(entry=entry), [entry])
