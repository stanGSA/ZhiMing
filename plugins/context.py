"""Shared deterministic plugin binding. No model-created profile or signals."""

import re

from pydantic import Field

from common.time_utils import NeedsInput
from harness.models import StrictInput
from plugins.base import Signal


class BirthInput(StrictInput):
    birth_local: str | None = None
    location_id: str | None = None
    tz: str | None = None
    lat: float | None = Field(default=None, gt=-90, lt=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    time_known: bool = True
    fold: int | None = Field(default=None, ge=0, le=1)


def birth_values(args, session):
    profile = session.profile
    values = dict(
        birth_local=args.birth_local or profile.get("birth_local_dt"),
        tz=args.tz or profile.get("tz"),
        lat=args.lat if args.lat is not None else profile.get("lat"),
        lon=args.lon if args.lon is not None else profile.get("lon"),
        time_known=args.time_known,
        fold=args.fold,
    )
    location = session.state.get("locations", {}).get(args.location_id)
    if args.location_id and location is None:
        raise NeedsInput("unresolved_location", "请先解析出生地并确认候选。")
    if location:
        values.update({k: location[k] for k in ("tz", "lat", "lon")})
        text = " ".join(session.user_messages)
        clock_tz = args.tz or profile.get("tz")
        if location["tz"] == "Asia/Urumqi":
            beijing = "北京时间" in text or "Asia/Shanghai" in text
            xinjiang = "新疆时间" in text or "Asia/Urumqi" in text
            if beijing != xinjiang:
                clock_tz = "Asia/Shanghai" if beijing else "Asia/Urumqi"
            elif not clock_tz or beijing == xinjiang and beijing:
                raise NeedsInput(
                    "confirm_clock_timezone",
                    "请确认出生钟表时间使用北京时间（Asia/Shanghai）还是新疆时间（Asia/Urumqi）。",
                )
        if clock_tz:
            values["tz"] = clock_tz
    if any(values[k] is None for k in ("tz", "lon")):
        raise NeedsInput(
            "missing_birth_location", "请补充出生地点，先用resolve_location解析经纬度和时区。"
        )
    return values


def birth_provenance(args, session):
    text = " ".join(session.user_messages)
    # Preserve punctuation equivalence without allowing fabricated dates or hours.
    normalized = re.sub(r"[年月/.]", "-", text).replace("日", " ").replace("T", " ")
    birth = args.birth_local
    if birth and birth != session.profile.get("birth_local_dt"):
        date = birth[:10]
        if date not in normalized:
            return "出生日期必须来自用户原话或已有画像，不能猜测"
        if args.time_known and len(birth) > 10 and birth[11:16] not in text:
            return "出生时刻必须有用户原话依据"
    if (
        not args.time_known
        and session.profile.get("time_known") is not False
        and not re.search(
            r"(?:不知道|不知|未知|不确定).{0,6}(?:时间|时辰)|(?:时间|时辰).{0,6}(?:不知道|不知|未知|不确定)",
            text,
        )
    ):
        return "出生时间未知须由用户明确说明；请先追问"
    if args.fold is not None and not re.search(
        rf"fold\s*=\s*{args.fold}|{'回拨前' if args.fold == 0 else '回拨后'}", text
    ):
        return "重复本地时间的fold必须由用户明确确认"
    if args.tz and args.tz != session.profile.get("tz"):
        aliases = {"Asia/Shanghai": "北京时间", "Asia/Urumqi": "新疆时间", "Etc/GMT-8": "UTC+8"}
        location = session.state.get("locations", {}).get(args.location_id, {})
        if (
            args.tz not in text
            and aliases.get(args.tz, args.tz) not in text
            and (args.tz != location.get("tz") or args.tz == "Asia/Urumqi")
        ):
            return "出生钟表时区须来自地点、用户原话或画像；新疆地点须确认钟表时间制"
    if not args.location_id:
        for field in ("lat", "lon", "tz"):
            value = getattr(args, field, None)
            if value is not None and value != session.profile.get(field) and str(value) not in text:
                return "经纬度与时区须来自地名解析、用户原话或画像，不能自行填写"
    return None


def range_provenance(args, session):
    text = " ".join(session.user_messages)
    # Explicit date range must match the human input; relative calendar requests are
    # anchored by the injected Asia/Shanghai date, never the host's timezone.
    explicit = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    if len(explicit) >= 2 and (args.start[:10], args.end[:10]) != (explicit[-2], explicit[-1]):
        return "计算日期范围必须与用户明确指定范围一致"
    current = session.state.get("timeframe")
    if current and current != (args.start, args.end):
        return "同一reading各体系必须使用相同时间范围；不同区间请开始新问题"
    return None


class MeaningPlugin:
    themes = {"career", "relationship", "self", "finance"}
    required_profile = set()  # Conditional birth requirements are handled with needs_input.

    def attach(self, result, atoms, session, result_key):
        result["interpretations"] = []
        for fact, kind, key, horizon, timeframe in atoms:
            entry = self.kb.lookup(self.name, kind, key)
            if entry is None:
                raise ValueError(f"Missing knowledge entry: {self.name}/{kind}/{key}")
            ref = f"{self.name}:{result.get('chart_id') or result.get('bazi_id')}:{fact}"
            components = [entry]
            for component_kind, component_key in self.compound_keys(result, kind, key, fact):
                component = self.kb.lookup(self.name, component_kind, component_key)
                if component is None:
                    raise ValueError(f"Missing compound entry: {component_kind}/{component_key}")
                if component["ref_id"] not in {c["ref_id"] for c in components}:
                    components.append(component)
            meaning = {k: entry[k] for k in ("text", "keywords", "theme_map", "reviewed", "ref_id")}
            weights = [1.0] + [self.kb.rules(self.name).get("context_weight", 0.25)] * (
                len(components) - 1
            )
            meaning["text"] = " ".join(c["text"] for c in components)
            meaning["theme_map"] = {
                theme: sum(
                    c["theme_map"].get(theme, 0) * w
                    for c, w in zip(components, weights, strict=True)
                )
                / sum(weights)
                for theme in {t for c in components for t in c["theme_map"]}
            }
            meaning["reviewed"] = all(c["reviewed"] for c in components)
            meaning["component_refs"] = [c["ref_id"] for c in components]
            result["interpretations"].append(
                dict(
                    ref_id=ref,
                    fact=fact,
                    kind=kind,
                    key=key,
                    horizon=horizon,
                    timeframe=timeframe,
                    meaning=meaning,
                )
            )
        signals = self.extract_signals([result])
        # Reusing a persistent chart must not create duplicate signals within a reading.
        old_refs = {s["ref_id"] for s in session.state["signals"]}
        session.state["signals"].extend(
            s.model_dump(mode="json") for s in signals if s.ref_id not in old_refs
        )
        session.state["allowed_refs"].update(s.ref_id for s in signals)
        session.state["kb_refs"].update(s.kb_ref for s in signals)
        session.state["kb_refs"].update(ref for s in signals for ref in s.kb_refs)
        session.state["kb_version"] = self.kb.version
        session.state[result_key] = result
        session.state.setdefault("calculations", {})[result_key] = result
        return result

    def compound_keys(self, result, kind, key, fact):
        return []

    def signal_strength(self, result, item, rule):
        return rule["strength"].get(item["kind"], 0.5)

    def extract_signals(self, results):
        rule = self.kb.rules(self.name)
        signals = []
        for result in results:
            for item in result["interpretations"]:
                entry = item["meaning"]
                for theme, valence in entry["theme_map"].items():
                    signals.append(
                        Signal(
                            ref_id=item["ref_id"],
                            system=self.name,
                            theme=theme,
                            valence=valence,
                            strength=self.signal_strength(result, item, rule),
                            horizon=item["horizon"],
                            timeframe=item["timeframe"],
                            keywords=tuple(entry["keywords"]),
                            kb_ref=entry["ref_id"],
                            kb_refs=tuple(entry.get("component_refs", [entry["ref_id"]])),
                            rule_version=rule["version"],
                            reviewed=entry["reviewed"],
                        )
                    )
        return signals
