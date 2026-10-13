"""Daily fortune: a deterministic composition of astro, bazi and tarot (no LLM, no specialist).

One call returns, for one user and one local date: exact aspects of the Moon and fast planets
to the natal chart, the day pillar and its ten-god relation to the day master, and a daily
card drawn with seed = SHA256(user_id, date). The result is cached in app.db `daily`
(user_id, date); asking again on the same day reads the cache, so the answer cannot change.
"""

import hashlib
import json
import re
from datetime import date as Date
from datetime import timedelta
from pathlib import Path

from pydantic import Field

from common.time_utils import NeedsInput
from harness.models import StrictInput
from harness.registry import Tool
from plugins.astro.calculator import BODY_ZH, natal_chart, transits
from plugins.base import Signal
from plugins.bazi.calculator import GAN, GAN_WX, WX, bazi_period, compute_bazi
from plugins.context import BirthInput, birth_values, period_timezone
from plugins.tarot.draw import draw_tarot

SEED_ALGORITHM = "daily-sha256-v1"


class DailyInput(StrictInput):
    date: str = Field(description="咨询的当地日期YYYY-MM-DD：今天用日历基准日期，明天加一天")
    location_id: str | None = Field(
        default=None, description="出生地已由resolve_location解析时填写"
    )
    tz: str | None = Field(default=None, description="咨询日期的IANA时区；通常省略")


def daily_seed(user_id: str, day: str) -> int:
    payload = json.dumps([SEED_ALGORITHM, user_id, day], separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big")


def requested_date(session) -> str | None:
    """The date the user asked about: an explicit date, or today/tomorrow from the anchor."""
    text = session.user_messages[-1] if session.user_messages else ""
    anchor = Date.fromisoformat(session.calendar_anchor) if session.calendar_anchor else None
    explicit = re.search(r"(\d{4})[-年/.](\d{1,2})[-月/.](\d{1,2})", text)
    if explicit:
        return Date(*map(int, explicit.groups())).isoformat()
    if anchor is None:
        return None
    short = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})[日号]", text)
    if short:
        return Date(anchor.year, int(short[1]), int(short[2])).isoformat()
    for word, offset in (("后天", 2), ("明天", 1), ("明日", 1), ("昨天", -1)):
        if word in text:
            return (anchor + timedelta(days=offset)).isoformat()
    return anchor.isoformat()


