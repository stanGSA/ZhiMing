"""Birth data typed into the question instead of the birth form (plan P3.1; astro and bazi).

The date and clock are read with plugins.context.inferred_birth, the same reading the
calculators' provenance check uses, and saved with a planned update_profile whose evidence is the
user's own message. The birth place is resolved with a planned resolve_location; a name shared by
several places is asked about, never chosen. Once the date and place are bound, the run goes on as
for the birth form: what is still missing (the clock, a Xinjiang clock, the solar-time choice…)
is asked by the calculator's own NeedsInput.

Left with the agent loop: a birth stated without a full date (“我是1990年3月出生的”), whose
month the Guard's question_range reads as a range; a birth that differs from the saved profile
(a correction); a birth typed while the web page's birth form is bound to the request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from common.input_evidence import DATE, clock_in
from common.location import ADMIN_ALIASES, COUNTRY_ALIASES, OTHER_PLACE, birth_place_mentioned
from plugins.context import birth_date_mentions, inferred_birth

UNKNOWN_TIME = re.compile(
    r"(?:不知道|不知|未知|不确定|查不到|不清楚).{0,6}(?:出生时间|时间|时辰|几点)"
    r"|(?:出生时间|时辰).{0,6}(?:不知道|未知|不知|不确定|不详|查不到|不清楚)"
)
# Time words that may follow a birth date: removed with it before a range is read.
TIME_TAIL = re.compile(
    r"[\s\d零〇一二两三四五六七八九十点时分秒半刻:：]*"
    r"(?:(?:凌晨|早上|上午|中午|下午|晚上|晚间)[\s\d零〇一二两三四五六七八九十点时分秒半刻:：]*)?"
)
PLACE = r"[一-鿿]{2,12}?"
END = r"(?=出生|人|[，,。；;！!？?、（(\s]|的|$)"
# “纽约（美国）出生”: a country or province in brackets after the place narrows it.
BRACKETED = re.compile(r"[（(](?P<hint>[^）)]{1,10})[）)]")
# Where a place is tied to a birth word: 出生在杭州 / 生于杭州 / 在杭州出生 / 杭州出生 /
# 出生地是杭州. Dates and clocks are removed first, so 出生于1993-08-17 23:20，北京 reads as
# 出生于 ，北京 (common.location.BIRTH_TIME_ONLY allows the same).
PLACE_PATTERNS = (
    re.compile(rf"出生地(?:点)?(?:是|为|在|：|:)?\s*(?P<place>{PLACE}){END}"),
    re.compile(rf"(?:出生|(?<![发产])生)(?:在|于)[\s，,]*(?P<place>{PLACE}){END}"),
    re.compile(rf"在(?P<place>{PLACE})出生"),
    re.compile(rf"(?P<place>{PLACE})出生"),
)
NOT_A_PLACE = re.compile(r"我|你|他|她|时间|时候|那天|当天|医院|家里|老家|早上|晚上|凌晨|下午|上午")
PROVINCES = tuple(
    sorted((name for name in ADMIN_ALIASES["CN"] if len(name) >= 2), key=len, reverse=True)
)
# A Chinese name for each country code a candidate may have, for the disambiguation question.
COUNTRY_ZH = {"CN": "中国", "US": "美国", "GB": "英国", "CA": "加拿大", "IN": "印度"}
COUNTRY_ZH |= {"NO": "挪威", "AU": "澳大利亚"}
ASK_PLACE = "请告诉我出生的城市（例如“杭州”“伦敦”），用来确定经纬度和时区。"


# A lunar birth date as compute_bazi's parse_lunar reads it (“农历2023年闰二月十五”), with the
# clock written after it in the same clause.
LUNAR = re.compile(
    r"(?:农历|阴历)\s*(?P<date>\d{4}年闰?(?:正|冬|腊|[一二三四五六七八九十]+)月"
    r"(?:初[一二三四五六七八九十]|十[一二三四五六七八九]?|廿[一二三四五六七八九]?|三十|\d{1,2}))"
)


@dataclass(frozen=True)
class Lunar:
    date: str  # as written, e.g. 2023年二月十五
    clock: str | None
    message: str
    unknown_time: bool

    @property
    def value(self) -> str:
        """compute_bazi's lunar_date: the date as written, and the clock as HH:MM."""
        return f"{self.date} {self.clock}" if self.clock else self.date


