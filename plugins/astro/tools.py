from pathlib import Path

from pydantic import Field

from common.time_utils import NeedsInput
from harness.models import StrictInput, ToolResult
from harness.registry import Tool
from plugins.astro.calculator import ASPECTS, SIGN_ZH, SIGNS, natal_chart, transits
from plugins.astro.validation import validate_output
from plugins.context import (
    BirthInput,
    MeaningPlugin,
    birth_provenance,
    birth_values,
    period_timezone,
    range_provenance,
)


class TransitInput(StrictInput):
    chart_id: str
    start: str
    end: str
    tz: str | None = None
    orb: float = Field(default=1.0, gt=0, le=8)
    bodies: list[str] | None = None


class AstroPlugin(MeaningPlugin):
    validate_output = staticmethod(validate_output)

    name = kb_partition = "astro"
    eval_dir = Path(__file__).parent / "evals"

    def __init__(self, kb, store):
        self.kb, self.store = kb, store
        self.tools = [
            Tool(
                "compute_natal_chart",
                "计算真实本命盘。出生资料来自用户/画像，地点先解析；未知时间宫位四轴null；需要确认时返回needs_input，请ask_user。",
                BirthInput,
                self.natal,
                partition="astro",
                roles=frozenset({"orchestrator", "astro"}),
                dependency="active_reading_id",
                validator=birth_provenance,
                model_result=self.project,
            ),
            Tool(
                "compute_transits",
                "已有本次chart_id计算指定日期区间的精确行运相位。日期结束日包含；时刻结束为半开。不能用原局代替行运回答时机。",
                TransitInput,
                self.transit,
                partition="astro",
                roles=frozenset({"orchestrator", "astro"}),
                dependency="chart_id",
                dependency_argument="chart_id",
                validator=range_provenance,
                model_result=self.project,
            ),
        ]

    def compound_keys(self, result, kind, key, fact):
        if kind in ("planet_sign", "planet_house"):
            body, value = key.split(":")
            keys = [("planet", body)]
            if kind == "planet_sign":
                keys.append(("sign", value))
                planet = next(p for p in result["planets"] if p["body"] == body)
                if planet["house"] is not None:
                    keys.extend(
                        [
                            ("planet_house", f"{body}:{planet['house']}"),
                            ("house", str(planet["house"])),
                        ]
                    )
            else:
                keys.append(("house", value))
            return keys
        if kind == "aspect":
            if fact.startswith("natal_aspect"):
                _, a, b, _ = fact.split(":")
                return [("planet", a), ("planet", b)]
            for e in result.get("events", []):
                if (
                    fact
                    == f"transit:{e['exact_utc']}:{e['transit_body']}:{e['natal_body']}:{e['aspect']}"
                ):
                    keys = [
                        ("planet", e["transit_body"]),
                        ("planet", e["natal_body"]),
                        ("sign", SIGNS[SIGN_ZH.index(e["natal_sign"])]),
                    ]
                    if e["natal_house"] is not None:
                        keys.append(("house", str(e["natal_house"])))
                    return keys
        return []

    def signal_strength(self, result, item, rule):
        if item["kind"] != "aspect":
            return super().signal_strength(result, item, rule)
        fact = item["fact"]
        if fact.startswith("natal_aspect"):
            index = int(fact.split(":")[0].removeprefix("natal_aspect"))
            aspect = result["aspects"][index]
            planets = {p["body"]: p for p in result["planets"]}
            speed = min(abs(planets[b]["speed_deg_per_day"]) for b in (aspect["a"], aspect["b"]))
            orb, limit = aspect["orb"], ASPECTS[aspect["type"]][1]
        else:
            event = next(
                e
                for e in result["events"]
                if fact
                == f"transit:{e['exact_utc']}:{e['transit_body']}:{e['natal_body']}:{e['aspect']}"
            )
            speed = abs(event["speed_deg_per_day"])
            orb, limit = event["orb_deg"], event["allowed_orb_deg"]
        formula = rule["aspect_strength"]
        tightness = max(0.0, 1 - orb / limit)
        slowness = 1 / (1 + speed)
        return min(
            1.0,
            formula["floor"]
            + formula["orb_weight"] * tightness
            + formula["speed_weight"] * slowness,
        )

    @staticmethod
    def project(data):
        if data.get("status") == "needs_input":
            return data
        result = {k: v for k, v in data.items() if k not in ("jd_tt", "jd_ut1", "input", "cusps")}
        # Interpretations are projected; the complete atomic table remains in trace/DB.
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
            if i["kind"] in ("planet_sign", "aspect")
        ]
        if "events" in result:
            # Slow-planet crossings first;
            # keep the full calculation in local trace/database and disclose truncation.
            events = result["events"]
            priority = {
                b: i
                for i, b in enumerate(
                    (
                        "Saturn",
                        "Jupiter",
                        "Mars",
                        "Uranus",
                        "Neptune",
                        "Pluto",
                        "Sun",
                        "Mercury",
                        "Venus",
                        "Moon",
                    )
                )
            }
            selected = sorted(events, key=lambda e: (priority[e["transit_body"]], e["exact_utc"]))[
                :12
            ]
            selected.sort(key=lambda e: e["exact_utc"])
            result["event_count"] = len(events)
            result["events"] = selected
            result["omitted_from_model_context"] = len(events) - len(selected)
            identifiers = {
                f"transit:{e['exact_utc']}:{e['transit_body']}:{e['natal_body']}:{e['aspect']}"
                for e in selected
            }
            result["interpretations"] = [
                i
                for i in result["interpretations"]
                if i["fact"] in identifiers or "no_exact_events" in i["fact"]
            ]
        return result

    def natal(self, args, session):
        try:
            inputs = birth_values(args, session)
            if inputs["lat"] is None or not inputs["birth_local"]:
                raise NeedsInput("missing_birth_information", "请补充出生日期时间与地点。")
            result, cached = self.store.cached_calculation(
                "astro", session.user_id, inputs, lambda: natal_chart(**inputs)
            )
        except NeedsInput as exc:
            return exc.result()
        session.state["chart_id"] = result["chart_id"]
        atoms = []
        for p in result["planets"]:
            atoms.append(
                (
                    f"{p['body']}:{p['sign']}",
                    "planet_sign",
                    f"{p['body']}:{p['sign']}",
                    "trait",
                    None,
                )
            )
            if p["house"] is not None:
                atoms.append(
                    (
                        f"{p['body']}:house{p['house']}",
                        "planet_house",
                        f"{p['body']}:{p['house']}",
                        "trait",
                        None,
                    )
                )
        for i, a in enumerate(result["aspects"]):
            atoms.append(
                (
                    f"natal_aspect{i}:{a['a']}:{a['b']}:{a['type']}",
                    "aspect",
                    a["type"],
                    "trait",
                    None,
                )
            )
        result = self.attach(result, atoms, session, "natal_result")
        result["cache_reused"] = cached
        return result

    def transit(self, args, session):
        chart = self.store.get_calculation("astro", session.user_id, args.chart_id)
        if not chart:
            return ToolResult.failure("ownership_denied", "chart_id不属于当前用户")
        try:
            result = transits(
                chart,
                args.start,
                args.end,
                period_timezone(args, session, chart),
                args.orb,
                args.bodies,
            )
        except NeedsInput as exc:
            return exc.result()
        atoms = [
            (
                f"transit:{e['exact_utc']}:{e['transit_body']}:{e['natal_body']}:{e['aspect']}",
                "aspect",
                e["aspect"],
                "timing",
                e["exact_date"],
            )
            for e in result["events"]
        ]
        # An empty interval is valid; explicitly include a neutral, grounded range fact.
        if not atoms:
            atoms = [
                (
                    f"transit:{args.start}:{args.end}:no_exact_events",
                    "transit",
                    "no_exact_events",
                    "timing",
                    f"{args.start}/{args.end}",
                )
            ]
        session.state["timeframe"] = (args.start, args.end)
        session.state["timeframe_tz"] = result["tz"]
        return self.attach(result, atoms, session, "transit_result")
