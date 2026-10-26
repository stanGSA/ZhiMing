"""Shared deterministic plugin binding. No model-created profile or signals."""

import re

from pydantic import Field

from common.input_evidence import (
    DATE,
    birth_mentions,
    question_range,
    reading_text,
    supported_birth,
)
from common.location import consultation_timezone_evidence, xinjiang_birth_clock
from common.time_utils import NeedsInput, date_range
from harness.models import StrictInput
from knowledge.review import lowest
from plugins.base import MEANING_FIELDS, Signal


class BirthInput(StrictInput):
    birth_local: str | None = None
    location_id: str | None = None
    tz: str | None = None
    lat: float | None = Field(default=None, gt=-90, lt=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    time_known: bool = True
    fold: int | None = Field(default=None, ge=0, le=1)


def location_choices(session):
    locations = session.state.get("locations", {})
    choices = "、".join(
        f"{key}（{value.get('display_name') or value.get('name') or value.get('tz')}）"
        for key, value in locations.items()
    )
    return (
        "可用的 location_id：" + choices
        if choices
        else '请先调用 resolve_location(query="出生地原话")，如有同名候选用 ask_user 确认'
    )


def resolve_birth_location(args, session):
    if args.location_id:
        return
    locations = session.state.get("locations", {})
    confirmed = session.profile.get("location_id")
    if confirmed in locations:
        args.location_id = confirmed
    elif len(locations) == 1:
        args.location_id = next(iter(locations))


def inferred_birth(session):
    text = reading_text(session)
    mentions = set()
    for clause in re.split(r"[。；;\n]", text):
        dates = list(re.finditer(DATE, clause))
        for i, match in enumerate(dates):
            left = dates[i - 1].end() if i else 0
            right = dates[i + 1].start() if i + 1 < len(dates) else len(clause)
            prefix = re.split(r"[，,]", clause[max(left, match.start() - 24) : match.start()])[-1]
            suffix = clause[match.end() : right]
            # A meeting/travel clock later in the question is not a birth clock.
            if not (
                re.search(r"出生|生于|生辰|生日", prefix)
                or re.search(r"出生|生于|生辰|生日", suffix[:24])
            ):
                continue
            mentions.update(birth_mentions(clause[match.start() : right]))
    # A range date without a clock must not be chosen as a birth date.
    if len({day for day, _ in mentions}) > 1:
        return None
    precise = {(day, clock) for day, clock in mentions if clock}
    if len(precise) == 1:
        day, clock = precise.pop()
        return f"{day} {clock}"
    if len(mentions) == 1:
        day, clock = mentions.pop()
        if session.profile.get("time_known") is False or re.search(
            r"时[辰间].{0,6}(?:不知道|未知|不知)|(?:不知道|未知|不知).{0,6}时[辰间]",
            reading_text(session),
        ):
            return day
    return None


def birth_values(args, session):
    profile = session.profile
    resolve_birth_location(args, session)
    values = dict(
        birth_local=args.birth_local or profile.get("birth_local_dt") or inferred_birth(session),
        tz=args.tz or profile.get("tz"),
        lat=args.lat if args.lat is not None else profile.get("lat"),
        lon=args.lon if args.lon is not None else profile.get("lon"),
        time_known=args.time_known
        if "time_known" in args.model_fields_set
        else profile.get("time_known", args.time_known),
        fold=args.fold,
    )
    location = session.state.get("locations", {}).get(args.location_id)
    if args.location_id and location is None:
        raise NeedsInput("unresolved_location", location_choices(session))
    if location:
        values.update({k: location[k] for k in ("tz", "lat", "lon")})
        clock_tz = args.tz or profile.get("tz")
        if location["tz"] == "Asia/Urumqi":
            clock_tz = xinjiang_birth_clock(session, args.location_id)
            if clock_tz is None or (args.tz and args.tz != clock_tz):
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
    resolve_birth_location(args, session)
    if not args.birth_local and not session.profile.get("birth_local_dt"):
        args.birth_local = inferred_birth(session)
    birth = args.birth_local
    if birth and birth != session.profile.get("birth_local_dt"):
        known = args.time_known and len(birth) > 10
        if not supported_birth(birth, text, known) and not supported_birth(
            birth, str(session.profile.get("birth_local_dt", "")), known
        ):
            return "出生日期必须来自用户原话或已有画像，不能猜测。" + (
                f"原话中的出生时间是 {inferred_birth(session)}；请按此重试"
                if inferred_birth(session)
                else "请调用 ask_user 确认出生时间"
            )
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
    location = session.state.get("locations", {}).get(args.location_id, {})
    if (
        location.get("tz") == "Asia/Urumqi"
        and args.tz
        and args.tz != xinjiang_birth_clock(session, args.location_id)
    ):
        return "新疆出生钟表时区须由当前出生资料的用户确认，不能沿用旧出生地的选择"
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
    text = reading_text(session)
    # Explicit date range must match the human input; relative calendar requests are
    # anchored by the injected Asia/Shanghai date, never the host's timezone.
    explicit = question_range(text, getattr(session, "calendar_anchor", None))
    tz = (
        getattr(args, "tz", None)
        or session.profile.get("consultation_tz")
        or session.state.get("timeframe_tz")
        or "Asia/Shanghai"
    )
    try:
        actual = date_range(args.start, args.end, tz, 3660)
        if explicit and actual != date_range(*explicit, tz, 3660):
            return "计算日期范围必须与用户明确指定范围一致"
    except NeedsInput as exc:
        return exc.question
    current = session.state.get("timeframe")
    if current and actual != date_range(*current, session.state.get("timeframe_tz", tz), 3660):
        return "同一reading各体系必须使用相同时间范围；不同区间请开始新问题"
    return None


def confirmed_timezone(session, birth_tz):
    """The latest consultation timezone the user stated for this question, if any."""
    confirmed = None
    for text in session.user_messages[session.state.get("question_message_index", 0) :]:
        evidence = consultation_timezone_evidence(text, session, birth_tz)
        if evidence:
            confirmed = evidence
    return confirmed


def period_timezone(args, session, chart):
    """Consultation timezone is separate from the birth clock timezone."""
    tz = args.tz or session.profile.get("consultation_tz") or session.state.get("timeframe_tz")
    birth_tz = chart.get("input", {}).get("tz")
    confirmed = confirmed_timezone(session, birth_tz)
    if confirmed:
        if args.tz and args.tz != confirmed:
            raise NeedsInput(
                "confirm_period_timezone", "日期区间时区与用户确认不一致，请使用：" + confirmed
            )
        return confirmed
    if not tz and birth_tz == "Asia/Shanghai":
        tz = birth_tz
    if not tz:
        raise NeedsInput(
            "confirm_period_timezone",
            "请确认咨询日期区间按哪个城市的时间，可以说“按洛杉矶时间”或“按北京时间”；请先解析该城市。出生地不一定是当前所在地。",
        )
    if args.tz and tz != session.profile.get("consultation_tz") and tz != "Asia/Shanghai":
        raise NeedsInput("confirm_period_timezone", "请确认日期区间使用的时区：" + tz)
    if (
        args.tz == "Asia/Shanghai"
        and birth_tz != "Asia/Shanghai"
        and session.profile.get("consultation_tz") != "Asia/Shanghai"
    ):
        raise NeedsInput("confirm_period_timezone", "海外资料请确认咨询区间是否使用北京时间。")
    return tz


class MeaningPlugin:
    themes = {"career", "relationship", "self", "finance"}
    required_profile = set()  # Conditional birth requirements are handled with needs_input.

    def attach(self, result, atoms, session, result_key):
        result["interpretations"] = self.interpret(result, atoms)
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

    def interpret(self, result, atoms):
        """Knowledge entries for each calculated fact; no session, so direct callers share it."""
        interpretations = []
        for fact, kind, key, horizon, timeframe in atoms:
            entry = self.kb.lookup(self.name, kind, key)
            if entry is None:
                raise ValueError(f"Missing knowledge entry: {self.name}/{kind}/{key}")
            identity = (
                result[self.id_key]
                if getattr(self, "id_key", None)
                else result.get("chart_id") or result.get("bazi_id")
            )
            ref = f"{self.name}:{identity}:{fact}"
            components = [entry]
            for component_kind, component_key in self.compound_keys(result, kind, key, fact):
                component = self.kb.lookup(self.name, component_kind, component_key)
                if component is None:
                    raise ValueError(f"Missing compound entry: {component_kind}/{component_key}")
                if component["ref_id"] not in {c["ref_id"] for c in components}:
                    components.append(component)
            meaning = {k: entry[k] for k in MEANING_FIELDS}
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
            meaning["review_status"] = lowest(c["review_status"] for c in components)
            meaning["component_refs"] = [c["ref_id"] for c in components]
            interpretations.append(
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
        return interpretations

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
                            review_status=entry["review_status"],
                        )
                    )
        return signals