def typed_lunar(text: str) -> Lunar | None:
    """The one lunar birth date a message states (only bazi computes from one)."""
    found = {m["date"]: m for m in LUNAR.finditer(text)}
    if len(found) != 1 or not re.search(r"出生|生于|生日|生辰", text):
        return None
    match = next(iter(found.values()))
    tail = re.split(r"[。；;\n]", text[match.end() :], maxsplit=1)[0]
    return Lunar(match["date"], clock_in(tail), text, bool(UNKNOWN_TIME.search(text)))


@dataclass(frozen=True)
class Typed:
    day: str
    clock: str | None
    message: str  # the user's message that states the date, the evidence saved with it
    unknown_time: bool

    @property
    def value(self) -> str:
        return f"{self.day} {self.clock}" if self.clock else self.day


def typed(text: str) -> Typed | None:
    """The one birth date a message states, with its clock when it states one."""
    mentions = birth_date_mentions(text)
    if len({day for day, _ in mentions}) != 1:
        return None
    clocks = {clock for _, clock in mentions if clock}
    if len(clocks) > 1:
        return None
    day = next(iter(mentions))[0]
    return Typed(day, next(iter(clocks), None), text, bool(UNKNOWN_TIME.search(text)))


def without_birth(text: str) -> str:
    """The text with each birth date and the clock after it removed, so a range is not read
    from them (r3: the Guard's question_range reads “1990年3月” as a month to compute)."""
    spans = []
    for clause in re.finditer(r"[^。；;\n]+", text):
        part = clause.group()
        dates = list(re.finditer(DATE, part))
        for index, match in enumerate(dates):
            left = dates[index - 1].end() if index else 0
            prefix = re.split(r"[，,]", part[max(left, match.start() - 24) : match.start()])[-1]
            suffix = part[match.end() : match.end() + 24]
            if re.search(r"出生|生于|生辰|生日", prefix) or re.search(
                r"出生|生于|生辰|生日", suffix
            ):
                tail = TIME_TAIL.match(part, match.end())
                spans.append((clause.start() + match.start(), clause.start() + tail.end()))
    for match in LUNAR.finditer(text):
        tail = TIME_TAIL.match(text, match.end())
        spans.append((match.start(), tail.end()))
    for start, end in sorted(set(spans), reverse=True):
        text = text[:start] + " " + text[end:]
    return text


def places(text: str) -> list[str]:
    """Places the message names as the birth place, most specific wording first."""
    scrubbed = BRACKETED.sub("", re.sub(DATE, " ", text))
    scrubbed = TIME_TAIL.sub(lambda m: " " if m.group().strip() else m.group(), scrubbed)
    found = []
    for pattern in PLACE_PATTERNS:
        for match in pattern.finditer(scrubbed):
            place = match["place"]
            if NOT_A_PLACE.search(place) or OTHER_PLACE.search(place):
                continue
            if place in text and birth_place_mentioned(text, place) and place not in found:
                found.append(place)
    return found


def hint(text: str, place: str) -> dict:
    """resolve_location narrowing the user wrote in brackets right after the place."""
    match = re.search(re.escape(place) + BRACKETED.pattern, text)
    return narrowing(match["hint"], None) if match else {}


def variants(place: str) -> list[str]:
    """The wordings tried in turn: as written, cut after 市 or 县, without a province before it."""
    out = [place]
    for mark in ("市", "县"):
        cut = re.match(rf"(.+?{mark})", place)
        if cut and cut[1] != place:
            out.append(cut[1])
            break
    for province in PROVINCES:
        if place.startswith(province) and len(place) > len(province) + 1:
            out.append(place[len(province) :])
            break
    if place.startswith("中国") and len(place) > 3:
        out.append(place[2:])
    return list(dict.fromkeys(v for v in out if len(v) >= 2))


def candidates_question(place: str, candidates: list[dict]) -> str:
    listed = "；".join(
        f"{c.get('name')}（{COUNTRY_ZH.get(c['country'], c['country'])}"
        + (f"·{c['admin1']}" if c.get("admin1") else "")
        + "）"
        for c in candidates[:5]
    )
    return (
        f"“{place}”有几个同名的地方：{listed}。请告诉我是哪个国家或省州的，例如“英国”或“加拿大”。"
    )