class DailyPlugin:
    name = kb_partition = "daily"
    required_profile = set()
    themes = {"self", "career", "relationship", "finance"}
    eval_dir = Path(__file__).parent / "evals"

    def __init__(self, kb, store):
        self.kb, self.store = kb, store
        self.tools = [
            Tool(
                "daily_fortune",
                "今日/明日运势一次调用：月亮与快行星对本命的精确相位、流日干支与日主十神、每日一牌（种子固定）。"
                "同一用户同一天结果不变；一周或更长区间不要用本工具。缺出生资料返回needs_input。",
                DailyInput,
                self.daily,
                partition="daily",
                roles=frozenset({"orchestrator"}),
                dependency="active_reading_id",
                validator=self.validate,
                cache_user_input=True,
                model_result=self.project,
            )
        ]

    @staticmethod
    def validate(args, session):
        try:
            Date.fromisoformat(args.date)
        except ValueError:
            return "date须为YYYY-MM-DD"
        wanted = requested_date(session)
        if wanted and args.date != wanted:
            return f"日期须与用户所问一致：{wanted}"
        if (
            args.tz
            and args.tz not in " ".join(session.user_messages)
            and args.tz
            not in (
                session.profile.get("consultation_tz"),
                session.profile.get("tz"),
            )
        ):
            return "咨询时区须来自用户原话或画像"
        return None

    @staticmethod
    def project(data):
        if data.get("status") == "needs_input":
            return data
        result = {k: v for k, v in data.items() if k not in ("natal", "bazi", "inputs")}
        result["natal_summary"] = [
            f"{p['body_zh']}{p['sign_zh']}" for p in data["natal"]["planets"]
        ]
        result["day_master"] = data["bazi"]["day_master"]
        result["events"] = [
            {
                k: e[k]
                for k in ("transit_body", "natal_body", "aspect", "exact_utc", "exact_date")
                + ("natal_sign", "natal_house", "time_uncertain")
            }
            for e in data["events"]
        ]
        result["interpretations"] = [
            dict(
                ref_id=i["ref_id"],
                fact=i["fact"],
                meaning=dict(text=i["meaning"]["text"], reviewed=i["meaning"]["reviewed"]),
            )
            for i in data["interpretations"]
        ]
        return result

    def inputs(self, args, session):
        missing = NeedsInput(
            "missing_birth_information",
            "每日运势需要出生日期、出生时间（不知道请说明）和出生地点，请补充。",
        )
        if not session.profile.get("birth_local_dt"):
            raise missing
        birth = birth_values(BirthInput(location_id=args.location_id), session)
        if birth["lat"] is None:
            raise missing
        tz = birth["tz"]
        overseas = tz not in ("Asia/Shanghai", "Asia/Urumqi", "Etc/GMT-8")
        solar = session.profile.get("true_solar_time")
        if overseas and solar is None:
            raise NeedsInput(
                "confirm_bazi_clock",
                "海外出生请确认流日日主按真太阳时，还是固定UTC+8口径（不用真太阳时）。",
            )
        bazi = dict(
            birth_local=birth["birth_local"],
            tz=tz,
            lon=birth["lon"],
            gender=None,  # The day relation needs only the day master; no luck pillars.
            time_known=birth["time_known"],
            true_solar_time=bool(solar),
            zishi_rule=session.profile.get("zishi_rule", "next_day"),
            fold=birth["fold"],
        )
        return birth, bazi

    def daily(self, args, session):
        try:
            birth, bazi_inputs = self.inputs(args, session)
            chart, _ = self.store.cached_calculation(
                "astro", session.user_id, birth, lambda: natal_chart(**birth)
            )
            bazi, _ = self.store.cached_calculation(
                "bazi", session.user_id, bazi_inputs, lambda: compute_bazi(**bazi_inputs)
            )
            if not bazi["day_master"]:
                raise NeedsInput("uncertain_day_master", "日柱无法确定，请补充出生时间。")
            tz = period_timezone(args, session, chart)
        except NeedsInput as exc:
            return exc.result()
        fingerprint = hashlib.sha256(
            json.dumps([SEED_ALGORITHM, birth, bazi_inputs, tz], sort_keys=True).encode()
        ).hexdigest()
        cached = self.store.get_daily(session.user_id, args.date)
        if cached and cached["result"]["fingerprint"] == fingerprint:
            result = cached["result"]
            result["cache_reused"] = True
        else:
            try:
                result = self.compute(session.user_id, args.date, tz, chart, bazi)
            except NeedsInput as exc:
                return exc.result()
            result["fingerprint"] = fingerprint
            self.store.save_daily(session.user_id, args.date, result, self.kb.version)
            result["cache_reused"] = False
            if cached is not None:
                result["recomputed_after_profile_change"] = True
        state = session.state
        signals = [Signal.model_validate(s) for s in result["signals"]]
        old = {s["ref_id"] for s in state["signals"]}
        state["signals"].extend(s.model_dump(mode="json") for s in signals if s.ref_id not in old)
        state["allowed_refs"].update(s.ref_id for s in signals)
        state["kb_refs"].update(ref for s in signals for ref in (s.kb_refs or (s.kb_ref,)))
        state["facts"].append(result["card"]["name"])
        # A cached day keeps the knowledge edition it was computed with.
        state["kb_version"] = result["kb_version"]
        state["kb_lookup_version"] = result["kb_version"]
        state["daily_result"] = result
        state.setdefault("calculations", {})["daily_result"] = result
        return {k: v for k, v in result.items() if k != "signals"}

    def compute(self, user_id, day, tz, chart, bazi):
        rule = self.kb.rules(self.name)
        daily_id = "dy" + hashlib.sha256(f"{user_id}:{day}".encode()).hexdigest()[:12]
        moves = transits(chart, day, day, tz, rule["transit_orb"], rule["transit_bodies"])
        period = bazi_period(bazi, day, day, "day", tz)
        noon = f"{day}T12:00:00"
        segments = period["periods"]
        main = next(
            (p for p in segments if p["start_utc"] <= _utc(noon, tz) < p["end_utc"]), segments[0]
        )
        seed = daily_seed(user_id, day)
        card = draw_tarot("single", f"daily:{day}", seed)["cards"][0]
        orientation = "reversed" if card["reversed"] else "upright"
        stem = main["pillars"]["day"][0]
        element = WX[GAN_WX[GAN.index(stem)]]
        items = []

        def add(fact, system, kind, key, strength, components=()):
            entry = self.kb.lookup(system, kind, key)
            if entry is None:
                raise ValueError(f"Missing knowledge entry: {system}/{kind}/{key}")
            parts = [entry] + [self.kb.lookup(s, k, v) for s, k, v in components]
            items.append(
                dict(
                    ref_id=f"daily:{daily_id}:{fact}",
                    fact=fact,
                    system=system,
                    kind=kind,
                    key=key,
                    strength=strength,
                    meaning=dict(
                        text=" ".join(p["text"] for p in parts),
                        keywords=entry["keywords"],
                        theme_map=entry["theme_map"],
                        reviewed=all(p["reviewed"] for p in parts),
                        ref_id=entry["ref_id"],
                        component_refs=[p["ref_id"] for p in parts],
                    ),
                )
            )

        for e in moves["events"]:
            add(
                f"transit:{e['exact_utc']}:{e['transit_body']}:{e['natal_body']}:{e['aspect']}",
                "astro",
                "aspect",
                e["aspect"],
                rule["strength"]["moon_aspect" if e["transit_body"] == "Moon" else "fast_aspect"],
                (("astro", "planet", e["transit_body"]), ("astro", "planet", e["natal_body"])),
            )
        if not moves["events"]:
            add("no_exact_events", "daily", "convention", "no_exact_events", 0.0)
        for p in segments:
            god = p["ten_gods"]["day"]
            add(
                f"day:{p['start_utc']}:{p['pillars']['day']}:{god}",
                "bazi",
                "ten_god",
                god,
                rule["strength"]["day_ten_god"],
            )
            for relation in p["relations"]["day"]:
                add(
                    f"day:{p['start_utc']}:{p['pillars']['day']}:{relation['type']}:"
                    f"{relation.get('natal_pillar', relation.get('branches'))}",
                    "bazi",
                    "relation",
                    relation["type"],
                    rule["strength"]["day_relation"],
                )
        add(
            f"card:{card['card_id']}:{orientation}",
            "tarot",
            "card",
            f"{card['card_id']}:{orientation}",
            rule["strength"]["daily_card"],
        )
        add(f"day_element:{element}", "daily", "day_element", element, 0.0)
        add("daily_seed", "daily", "convention", "daily_seed", 0.0)
        if not chart["time_known"]:
            add("unknown_time", "daily", "convention", "unknown_time", 0.0)
        signals = []
        for item in items:
            themes = [t for t, v in item["meaning"]["theme_map"].items() if v]
            for theme in themes or ["self"]:
                signals.append(
                    Signal(
                        ref_id=item["ref_id"],
                        system=self.name,
                        theme=theme,
                        valence=item["meaning"]["theme_map"].get(theme, 0.0),
                        strength=item["strength"] if themes else 0.0,
                        horizon=rule["horizon"],
                        timeframe=f"{day}/{day}",
                        keywords=tuple(item["meaning"]["keywords"]),
                        kb_ref=item["meaning"]["ref_id"],
                        kb_refs=tuple(item["meaning"]["component_refs"]),
                        rule_version=rule["version"],
                        reviewed=item["meaning"]["reviewed"],
                    ).model_dump(mode="json")
                )
        card_ref = next(i["ref_id"] for i in items if i["fact"].startswith("card:"))
        return dict(
            daily_id=daily_id,
            date=day,
            tz=tz,
            seed=seed,
            seed_algorithm=SEED_ALGORITHM,
            kb_version=self.kb.version,
            natal=dict(
                planets=chart["planets"],
                aspects=chart["aspects"],
                axes=chart["axes"],
                time_known=chart["time_known"],
                chart_id=chart.get("chart_id"),
            ),
            bazi=dict(
                pillars=bazi["pillars"],
                day_master=bazi["day_master"],
                bazi_id=bazi.get("bazi_id"),
                time_known=bazi["time_known"],
            ),
            events=moves["events"],
            day=dict(
                pillar=main["pillars"]["day"],
                ten_god=main["ten_gods"]["day"],
                relations=main["relations"]["day"],
                segments=[
                    dict(
                        start_utc=p["start_utc"],
                        end_utc=p["end_utc"],
                        pillar=p["pillars"]["day"],
                        ten_god=p["ten_gods"]["day"],
                    )
                    for p in segments
                ],
                element=element,
            ),
            card=dict(**card, ref_id=card_ref, meaning_key=f"{card['card_id']}:{orientation}"),
            interpretations=items,
            signals=signals,
            uncertainty=chart["uncertainty"],
            conventions=dict(
                transits="当日（咨询时区）内月亮、太阳、水星、金星、火星对本命行星的精确相位；容许度1度只作解释",
                day_pillar="流日按八字日界（默认23点换日）分段，主流日取当地正午所在段",
                card=f"每日一牌：单张，seed=SHA256({SEED_ALGORITHM}, 用户编号, 日期)前8字节",
                color="幸运色只是流日天干五行的传统配色约定",
            ),
            bodies=[BODY_ZH[b] for b in rule["transit_bodies"]],
        )


def _utc(local, tz):
    from common.time_utils import local_instant

    return local_instant(local, tz).isoformat()
