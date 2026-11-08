"""Daily fortune in the pipeline (plan P2.3).

daily_fortune already composes the day by code: the Moon's and the fast planets' exact aspects
to the natal chart, the day pillar with its ten-god relation and its relations to the natal
pillars, a card drawn with a fixed seed, and the day's element; the same user and day reads the
same cached result. The pipeline only writes it up.

By the owner's decision of 2026-11-08 (P3, bazi PR), what the day needs is settled by code, as for
astro and bazi: missing birth data asks for the birth form or is read from the message
(pipeline/birth.py); a missing clock, a Xinjiang birth clock and an overseas birth's solar-time
choice are asked; a timezone or residence the user states is saved as consultation_tz, and one
that names no timezone is asked about; an overseas birth without a stated residence is dated in
the birth place's timezone, and the reading says so. Ranges longer than a day, follow-ups and
corrections of birth data stay with the agent loop.
"""

from __future__ import annotations

import re
from datetime import date as Date
from datetime import datetime
from zoneinfo import ZoneInfo

from common.input_evidence import DATE as BIRTH_DATE
from common.input_evidence import birth_mentions
from common.location import consultation_timezone_evidence
from harness.failures import failure
from harness.refs import short
from pipeline import birth, compose, requirements, verify
from pipeline.factsheet import CAVEAT, Fact, shorten
from pipeline.intent import CONTINUE, Intent
from pipeline.render import safety_for
from pipeline.state import RESUMABLE, snapshot
from pipeline.system import System
from plugins.astro.calculator import BODY_ZH
from plugins.daily.tools import InvalidDate, date_mentions

