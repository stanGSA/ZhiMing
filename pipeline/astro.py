"""Astrology in the pipeline: the natal chart and transits over a range (plan P3).

Code decides everything a calculation needs (pipeline/requirements.py): whether the birth data
is there, the range of dates a timing question asks about and its consultation timezone. What
is missing is asked with a templated question that ends the turn; the next message resumes the
run where it stopped. The planned calls are compute_natal_chart and, for a timing question,
compute_transits, both through the Guard. The writer cites planets, signs, houses, aspects and
transit dates by number only; what it writes by hand is checked against the chart (P3.4).

Left with the agent loop in this first P3 step: follow-ups to a saved reading, corrections of
birth data, birth data typed into the message instead of the birth form (resolving a place
needs the location tool), techniques the calculator does not have (synastry, progressions…)
and questions that also name another system (问道's several systems are P3.5).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from common.input_evidence import DATE as BIRTH_DATE
from common.input_evidence import clock_in
from common.time_utils import NeedsInput
from harness.failures import failure
from harness.refs import short
from pipeline import compose, requirements
from pipeline.factsheet import CAVEAT, Fact, shorten
from pipeline.intent import CONTINUE, Intent
from pipeline.render import safety_for
from pipeline.state import RESUMABLE, snapshot
from pipeline.system import System
from plugins.astro.calculator import BODY_ZH, SIGN_ZH
from plugins.astro.tools import AstroPlugin
from plugins.astro.validation import DATE, aspect_assertions

ASTRO = re.compile(
    # 上升 alone is ordinary prose (压力上升); the rising sign is named as such.
    r"星盘|占星|星座|本命盘|行运|上升(?:星座|点|在|是|落)|太阳星座|月亮星座|水逆|行星|宫位|相位|"
    r"土星|木星|金星|火星|水星|冥王|海王|天王"
)
OTHER = re.compile(
    r"塔罗|牌阵|抽[一二两三]?张|八字|四柱|命盘|命理|紫微|姓名|名字|五格|解梦|梦见|梦到|做梦|"
    r"流年|流月|流日|大运|日柱|十神|干支|每日运势|今日运势|今天运势"
)
# Techniques compute_natal_chart and compute_transits do not calculate.
UNSUPPORTED = re.compile(
    r"合盘|配对|比较盘|组合盘|两个人的星盘|推运|次限|三限|太阳弧|返照|日返|月返|法达|小限|"
    r"中点|小行星|凯龙|莉莉丝|北交|南交|婚神|谷神|恒星"
)
REFERS_TO_READING = re.compile(
    r"(?:上一条|上一次|上次|刚才|之前|前面|那次|原来)(?:那个|这个|那次|那条|的)?"
    r"(?:星盘|解读|记录|分析|结果)|原记录|[这那]段解读|(?:你|刚才)(?:说|提到)的"
)
BIRTH_CORRECTION = re.compile(
    r"(?:出生(?:日期|时间|时刻|地点|资料|信息)|出生信息|出生表单).{0,16}"
    r"(?:更正|改成|改为|记错|不准确|不对)|"
    r"(?:更正|改成|改为|记错|不准确|不对).{0,16}"
    r"(?:出生(?:日期|时间|时刻|地点|资料|信息)|出生信息|出生表单)"
)
UNKNOWN_TIME = re.compile(
    r"(?:不知道|不知|未知|不确定|查不到|不清楚).{0,6}(?:出生时间|时间|时辰|几点)"
    r"|(?:出生时间|时辰).{0,6}(?:不知道|未知|不知|不确定|不详|查不到|不清楚)"
)
# Transit bodies in the order AstroPlugin.project lists them, in three tiers.
SLOW = ("Saturn", "Jupiter", "Mars", "Uranus", "Neptune", "Pluto")
TRANSIT_TIERS = (SLOW, (*SLOW, "Sun", "Mercury", "Venus"), None)
LISTED_TRANSITS = 12
# A pipeline run asks at most twice; a third message goes to the agent loop.
MAX_ASKS = 2
ASPECT_ZH = {
    "conjunction": "合相",
    "opposition": "对分相",
    "square": "四分相",
    "trine": "三分相",
    "sextile": "六分相",
}
SIGN_NAMES = "|".join(SIGN_ZH)
BODY_NAMES = "|".join(BODY_ZH.values())
HOUSE_NUMBER = r"[一二三四五六七八九十]{1,3}|\d{1,2}"
# “太阳在金牛座”“太阳的星座是金牛”“太阳星座金牛”“月亮落在了天蝎”, and the same said of several
# planets at once (“太阳、水星都落在天秤座”“土星与海王星同在摩羯座”): each listed planet is
# checked. The sign or house may also come first (“天秤座的太阳和水星”). Denials are left to
# the shared validator, which runs after these.
PLACED = r"(?:的)?(?:星座|所在星座)?(?:落在|落入|落于|落|进入|在|位于|处于|是|为)?了?"
ADVERB = r"(?:都|也|均|皆|同|同样|一起|一同|全都|还|又|则|正好|恰好){0,2}"
JOINER = r"(?:、|和|与|及|以及|跟)"
BODIES = rf"(?P<bodies>(?:{BODY_NAMES})(?:{JOINER}(?:本命)?的?(?:{BODY_NAMES}))*)"
SIGN_CLAIM = re.compile(
    rf"(?P<marker>行运|本命)?的?{BODIES}{ADVERB}{PLACED}(?P<sign>{SIGN_NAMES})(?:座)?"
)
SIGN_FIRST = re.compile(rf"(?P<sign>{SIGN_NAMES})座?(?:里|中)?的{BODIES}")
HOUSE_CLAIM = re.compile(
    rf"(?P<marker>行运|本命)?的?{BODIES}(?:的)?(?:宫位)?{ADVERB}"
    rf"(?:落在|落入|落于|落|进入|在|位于|处于|是|为)?了?第?(?P<house>{HOUSE_NUMBER})宫"
)
HOUSE_FIRST = re.compile(rf"第(?P<house>{HOUSE_NUMBER})宫(?:里|中)?的{BODIES}")
# A placeholder renders “本命太阳在金牛座” / “行运土星与本命太阳三分相”: written in front of one,
# 本命 or 行运 appears twice (r1 unclear_range#2: “你本命本命水星在金牛座”).
REPEATED_LABEL = re.compile(r"(本命|行运)的?\1")
ANGLE_CLAIM = re.compile(
    rf"(?P<angle>上升|天顶)(?:星座)?(?:是|为|在|落在|落)?(?P<sign>{SIGN_NAMES})"
)
# Relative time words and the span each names, from the calendar's today (r1
# next_month_career#1: the user asked about 下个月, the summary said 这个月).
RELATIVE = re.compile(r"下下个月|下个月|这个月|本月|下周|这周|本周|今天|明天|后天|明年|今年")
COMPARED = re.compile(r"比(?!较)|相比|比起|不是|而不是|并非|之前|以前|已经|过去|上个月|刚过")
# Parts of a month a section title may name, and what widens or extends them.
PARTS = (
    (re.compile(r"上旬|月初"), (1, 10)),
    (re.compile(r"中旬|月中"), (11, 20)),
    (re.compile(r"下旬|月底|月末"), (21, 31)),
)
AROUND = re.compile(r"前后|左右|附近|一带")
LATER = re.compile(r"(?:上旬|月初|中旬|月中)(?:以后|之后|起|开始)")
EARLIER = re.compile(r"(?:中旬|月中|下旬|月底|月末)(?:以前|之前|前)(?!后)")
TOLERANCE = 2


def part_of_month(day: int) -> str:
    return "上旬" if day <= 10 else "中旬" if day <= 20 else "下旬"


def relative_span(word: str, today: date) -> tuple[date, date]:
    """The dates a relative time word names, counted from ``today``."""
    import calendar as months

    def month(offset: int) -> tuple[date, date]:
        year, index = divmod(today.year * 12 + today.month - 1 + offset, 12)
        last = months.monthrange(year, index + 1)[1]
        return date(year, index + 1, 1), date(year, index + 1, last)

    monday = today - timedelta(days=today.weekday())
    spans = {
        "这个月": month(0),
        "本月": month(0),
        "下个月": month(1),
        "下下个月": month(2),
        "这周": (monday, monday + timedelta(days=6)),
        "本周": (monday, monday + timedelta(days=6)),
        "下周": (monday + timedelta(days=7), monday + timedelta(days=13)),
        "今天": (today, today),
        "明天": (today + timedelta(days=1), today + timedelta(days=1)),
        "后天": (today + timedelta(days=2), today + timedelta(days=2)),
        "今年": (date(today.year, 1, 1), date(today.year, 12, 31)),
        "明年": (date(today.year + 1, 1, 1), date(today.year + 1, 12, 31)),
    }
    return spans[word]


TIMING_LABELS = ("行运相位", "行运")
SECTION_ORDER = ("行运相位", "行运", "本命落座", "本命宫位", "本命相位")
MAX_NATAL_ASPECTS = 8
SAFETY_FALLBACK = "这类问题牵涉重大的现实决定，请结合专业意见再做判断。"


def chinese(keywords) -> list[str]:
    return [k for k in keywords or [] if re.search(r"[一-鿿]", k)]


def chinese_number(text: str) -> int:
    if text.isdigit():
        return int(text)
    digits = dict(zip("一二三四五六七八九", range(1, 10), strict=True))
    if text == "十":
        return 10
    if text.startswith("十"):
        return 10 + digits.get(text[1:], 0)
    if text.endswith("十"):
        return digits.get(text[0], 0) * 10
    if "十" in text:
        head, tail = text.split("十", 1)
        return digits.get(head, 0) * 10 + digits.get(tail, 0)
    return digits.get(text, 0)


def local_date(value: str) -> str:
    day = date.fromisoformat(value)
    return f"{day.year}年{day.month}月{day.day}日"


def zone_label(tz: str) -> str:
    return "北京时间" if tz == "Asia/Shanghai" else f"{tz}当地日期"


class Astro(System):
    name = "astro"
    kept = "星盘计算结果"

    # ---- ① intent ------------------------------------------------------------------------

    def detect(self, runtime, message):
        session = runtime.session
        selected = session.state.get("selected_systems")
        if selected not in (None, ["astro"]) or session.pinned_reading_id:
            return None
        question = self.question(message)
        run = runtime.store.unfinished_pipeline_run(session.user_id)
        if run and run["state"].get("system") == "astro" and run["stage"] == "awaiting_input":
            if not self.answering(session, run):
                # A question asked in another conversation, or answered by something else
                # since: this message is not its answer.
                runtime.store.finish_pipeline_run(run["run_id"])
                run = None
        if run and run["state"].get("system") == "astro":
            if run["stage"] == "awaiting_input":
                handed = (
                    (selected is None and OTHER.search(question))
                    or run["state"].get("asks", 0) >= MAX_ASKS
                    or (
                        run["state"].get("needs") == "birth"
                        and not requirements.birth_ready(session)
                    )
                )
                if handed:
                    # Another question, or what was asked is still missing: the agent loop
                    # takes over (it can resolve a place typed into the message).
                    runtime.store.finish_pipeline_run(run["run_id"])
                    return None
                return Intent("astro", "input", run=run)
            if run["stage"] in RESUMABLE and (
                CONTINUE.search(message) or question == run["state"]["question"].strip()
            ):
                return Intent("astro", "resume", run=run)
        if selected is None and (OTHER.search(question) or not ASTRO.search(question)):
            return None
        if (
            UNSUPPORTED.search(question)
            or REFERS_TO_READING.search(question)
            or BIRTH_CORRECTION.search(question)
        ):
            return None
        if not requirements.birth_ready(session) and (
            re.search(BIRTH_DATE, question) or re.search(r"出生|生于", question)
        ):
            return None  # birth data in words: the agent loop resolves and saves it
        return Intent("astro", "new")

    @staticmethod
    def answering(session, run: dict) -> bool:
        """Whether the run's question is the last thing said to the user in this conversation."""
        asked = run["state"].get("asked")
        last = next(
            (
                m.get("content") or ""
                for m in reversed(session.messages)
                if m["role"] == "assistant"
            ),
            "",
        )
        return bool(asked) and run.get("session_id") == session.id and asked in last

    def question(self, message):
        return requirements.strip_birth_note(message).strip() or message

    # ---- ② requirements and ③ compute ----------------------------------------------------

    def text(self, run, session) -> str:
        """The question and every answer given since, as the calculators read them."""
        index = session.state.get("question_message_index", 0)
        answers = session.user_messages[index:] if index >= 0 else session.user_messages[-1:]
        parts = [run.question, *(requirements.strip_birth_note(a) for a in answers)]
        return " ".join(dict.fromkeys(p.strip() for p in parts if p and p.strip()))

    async def ask(self, runner, run, question: str, needs: str):
        """End the turn with a question; the run waits for the answer (stage awaiting_input)."""
        session = runner.session
        run.asks += 1
        run.needs = needs
        run.asked = question
        _, terminal = await runner.planned([("ask_user", {"question": question})])
        run.snapshot = snapshot(session.state)
        run.save(runner.store, session, "awaiting_input")
        return terminal or failure(session, "tool_error", "ask_failed", question)

    async def compute(self, runner, run):
        session = runner.session
        state = session.state
        if not (run.reading_id and state.get("active_reading_id") == run.reading_id):
            results, _ = await runner.planned(
                [("start_reading", {"question": run.question, "systems": ["astro"]})]
            )
            if not results[0]["ok"]:
                error = results[0]
                return failure(session, "tool_error", error.get("code"), error["error"])
            run.reading_id = session.state["active_reading_id"]
            state = session.state
        text = self.text(run, session)
        if not state.get("astro_question_type"):
            timing = requirements.asked_range(text, session.calendar_anchor) is not None
            state["astro_question_type"] = (
                "timing" if timing or requirements.is_timing(run.question) else "trait"
            )
        if not requirements.birth_ready(session):
            return await self.ask(runner, run, requirements.BIRTH_FORM, "birth")
        if not state.get("natal_result"):
            arguments = {}
            if session.profile.get("time_known") is False or UNKNOWN_TIME.search(text):
                arguments["time_known"] = False
            answer = session.user_messages[-1] if session.user_messages else ""
            if run.needs == "missing_birth_time":
                clock = clock_in(answer)
                birth = session.profile.get("birth_local_dt")
                if clock and birth:
                    arguments["birth_local"] = f"{birth[:10]} {clock}"
            elif run.needs == "ambiguous_local_time":
                fold = re.search(r"fold\s*=\s*([01])", answer)
                if fold:
                    arguments["fold"] = int(fold[1])
                elif "回拨前" in answer:
                    arguments["fold"] = 0
                elif "回拨后" in answer:
                    arguments["fold"] = 1
            results, _ = await runner.planned([("compute_natal_chart", arguments)])
            stopped = await self.checked(runner, run, results[0])
            if stopped is not None:
                return stopped
        if state["astro_question_type"] != "timing" or state.get("transit_result"):
            return None
        found = requirements.asked_range(text, session.calendar_anchor)
        if found is None:
            return await self.ask(runner, run, requirements.UNCLEAR_RANGE, "range")
        start, end = found
        if (date.fromisoformat(end) - date.fromisoformat(start)).days >= 3660:
            return await self.ask(runner, run, requirements.TOO_LONG, "range")
        try:
            period = requirements.period_choice(session, state["natal_result"], start, end)
        except NeedsInput as exc:
            return await self.ask(runner, run, exc.question, "timezone")
        # compute_transits reads the consultation timezone from here when none is passed
        # (plugins.context.period_timezone); its own checks are unchanged.
        state["timeframe_tz"] = period.tz
        state["timeframe_default"] = period.defaulted
        # The fact sheet lists twelve transits, slow planets first (AstroPlugin.project). The
        # slow planets are computed first and faster ones only while fewer than twelve
        # events are found: the listed twelve are the same as from all ten planets, and a
        # year's range no longer computes every lunar aspect (r1 P95 199 s, mostly the Moon).
        for bodies in TRANSIT_TIERS:
            arguments = {"chart_id": state["chart_id"], "start": start, "end": end}
            if bodies is not None:
                arguments["bodies"] = list(bodies)
            results, _ = await runner.planned([("compute_transits", arguments)])
            stopped = await self.checked(runner, run, results[0])
            if stopped is not None:
                return stopped
            state["transit_bodies"] = list(bodies) if bodies is not None else None
            if len(state["transit_result"]["events"]) >= LISTED_TRANSITS:
                return None
        return None

    async def checked(self, runner, run, result: dict):
        if not result["ok"]:
            return failure(runner.session, "tool_error", result.get("code"), result["error"])
        data = result["data"]
        if data.get("status") == "needs_input":
            return await self.ask(runner, run, data["question"], data.get("code") or "input")
        return None

    # ---- ④ fact sheet --------------------------------------------------------------------

    def question_type(self, run, session, followup):
        return session.state.get("astro_question_type") or "trait"

    def facts(self, session):
        state = session.state
        natal = state.get("natal_result") or {}
        transit = state.get("transit_result") or {}
        timing = state.get("astro_question_type") == "timing"
        allowed = state.get("allowed_refs", ())
        items = []
        if timing and transit:
            selected = AstroPlugin.project(dict(transit))
            kept = {item["fact"] for item in selected["interpretations"]}
            items += [i for i in transit.get("interpretations", []) if i["fact"] in kept]
            bodies = {e["natal_body"] for e in selected["events"]}
            items += [
                i
                for i in natal.get("interpretations", [])
                if i["kind"] == "planet_sign" and i["fact"].split(":")[0] in bodies
            ]
        else:
            interpretations = natal.get("interpretations", [])
            items += [i for i in interpretations if i["kind"] in ("planet_sign", "planet_house")]
            aspects = sorted(
                (i for i in interpretations if i["kind"] == "aspect"),
                key=lambda i: natal["aspects"][int(i["fact"].split(":")[0][12:])]["orb"],
            )
            items += aspects[:MAX_NATAL_ASPECTS]
        texts = self.texts(state)
        facts = []
        for item in items:
            if item["ref_id"] not in allowed or item["fact"] not in texts:
                continue
            label, text = texts[item["fact"]]
            alias = short(item["ref_id"], session)
            when = ""
            if label == "行运相位" and self.spans_a_month(transit):
                day = int(item["timeframe"][8:10])
                when = f"｜时段：{item['timeframe'][5:7].lstrip('0')}月{part_of_month(day)}"
            meaning = item.get("meaning") or {}
            keywords = "、".join(chinese(meaning.get("keywords"))[:6])
            general = shorten(CAVEAT.sub("", meaning.get("text") or ""), 140)
            line = (
                f"{alias}｜{label}｜{text}{when}｜关键词：{keywords or '无'}"
                f"｜一般含义：{general or '无'}"
            )
            facts.append(Fact(alias, item["ref_id"], label, text, line))
        return facts

    @staticmethod
    def spans_a_month(transit: dict) -> bool:
        if not transit:
            return False
        start, end = date.fromisoformat(transit["start"]), date.fromisoformat(transit["end"])
        return (end - start).days >= 10

    @staticmethod
    def texts(state) -> dict[str, tuple[str, str]]:
        """fact → (where it sits on the fact sheet, the text code renders for it)."""
        natal = state.get("natal_result") or {}
        out = {}
        for planet in natal.get("planets", []):
            body = planet["body_zh"]
            out[f"{planet['body']}:{planet['sign']}"] = (
                "本命落座",
                f"本命{body}在{planet['sign_zh']}座",
            )
            if planet["house"] is not None:
                out[f"{planet['body']}:house{planet['house']}"] = (
                    "本命宫位",
                    f"本命{body}在第{planet['house']}宫",
                )
        for index, aspect in enumerate(natal.get("aspects", [])):
            fact = f"natal_aspect{index}:{aspect['a']}:{aspect['b']}:{aspect['type']}"
            out[fact] = (
                "本命相位",
                f"本命{BODY_ZH[aspect['a']]}与{BODY_ZH[aspect['b']]}{ASPECT_ZH[aspect['type']]}",
            )
        transit = state.get("transit_result") or {}
        tz = transit.get("tz")
        for event in transit.get("events", []):
            fact = (
                f"transit:{event['exact_utc']}:{event['transit_body']}:"
                f"{event['natal_body']}:{event['aspect']}"
            )
            out[fact] = (
                "行运相位",
                f"行运{BODY_ZH[event['transit_body']]}与本命{BODY_ZH[event['natal_body']]}"
                f"{ASPECT_ZH[event['aspect']]}（{local_date(event['exact_date'])}精确，{zone_label(tz)}）",
            )
        if transit:
            out[f"transit:{transit['start']}:{transit['end']}:no_exact_events"] = (
                "行运",
                f"{local_date(transit['start'])}至{local_date(transit['end'])}没有精确行运相位",
            )
        return out

    # ---- ⑤ compose -----------------------------------------------------------------------

    def context(self, session) -> list[str]:
        state = session.state
        natal = state.get("natal_result") or {}
        transit = state.get("transit_result") or {}
        lines = []
        if state.get("astro_question_type") == "timing" and transit:
            lines.append(
                f"问题类型：时机。日期范围：{transit['start']}至{transit['end']}（{transit['tz']}，首尾两天都含）"
            )
            phrase = RELATIVE.search(session.state.get("question") or "")
            if phrase:
                lines.append(
                    f"用户说的时间是“{phrase[0]}”，即{transit['start']}至{transit['end']}；"
                    f"正文提到这段时间时写“{phrase[0]}”或具体月份，不要换成别的说法（如“这个月”）。"
                )
            if self.spans_a_month(transit):
                lines.append(
                    "按上旬、中旬、下旬或月初、月中、月底分段时，每段只放事实表“时段”一栏对应的相位。"
                )
            total = len(transit.get("events", []))
            listed = min(total, LISTED_TRANSITS)
            if total > listed:
                lines.append(f"这段时间的精确行运相位按慢行星优先，事实表列出其中{listed}个。")
        else:
            lines.append("问题类型：本命（性格、倾向、做事方式）")
        if not natal.get("time_known", True):
            lines.append(
                "出生时间未知：没有宫位和上升、天顶，不要提宫位、上升或天顶；月亮落座可能有误差。"
            )
        lines.append(
            "时间口径：相位的精确日期是计算时刻，不是现实事件发生的日期；一个相位的影响不只在那一天。"
        )
        return lines

    def messages(self, run, facts, session, *, prior=None, extra=""):
        return compose.astro_messages(run.question, self.context(session), facts, extra=extra)

    # ---- ⑥ verify ------------------------------------------------------------------------

    def problems(self, texts, session):
        """The chart's closed vocabulary (plan P3.4) and the shared wording rules.

        Signs, houses, the angles, aspects and dates written by hand must be the chart's; a
        placeholder renders them right, so these catch what the writer wrote instead of one.
        """
        state = session.state
        natal = state.get("natal_result") or {}
        transit = state.get("transit_result") or {}
        planets = {p["body_zh"]: p for p in natal.get("planets", [])}
        known = natal.get("time_known", True)
        natal_aspects = {(a["a"], a["b"], a["type"]) for a in natal.get("aspects", [])} | {
            (a["b"], a["a"], a["type"]) for a in natal.get("aspects", [])
        }
        events = {
            (e["transit_body"], e["natal_body"], e["aspect"]) for e in transit.get("events", [])
        }
        # A date on its own must be one of the fact sheet's: a listed transit's, the range's
        # first or last day, or the birth date. A date in a sentence that names a transit
        # aspect must be that aspect's own: any event's date is too wide a set, since over two
        # months nearly every day is some event's.
        listed = AstroPlugin.project(dict(transit))["events"] if transit else []
        dates = {e["exact_date"] for e in listed}
        if transit:
            dates |= {transit["start"], transit["end"]}
        dates.add(str((natal.get("input") or {}).get("birth_local") or "")[:10])
        dated: dict[tuple, set[str]] = {}
        for e in transit.get("events", []):
            key = (e["transit_body"], e["natal_body"], e["aspect"])
            dated.setdefault(key, set()).add(e["exact_date"])
        found = []
        for text in texts:
            for match in REPEATED_LABEL.finditer(text):
                found.append(
                    f"“{match[0]}”把“{match[1]}”写了两遍：编号会替换成带“本命”或“行运”的文字，"
                    "编号前不要再写"
                )
            for match in [*SIGN_CLAIM.finditer(text), *SIGN_FIRST.finditer(text)]:
                if re.search(
                    r"(?:并)?(?:不是|并非|不在|没在|未在)\s*$",
                    text[max(0, match.start() - 8) : match.start()],
                ):
                    continue
                sign = match["sign"]
                for body in re.findall(BODY_NAMES, match["bodies"]):
                    if match.groupdict().get("marker") == "行运":
                        found.append(
                            f"行运{body}的星座不在事实表里：“{match[0]}”；行运只写事实表里的相位编号"
                        )
                        break
                    if body in planets and planets[body]["sign_zh"] != sign:
                        found.append(
                            f"本命{body}在{planets[body]['sign_zh']}座，正文写成了{sign}座"
                        )
            for match in [*HOUSE_CLAIM.finditer(text), *HOUSE_FIRST.finditer(text)]:
                if re.search(
                    r"(?:并)?(?:不是|并非|不在|没在|未在)\s*$",
                    text[max(0, match.start() - 8) : match.start()],
                ):
                    continue
                house = chinese_number(match["house"])
                if not known:
                    found.append("出生时间未知，没有宫位，正文不能写宫位")
                    continue
                for body in re.findall(BODY_NAMES, match["bodies"]):
                    if match.groupdict().get("marker") == "行运":
                        found.append(f"行运{body}的宫位不在事实表里：“{match[0]}”")
                        break
                    if body in planets and planets[body]["house"] != house:
                        found.append(
                            f"本命{body}在第{planets[body]['house']}宫，正文写成了第{house}宫"
                        )
            for match in ANGLE_CLAIM.finditer(text):
                angle = "asc" if match["angle"] == "上升" else "mc"
                if not known or not natal.get(angle):
                    found.append(f"出生时间未知，没有{match['angle']}星座，正文不能写")
                elif natal[angle]["sign_zh"] != match["sign"]:
                    found.append(
                        f"{match['angle']}是{natal[angle]['sign_zh']}座，正文写成了{match['sign']}座"
                    )
            for _, source, target, aspect in aspect_assertions(text):
                if (source, target, aspect) in natal_aspects | events:
                    continue
                found.append(
                    f"事实表里没有{BODY_ZH[source]}与{BODY_ZH[target]}的{ASPECT_ZH[aspect]}；"
                    "相位只写事实表里的编号"
                )
            found += self.date_problems(text, dates, dated)
        found += self.wording_problems(texts, session)
        return list(dict.fromkeys(found))

    @staticmethod
    def date_problems(text: str, dates: set[str], dated: dict) -> list[str]:
        found = []
        for sentence in re.split(r"(?<=[。！？!?；;])|\n", text):
            claims = [
                dated[(source, target, aspect)]
                for _, source, target, aspect in aspect_assertions(sentence)
                if (source, target, aspect) in dated
            ]
            allowed = set().union(*claims) if claims else dates
            for match in DATE.finditer(sentence):
                year, month, day, short_month, short_day = match.groups()
                if year:
                    value = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
                    ok = value in allowed
                else:
                    value = f"{int(short_month):02d}-{int(short_day):02d}"
                    ok = any(d.endswith(value) for d in allowed)
                if ok:
                    continue
                if claims:
                    found.append(
                        f"日期{match[0]}不是同一句里那个相位的精确日期；日期只能通过编号写入"
                    )
                else:
                    found.append(f"日期{match[0]}不在事实表里；日期只能通过编号写入")
        return found

    def reading_problems(self, args, facts, session):
        """The summary's time words and the sections' parts of the month, against the range.

        The summary's first sentence answers the question, so a relative time word in it must
        name a span inside the computed range (这个月 for a question about next month is
        refused; 比起这个月 is a comparison and is not). A section title that names a part of
        a single month (上旬, 月中前后…) may cite only transits whose exact date falls in it;
        前后/左右 widen the part by two days, 以后/以前 extend it to the month's end or start.
        """
        state = session.state
        transit = state.get("transit_result") or {}
        if state.get("astro_question_type") != "timing" or not transit:
            return []
        found = []
        start, end = date.fromisoformat(transit["start"]), date.fromisoformat(transit["end"])
        today = date.fromisoformat(session.calendar_anchor) if session.calendar_anchor else None
        first = re.split(r"[。！？!?]", args.get("summary") or "")[0]
        if today is not None:
            for clause in re.split(r"[，,；;：:]", first):
                if COMPARED.search(clause):
                    continue
                for match in RELATIVE.finditer(clause):
                    low, high = relative_span(match[0], today)
                    if high < start or low > end:
                        found.append(
                            f"摘要第一句写成了“{match[0]}”，这次看的是{transit['start']}至"
                            f"{transit['end']}；按用户说的时间写"
                        )
        if start.year != end.year or start.month != end.month:
            return found
        dated = {}
        for fact in facts:
            if fact.label != "行运相位":
                continue
            event = next(
                (e for e in transit["events"] if f":transit:{e['exact_utc']}:" in fact.ref), None
            )
            if event:
                dated[fact.alias] = int(event["exact_date"][8:10])
        for section in args.get("sections", []):
            title = section.get("title") or ""
            parts = [span for pattern, span in PARTS if pattern.search(title)]
            if not parts:
                continue
            low, high = min(p[0] for p in parts), max(p[1] for p in parts)
            if LATER.search(title):
                high = 31
            if EARLIER.search(title):
                low = 1
            if AROUND.search(title):
                low, high = low - TOLERANCE, high + TOLERANCE
            for alias in section.get("ref_ids", []):
                day = dated.get(alias)
                if day is not None and not low <= day <= high:
                    found.append(
                        f"“{title}”这一层引用了{transit['start'][5:7].lstrip('0')}月{day}日精确的"
                        f"相位{alias}，不在这一段里；按事实表的“时段”分段"
                    )
        return found

    # ---- what code adds ------------------------------------------------------------------

    def note(self, session) -> str:
        state = session.state
        if not state.get("timeframe_default"):
            return ""
        transit = state.get("transit_result") or {}
        place = session.profile.get("birth_place")
        binding = getattr(session, "birth_binding", None) or {}
        location = binding.get("location") or {}
        place = location.get("name") or place
        return requirements.Period(
            transit.get("start", ""), transit.get("end", ""), transit.get("tz", ""), True
        ).note(place)

    def complete(self, args, session):
        """Code says which clock the dates are in when it chose the birth place's (2026-11-07)."""
        note = self.note(session)
        if not note:
            return
        closing = args.get("closing") or ""
        room = 200 - len(note) - 1
        if len(closing) > room:
            closing = closing[: max(0, room - 1)] + "…" if room > 1 else ""
        args["closing"] = f"{closing}\n{note}" if closing else note

    def degraded(self, session, facts, question_type, risk_text, followup, *, safety_only):
        state = session.state
        transit = state.get("transit_result") or {}
        safety = safety_for(risk_text)
        evidence = [{"ref_id": fact.alias} for fact in facts]
        what = (
            f"{transit['start']}至{transit['end']}的星盘行运计算"
            if question_type == "timing" and transit
            else "本命星盘的计算"
        )
        if safety_only:
            args = {
                "question_type": question_type,
                "systems_used": ["astro"],
                "summary": f"这是{what}。这个问题牵涉重大的现实决定，这次不作解读。",
                "sections": [],
                "evidence": evidence,
                "advice": ["先听专业意见：现实中的重要决定，请结合专业人士的意见。"],
                "closing": "",
                "confidence": {"level": "low", "reason": "这次没有给出星盘解读。"},
                "safety": safety if safety["flag"] else {"flag": True, "note": SAFETY_FALLBACK},
            }
        else:
            meanings = {}
            for key in ("natal_result", "transit_result"):
                for item in (state.get(key) or {}).get("interpretations", []):
                    meanings[item["ref_id"]] = item.get("meaning") or {}
            groups = {label: [] for label in SECTION_ORDER}
            for fact in facts:
                groups.setdefault(fact.label, []).append(fact)
            sections = []
            for label, group in groups.items():
                if not group:
                    continue
                sentences = []
                for fact in group:
                    keywords = "、".join(chinese(meanings.get(fact.ref, {}).get("keywords"))[:3])
                    sentences.append(
                        f"{fact.text}，常和{keywords}联系在一起。" if keywords else f"{fact.text}。"
                    )
                sections.append(
                    {
                        "title": label,
                        "body": "".join(sentences)[:1200],
                        "ref_ids": [f.alias for f in group],
                    }
                )
            args = {
                "question_type": question_type,
                "systems_used": ["astro"],
                "summary": f"这是{what}。下面先列出各项依据和一般说法，请当作提示参考。"[:200],
                "sections": sections[:6],
                "evidence": evidence,
                "advice": ["当作提示：对照自己的安排，选一两件事多留意。"],
                "closing": "",
                "confidence": {"level": "low", "reason": "这次只给出了各项的一般说法。"},
                "safety": safety,
            }
        self.complete(args, session)
        return args