def narrowing(answer: str, candidates: list[dict] | None) -> dict:
    """resolve_location arguments the answer supports: a country or province named in it.

    Only words the user wrote are passed, so the tool's own validator accepts them. Without
    candidates, any country or Chinese province the answer names is passed.
    """
    if candidates is None:
        for alias in sorted(COUNTRY_ALIASES, key=len, reverse=True):
            if alias in answer:
                return {"country": alias}
        return {}
    countries = {c["country"] for c in candidates}
    for alias, code in sorted(COUNTRY_ALIASES.items(), key=lambda pair: -len(pair[0])):
        if code in countries and alias in answer:
            arguments = {"country": alias}
            admins = ADMIN_ALIASES.get(code, {})
            for name, admin in sorted(admins.items(), key=lambda pair: -len(pair[0])):
                if name in answer and any(c["admin1"] == admin for c in candidates):
                    arguments["admin1"] = name
                    break
            return arguments
    for code in countries:
        for name, admin in sorted(
            ADMIN_ALIASES.get(code, {}).items(), key=lambda pair: -len(pair[0])
        ):
            if name in answer and any(c["admin1"] == admin for c in candidates):
                return {"admin1": name}
    return {}


def bound(session) -> bool:
    """A birth date (saved, or a lunar one kept with the reading) and a birth place resolved
    in this reading, without the birth form."""
    dated = session.profile.get("birth_local_dt") or session.state.get("typed_lunar")
    return bool(dated) and len(session.state.get("locations", {})) == 1


async def bind(system, runner, run):
    """Save a typed birth and resolve its place; a TurnOutcome when something must be asked.

    ``system`` supplies ask(runner, run, question, needs) and the form question it asks when the
    message has no full birth date. Called after start_reading, which starts a fresh state.
    """
    session = runner.session
    state = session.state
    index = state.get("question_message_index", 0)
    messages = session.user_messages[index:] if index >= 0 else session.user_messages[-1:]
    stated = next((t for t in map(typed, messages) if t), None)
    lunar = None
    if stated is None and getattr(system, "lunar", False):
        lunar = next((t for t in map(typed_lunar, messages) if t), None)
    if stated is None and lunar is None:
        return await system.ask(runner, run, system.birth_form, "birth")
    profile = session.profile
    if lunar is not None:
        # The calculator converts the lunar date once the leap month is confirmed; the date is
        # kept with the reading, not saved to the profile as a solar one.
        state["typed_lunar"] = lunar.value
        stated = lunar
    elif str(profile.get("birth_local_dt") or "") != (inferred_birth(session) or stated.value):
        value = inferred_birth(session) or stated.value
        results, _ = await runner.planned(
            [
                (
                    "update_profile",
                    {"field": "birth_local_dt", "value": value, "evidence": stated.message},
                )
            ]
        )
        if not results[0]["ok"]:
            return await system.ask(runner, run, system.birth_form, "birth")
    if stated.unknown_time and session.profile.get("time_known") is not False:
        await runner.planned(
            [
                (
                    "update_profile",
                    {"field": "time_known", "value": False, "evidence": stated.message},
                )
            ]
        )
    if state.get("locations"):
        return None
    answer = session.user_messages[-1] if session.user_messages else ""
    if run.needs == "location_choice" and state.get("birth_place_query"):
        query = state["birth_place_query"]
        arguments = narrowing(answer, state.get("birth_place_candidates", []))
        if not arguments:
            return await system.ask(
                runner,
                run,
                candidates_question(query, state["birth_place_candidates"]),
                "location_choice",
            )
        results, _ = await runner.planned([("resolve_location", {"query": query, **arguments})])
        return await located(system, runner, run, query, results[0])
    wordings = places(stated.message)
    if run.needs == "birth_place":
        wordings = places(answer) or [answer.strip().rstrip("。.！!")]
    for place in wordings:
        narrowed = hint(stated.message, place)
        for query in variants(place):
            results, _ = await runner.planned([("resolve_location", {"query": query, **narrowed})])
            result = results[0]
            if result["ok"] and result["data"].get("code") == "missing_location":
                continue
            return await located(system, runner, run, query, result)
    return await system.ask(runner, run, ASK_PLACE, "birth_place")


async def located(system, runner, run, query: str, result: dict):
    """After resolve_location: nothing to ask once the place is resolved."""
    state = runner.session.state
    if not result["ok"]:
        return await system.ask(runner, run, ASK_PLACE, "birth_place")
    data = result["data"]
    if data.get("status") == "resolved":
        state.pop("birth_place_candidates", None)
        return None
    candidates = data.get("candidates") or []
    if not candidates:
        return await system.ask(runner, run, ASK_PLACE, "birth_place")
    state["birth_place_query"] = query
    state["birth_place_candidates"] = candidates
    return await system.ask(runner, run, candidates_question(query, candidates), "location_choice")