DAILY = re.compile(
    r"(?:今日|今天|明日|明天|后天|大后天|当天|每日|日)[^，,。？?！!\n]{0,6}?(?:运势|运气|运程)|"
    r"\d{1,2}月\d{1,2}[日号](?:的)?(?:运势|运气)|\d{4}年\d{1,2}月\d{1,2}[日号](?:的)?(?:运势|运气)"
)
# daily_fortune is one day; a week or more is the agent loop's (the tool says so itself).
RANGE = re.compile(r"本周|这周|下周|一周|这个月|本月|下个?月|今年|明年|这几天|最近几天|周末|几天")
OTHER = re.compile(
    r"塔罗|牌阵|抽[一二两三]?张|八字|四柱|命盘|占星|星盘|星座|行运|本命|姓名|名字|五格|"
    r"解梦|梦见|梦到|流年|大运"
)
BIRTH_CORRECTION = re.compile(
    r"(?:出生(?:日期|时间|时刻|地点|资料|信息)|出生信息|出生表单).{0,16}"
    r"(?:更正|改成|改为|记错|不准确|不对|不知道|不清楚|未知|不确定)|"
    r"(?:更正|改成|改为|记错|不准确|不对|不知道|不清楚|未知|不确定).{0,16}"
    r"(?:出生(?:日期|时间|时刻|地点|资料|信息)|出生信息|出生表单)"
)
MULTI_DAY = re.compile(r"分别|各自|每天|每日|逐日|每天都|到|至|—|～|~")
REFERS_TO_READING = re.compile(
    r"(?:上一条|上一次|上次|刚才|之前|前面|那次|原来)(?:那个|这个|那次|那条|的)?"
    r"(?:运势|解读|记录|分析)|原记录|[这那]段解读|(?:你|刚才)(?:说|提到)的"
)
# The web page appends the birth form to the message; the reading keeps the question itself.
BIRTH_NOTE = re.compile(r"\n*我在出生信息表中填写的资料：[^\n]*")
TEN_GODS = ("比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "偏官", "正官", "偏印", "正印")
TEN_GOD = re.compile("|".join(TEN_GODS))
STEMS, BRANCHES = "甲乙丙丁戊己庚辛壬癸", "子丑寅卯辰巳午未申酉戌亥"
JIAZI = re.compile("|".join(STEMS[i % 10] + BRANCHES[i % 12] for i in range(60)))
ASPECT_ZH = {
    "conjunction": "合相",
    "opposition": "对分相",
    "square": "四分相",
    "trine": "三分相",
    "sextile": "六分相",
}
PILLAR_ZH = {"year": "年柱", "month": "月柱", "day": "日柱", "time": "时柱"}
# A hand-written aspect (r7 tomorrow_work#3: 月亮与本命火星、金星的三分相) is a fact like any
# other: the prompt asks for placeholders, and one that is not the day's is refused. Support the
# common aliases and either body order, while retaining lists and the optional 的.
BODY_NAMES = "|".join(BODY_ZH.values())
ASPECT_WORDS = {
    "合相": "conjunction",
    "合": "conjunction",
    "对分": "opposition",
    "对冲": "opposition",
    "冲相": "opposition",
    "冲": "opposition",
    "三分": "trine",
    "拱相": "trine",
    "拱": "trine",
    "四分": "square",
    "刑相": "square",
    "刑": "square",
    "刑克": "square",
    "六分": "sextile",
    "六合": "sextile",
}
ASPECT_ALIASES = "|".join(
    re.escape(word) + ("(?!突)" if word == "冲" else "")
    for word in sorted(ASPECT_WORDS, key=len, reverse=True)
)
ASPECT_BODY = rf"(?:(?:行运|本命)的?)?(?:{BODY_NAMES})"
ASPECT_LEFT = rf"(?P<left_marker>行运|本命)?的?(?P<left>{BODY_NAMES})"
ASPECT_RIGHT = rf"(?P<right>{ASPECT_BODY}(?:(?:、|和|与|及|以及){ASPECT_BODY})*)"
ASPECT_NAME = rf"(?P<aspect>{ASPECT_ALIASES})(?:相)?"
ASPECT_CLAIMS = (
    re.compile(
        rf"{ASPECT_LEFT}(?:与|和|对){ASPECT_RIGHT}"
        rf"(?:之间)?(?:的|形成的?|呈|构成|成)?\s*{ASPECT_NAME}"
    ),
    re.compile(rf"{ASPECT_LEFT}(?:与|和|对)?\s*{ASPECT_NAME}\s*{ASPECT_RIGHT}"),
)
ASPECT_BODY_TOKEN = re.compile(rf"(?P<marker>行运|本命)?的?(?P<body>{BODY_NAMES})")


def daily_aspect_assertions(text: str):
    """Yield (transit body, natal body, aspect) for hand-written daily claims."""
    names = {zh: key for key, zh in BODY_ZH.items()}
    for pattern in ASPECT_CLAIMS:
        for match in pattern.finditer(text):
            left = names[match["left"]]
            # Unmarked daily claims retain the original left-transit convention. Reverse
            # natal-first claims only with an explicit transit marker; otherwise they may
            # describe the natal chart. List roles persist until another marker occurs.
            right_marker = "本命"
            for item in ASPECT_BODY_TOKEN.finditer(match["right"]):
                right_marker = item["marker"] or right_marker
                left_marker = match["left_marker"] or ("本命" if right_marker == "行运" else "行运")
                if left_marker == right_marker:
                    continue  # Natal–natal and transit–transit are not daily events.
                right = names[item["body"]]
                transit, natal = (right, left) if left_marker == "本命" else (left, right)
                yield transit, natal, ASPECT_WORDS[match["aspect"]]


CONVENTIONS = {
    "daily_seed": "每日一牌的抽法",
    "no_exact_events": "当天没有精确相位",
    "unknown_time": "出生时间未知",
}
SAFETY_FALLBACK = "这类问题牵涉重大的现实决定，请结合专业意见再做判断。"
# A run asks at most three times: typed birth data may need its place and clock, then an
# overseas birth's solar-time choice.
MAX_ASKS = 3
ASK_CLOCK = (
    "每日运势需要出生时间：请把出生日期和时间一起再说一遍，例如“1990年3月5日早上8点”；"
    "不知道时间就说“不知道出生时间”。"
)
ASK_XINJIANG = "请确认出生钟表时间使用北京时间还是新疆时间。"
ASK_TIMEZONE = "今天按哪个城市的时间来看？可以说“按北京时间”，或“按纽约时间”。"
SECTION_ORDER = ("流日", "流日（换日后）", "流日与本命", "当天的相位", "每日一牌", "流日五行")


def chinese(keywords) -> list[str]:
    """Keywords a reader can read: the aspects' entries carry English keys among them."""
    return [k for k in keywords or [] if re.search(r"[\u4e00-\u9fff]", k)]


class Daily(System):
    name = "daily"
    kept = "当天的计算结果"
    birth_form = (
        "看每日运势需要出生日期、时间和地点：请在页面上的出生信息表里补全"
        "（时间不知道可以选未知），填好后发送“继续”。也可以直接告诉我，例如"
        "“我1990年3月5日早上8点出生在杭州”。"
    )

    # ---- ① intent ------------------------------------------------------------------------

    def detect(self, runtime, message):
        from pipeline.astro import BIRTH_MENTION, Astro, typed_birth_usable

        session = runtime.session
        selected = session.state.get("selected_systems")
        if selected not in (None, ["daily"]) or session.pinned_reading_id:
            return None
        question = self.question(message)
        run = runtime.store.unfinished_pipeline_run(session.user_id)
        if run and run["state"].get("system") == "daily" and run["stage"] == "awaiting_input":
            if not Astro.answering(session, run):
                runtime.store.finish_pipeline_run(run["run_id"])
                run = None
        if run and run["state"].get("system") == "daily":
            if run["stage"] == "awaiting_input":
                needs = run["state"].get("needs")
                handed = (
                    (selected is None and OTHER.search(question))
                    or run["state"].get("asks", 0) >= MAX_ASKS
                    or (
                        BIRTH_MENTION.search(question)
                        and needs not in ("birth", "missing_birth_time")
                    )
                    or (
                        needs == "birth"
                        and not requirements.birth_ready(session)
                        and not typed_birth_usable(question, session)
                    )
                )
                if handed:
                    runtime.store.finish_pipeline_run(run["run_id"])
                    return None
                return Intent("daily", "input", run=run)
            if run["stage"] in RESUMABLE and (
                CONTINUE.search(message) or question == run["state"]["question"].strip()
            ):
                return Intent("daily", "resume", run=run)
        if selected is None and (OTHER.search(question) or not DAILY.search(question)):
            return None
        if RANGE.search(question) or REFERS_TO_READING.search(question):
            return None
        unknown_time = re.search(
            r"(?:不知道|不清楚|未知|不确定).{0,8}出生时间|出生时间.{0,8}(?:不知道|不清楚|未知|不确定)",
            question,
        )
        if BIRTH_CORRECTION.search(question) and not (
            session.profile.get("time_known") is False and unknown_time
        ):
            return None
        mentions = date_mentions(
            question,
            Date.fromisoformat(session.calendar_anchor) if session.calendar_anchor else None,
            str(session.profile.get("birth_local_dt") or "")[:10] or None,
        )
        if MULTI_DAY.search(question) and (
            len(mentions) > 1 or re.search(r"每天|每日|逐日", question)
        ):
            return None
        if not DAILY.search(question) and self.saved_daily(runtime):
            return None
        if BIRTH_MENTION.search(question) and not typed_birth_usable(question, session):
            return None  # a birth without a full date, or one that corrects the saved birth
        if not requirements.birth_ready(session) and (
            re.search(BIRTH_DATE, question) or re.search(r"出生|生于", question)
        ):
            if not typed_birth_usable(question, session):
                return None
        if self.target(session, question) is None:
            return None  # a day that does not exist: the agent loop asks which one
        return Intent("daily", "new")

    def question(self, message):
        return BIRTH_NOTE.sub("", message).strip() or message

    @staticmethod
    def saved_daily(runtime) -> bool:
        session, store = runtime.session, runtime.store
        state = session.state
        candidates = []
        if state.get("complete") and state.get("active_reading_id"):
            candidates.append(state["active_reading_id"])
        candidates += [row["reading_id"] for row in store.recent_readings(session.user_id, limit=1)]
        for reading_id in candidates:
            saved = store.get_reading(session.user_id, reading_id)
            if saved:
                return saved.get("systems_used") == ["daily"]
        return False

    def target(self, session, question: str) -> str | None:
        """The day asked about, read as daily_fortune's own validator reads it."""
        anchor = Date.fromisoformat(session.calendar_anchor) if session.calendar_anchor else None
        birth = str(session.profile.get("birth_local_dt") or "")[:10] or None
        mentions = date_mentions(question, anchor, birth)
        if any(isinstance(mention, InvalidDate) for mention in mentions):
            return None
        if mentions:
            return mentions[-1]
        return anchor.isoformat() if anchor else None

    # ---- ② requirements and ③ compute (plan P3.1, owner 2026-11-08) ---------------------

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
        if not (run.reading_id and session.state.get("active_reading_id") == run.reading_id):
            results, _ = await runner.planned(
                [("start_reading", {"question": run.question, "systems": ["daily"]})]
            )
            if not results[0]["ok"]:
                error = results[0]
                return failure(session, "tool_error", error.get("code"), error["error"])
            run.reading_id = session.state["active_reading_id"]
        stopped = await self.birth_data(runner, run)
        if stopped is not None:
            return stopped
        stopped = await self.consultation_timezone(runner, run)
        if stopped is not None:
            return stopped
        day = self.target(session, run.question)
        if day is None:
            return failure(session, "tool_error", "invalid_date", "用户给出的日期不存在")
        results, _ = await runner.planned([("daily_fortune", {"date": day})])
        if not results[0]["ok"]:
            error = results[0]
            return failure(session, "tool_error", error.get("code"), error["error"])
        data = results[0]["data"]
        if data.get("status") == "needs_input":
            code = data.get("code") or "input"
            question = (
                ASK_CLOCK
                if code in ("missing_birth_time", "uncertain_day_master")
                else (data["question"])
            )
            needs = "missing_birth_time" if question is ASK_CLOCK else code
            return await self.ask(runner, run, question, needs)
        if session.state.get("daily_tz_default") and data.get("tz") != session.profile.get("tz"):
            session.state["daily_tz_default"] = False
        return None

    async def birth_data(self, runner, run):
        """Birth data from the profile, the message (pipeline.birth) or an answer, saved by
        planned update_profile and resolve_location calls; daily_fortune reads the profile."""
        session = runner.session
        answer = session.user_messages[-1] if session.user_messages else ""
        if run.needs == "missing_birth_time":
            saved = str(session.profile.get("birth_local_dt") or "")
            mentions = birth_mentions(answer)
            precise = [(day, clock) for day, clock in mentions if clock and day == saved[:10]]
            if precise:
                day, clock = precise[0]
                await runner.planned(
                    [
                        (
                            "update_profile",
                            {
                                "field": "birth_local_dt",
                                "value": f"{day} {clock}",
                                "evidence": answer,
                            },
                        )
                    ]
                )
            elif birth.UNKNOWN_TIME.search(answer):
                await runner.planned(
                    [
                        (
                            "update_profile",
                            {"field": "time_known", "value": False, "evidence": answer},
                        )
                    ]
                )
        if run.needs == "xinjiang_clock":
            # resolve_location saves the birth clock once the user has named it.
            await runner.planned(
                [("resolve_location", {"query": session.profile.get("birth_place") or ""})]
            )
        if requirements.birth_ready(session):
            return None
        if not birth.bound(session):
            stopped = await birth.bind(self, runner, run)
            if stopped is not None:
                return stopped
        if requirements.birth_ready(session):
            return None
        locations = list(session.state.get("locations", {}).values())
        if (
            session.profile.get("birth_place")
            and len(locations) == 1
            and locations[0]["tz"] == "Asia/Urumqi"
            and not session.profile.get("tz")
        ):
            return await self.ask(runner, run, ASK_XINJIANG, "xinjiang_clock")
        return await self.ask(runner, run, self.birth_form, "birth")

    async def consultation_timezone(self, runner, run):
        """The timezone the day is dated in (owner, 2026-11-08, as astro_timing on 2026-11-07).

        A timezone or residence the user states is saved as consultation_tz, which also dates
        “今天”; a residence that does not name a timezone is asked about; an overseas birth
        without a stated residence keeps the birth place's timezone, and the reading says so.
        """
        session = runner.session
        profile = session.profile
        birth_tz = profile.get("tz")
        index = session.state.get("question_message_index", 0)
        texts = [
            requirements.strip_birth_note(text)
            for text in (
                session.user_messages[index:] if index >= 0 else session.user_messages[-1:]
            )
        ]
        if run.needs == "timezone":
            city = re.search(
                r"(?:按|用)\s*(?P<city>[\u4e00-\u9fff]{2,8}?)(?:的)?(?:当地)?时间", texts[-1]
            )
            if city and city["city"] not in ("北京", "当地", "出生地"):
                await runner.planned([("resolve_location", {"query": city["city"]})])
        stated = None
        for text in texts:
            found = consultation_timezone_evidence(text, session, birth_tz)
            if found:
                stated = (found, text)
        if stated and stated[0] != profile.get("consultation_tz"):
            value, evidence = stated
            results, _ = await runner.planned(
                [
                    (
                        "update_profile",
                        {"field": "consultation_tz", "value": value, "evidence": evidence},
                    )
                ]
            )
            if not results[0]["ok"]:
                return await self.ask(runner, run, ASK_TIMEZONE, "timezone")
            return None
        if stated or profile.get("consultation_tz"):
            return None
        if any(requirements.RESIDENCE.search(text) for text in texts):
            return await self.ask(runner, run, ASK_TIMEZONE, "timezone")
        session.state["daily_tz_default"] = requirements.overseas(birth_tz)
        return None

    # ---- ④ fact sheet --------------------------------------------------------------------

    @staticmethod
    def result(state) -> dict:
        return state.get("daily_result") or {}

    def facts(self, session):
        state = session.state
        result = self.result(state)
        texts = self.texts(result)
        facts = []
        for item in result.get("interpretations", []):
            if item["ref_id"] not in state.get("allowed_refs", ()):
                continue
            label, text = texts.get(item["fact"], ("约定", CONVENTIONS.get(item["key"], "约定")))
            alias = short(item["ref_id"], session)
            meaning = item.get("meaning") or {}
            keywords = "、".join(chinese(meaning.get("keywords"))[:6])
            general = shorten(CAVEAT.sub("", meaning.get("text") or ""), 140)
            line = (
                f"{alias}｜{label}｜{text}｜关键词：{keywords or '无'}｜一般含义：{general or '无'}"
            )
            facts.append(Fact(alias, item["ref_id"], label, text, line))
        return facts

    @staticmethod
    def texts(result: dict) -> dict[str, tuple[str, str]]:
        """fact → (where it sits on the fact sheet, the text code renders for it)."""
        tz = ZoneInfo(result["tz"])
        out = {}
        segments = result["day"]["segments"]
        main = result["day"]["pillar"]
        for segment in segments:
            local = datetime.fromisoformat(segment["start_utc"]).astimezone(tz)
            end = datetime.fromisoformat(segment["end_utc"]).astimezone(tz)
            until = "24:00" if end.date() > local.date() else f"{end:%H:%M}"
            interval = f"{local:%H:%M}–{until}，{result['tz']}"
            late = segment["pillar"] != main
            prefix = f"{local:%H:%M}后的流日" if late else "流日"
            fact = f"day:{segment['start_utc']}:{segment['pillar']}:{segment['ten_god']}"
            out[fact] = (
                "流日（换日后）" if late else "流日",
                f"{prefix}{segment['pillar']}（十神{segment['ten_god']}）（仅{interval}）",
            )
        natal = result["bazi"]["pillars"]
        for item in result["interpretations"]:
            fact = item["fact"]
            if item["kind"] == "relation" and fact.startswith("day:"):
                # The segment's start is an ISO instant with colons of its own.
                segment_fact, pillar, kind, where = fact.rsplit(":", 3)
                where = where if where in PILLAR_ZH else None
                against = f"本命{PILLAR_ZH[where]}{natal.get(where) or ''}" if where else "本命"
                # Relations belong to a segment too; the late segment is not the whole evening.
                segment = next(s for s in segments if segment_fact == f"day:{s['start_utc']}")
                start = datetime.fromisoformat(segment["start_utc"]).astimezone(tz)
                end = datetime.fromisoformat(segment["end_utc"]).astimezone(tz)
                until = "24:00" if end.date() > start.date() else f"{end:%H:%M}"
                pair = ""
                if where and natal.get(where):
                    index = 0 if kind.startswith("天干") else 1
                    part = "天干" if index == 0 else "地支"
                    pair = f"，{part}{pillar[index]}与{natal[where][index]}"
                out[fact] = (
                    "流日与本命",
                    f"流日{pillar}与{against}{kind}（仅{start:%H:%M}–{until}，{result['tz']}{pair}）",
                )
            elif item["kind"] == "aspect":
                *_, body, natal_body, aspect = fact.split(":")
                text = f"月亮与本命{BODY_ZH[natal_body]}{ASPECT_ZH[aspect]}"
                if body != "Moon":
                    text = f"行运{BODY_ZH[body]}与本命{BODY_ZH[natal_body]}{ASPECT_ZH[aspect]}"
                out[fact] = ("当天的相位", text)
        card = result["card"]
        out[f"card:{card['card_id']}:{card['meaning_key'].split(':')[1]}"] = (
            "每日一牌",
            f"【{card['name']}】{'逆位' if card['reversed'] else '正位'}",
        )
        out[f"day_element:{result['day']['element']}"] = (
            "流日五行",
            f"流日天干五行{result['day']['element']}",
        )
        return out

    # ---- ⑤ compose -----------------------------------------------------------------------

    def messages(self, run, facts, session, *, prior=None, extra=""):
        result = self.result(session.state)
        context = [
            f"日期：{result['date']}（{result['tz']}）",
            f"本命日主：{result['bazi']['day_master']}",
            "时间口径：事实表的流日及其干支关系仅适用于标明的当地时段；"
            "23点换日不等于入夜，23:00–24:00仅为当天最后一小时。"
            "相位精确时刻是计算时刻，不是现实事件或心情转折的时刻。",
        ]
        return compose.daily_messages(run.question, context, facts, extra=extra)

    def question_type(self, run, session, followup):
        return "daily"

    # ---- ⑥ verify ------------------------------------------------------------------------

    def problems(self, texts, session):
        """The day's closed vocabulary (plan P2.4) and the shared wording rules.

        A ten-god name must be one of the day's; a stem-branch pair one of the day's or the
        natal pillars; a card the day's card in its orientation. The output validators catch
        a wrong day pillar or card already; a wrong ten god they let through (P0.2).
        """
        result = self.result(session.state)
        gods = list(dict.fromkeys(s["ten_god"] for s in result["day"]["segments"]))
        pillars = {s["pillar"] for s in result["day"]["segments"]}
        pillars |= {p for p in result["bazi"]["pillars"].values() if p}
        found = []
        for text in texts:
            found += self.fact_claim_problems(text, result)
            for match in TEN_GOD.finditer(text):
                if match[0] not in gods:
                    found.append(f"当天流日的十神是{'、'.join(gods)}，正文写成了{match[0]}")
            for match in JIAZI.finditer(text):
                if match[0] not in pillars:
                    found.append(f"{match[0]}不是当天的流日，也不是本命的干支")
        found += verify.tarot_problems(texts, [result["card"]])
        found += self.wording_problems(texts, session)
        return list(dict.fromkeys(found))

    @staticmethod
    def fact_claim_problems(text: str, result: dict) -> list[str]:
        """Check explicit daily-only facts that are not represented by stem/card mentions."""
        found = []
        master = result["bazi"]["day_master"]
        for match in re.finditer(r"日主(?:是|为|：|:)?\s*([甲乙丙丁戊己庚辛壬癸])", text):
            if match[1] != master[0]:
                found.append(f"本命日主是{master[0]}，正文写成了{match[1]}")

        element = result["day"]["element"]
        for match in re.finditer(r"(?:流日天干)?五行(?:属|为|：|:)?\s*([金木水火土])", text):
            if match[1] != element:
                found.append(f"当天流日五行是{element}，正文写成了{match[1]}")

        events = {(e["transit_body"], e["natal_body"], e["aspect"]) for e in result["events"]}
        for transit, natal, aspect in daily_aspect_assertions(text):
            if (transit, natal, aspect) not in events:
                found.append(
                    f"当天没有{BODY_ZH[transit]}与本命{BODY_ZH[natal]}的{ASPECT_ZH[aspect]}；相位只写事实表里的编号"
                )

        for match in re.finditer(r"(?<!\d)(\d{4})年(\d{1,2})月(\d{1,2})[日号]?", text):
            context = text[max(0, match.start() - 12) : match.end() + 8]
            if not re.search(r"今天|今日|当日|当天|日期|运势|解读|流日", context):
                continue
            value = f"{int(match[1]):04d}-{int(match[2]):02d}-{int(match[3]):02d}"
            if value != result["date"]:
                found.append(f"当天日期是{result['date']}，正文写成了{value}")
        return found

    # ---- readings written by code --------------------------------------------------------

    def note(self, session) -> str:
        """Which clock dated the day, when code chose the birth place's (owner, 2026-11-08)."""
        state = session.state
        result = self.result(state)
        if not state.get("daily_tz_default") or not result:
            return ""
        binding = getattr(session, "birth_binding", None) or {}
        place = (binding.get("location") or {}).get("name") or session.profile.get("birth_place")
        return requirements.Period(result["date"], result["date"], result["tz"], True).note(place)

    def complete(self, args, session):
        note = self.note(session)
        if not note:
            return
        closing = args.get("closing") or ""
        room = 200 - len(note) - 1
        if len(closing) > room:
            closing = closing[: max(0, room - 1)] + "…" if room > 1 else ""
        args["closing"] = f"{closing}\n{note}" if closing else note

    def degraded(self, session, facts, question_type, risk_text, followup, *, safety_only):
        result = self.result(session.state)
        safety = safety_for(risk_text)
        evidence = [{"ref_id": fact.alias} for fact in facts]
        if safety_only:
            args = {
                "question_type": question_type,
                "systems_used": ["daily"],
                "summary": f"这是{result['date']}的运势计算。这个问题牵涉重大的现实决定，这次不作解读。",
                "sections": [],
                "evidence": evidence,
                "advice": ["先听专业意见：现实中的重要决定，请结合专业人士的意见。"],
                "closing": "",
                "confidence": {"level": "low", "reason": "这次没有给出运势解读。"},
                "safety": safety if safety["flag"] else {"flag": True, "note": SAFETY_FALLBACK},
            }
            self.complete(args, session)
            return args
        meanings = {item["ref_id"]: item.get("meaning") or {} for item in result["interpretations"]}
        groups = {label: [] for label in SECTION_ORDER}
        for fact in facts:
            if fact.label != "约定":
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
            "systems_used": ["daily"],
            "summary": f"这是{result['date']}的运势计算。下面先列出当天的各项依据和一般说法，请当作当天的提示参考。"[
                :200
            ],
            "sections": sections[:6],
            "evidence": evidence,
            "advice": ["当作提示：对照当天的安排，选一两件事多留意。"],
            "closing": "",
            "confidence": {"level": "low", "reason": "这次只给出了各项的一般说法。"},
            "safety": safety,
        }
        self.complete(args, session)
        return args
