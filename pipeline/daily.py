"""Daily fortune in the pipeline (plan P2.3).

daily_fortune already composes the day by code: the Moon's and the fast planets' exact aspects
to the natal chart, the day pillar with its ten-god relation and its relations to the natal
pillars, a card drawn with a fixed seed, and the day's element; the same user and day reads the
same cached result. The pipeline only writes it up.

By the owner's decision (P2), the pipeline takes a daily question only when the profile already
holds birth data the calculation can use as it is. Missing or unconfirmed data (no birth date or
place, an overseas birth whose true solar time is not settled, a consultation timezone stated
in the message or differing from the calendar's) and ranges longer than a day stay with the
agent loop, which asks and saves; P3's requirements stage moves that into code.
"""

from __future__ import annotations

import re
from datetime import date as Date
from datetime import datetime
from zoneinfo import ZoneInfo

from common.location import consultation_timezone_evidence
from common.time_utils import NeedsInput
from harness.failures import failure
from harness.refs import short
from harness.session import profile_timezone
from pipeline import compose, verify
from pipeline.factsheet import CAVEAT, Fact, shorten
from pipeline.intent import CONTINUE, Intent
from pipeline.render import safety_for
from pipeline.state import RESUMABLE
from pipeline.system import System
from plugins.astro.calculator import BODY_ZH
from plugins.daily.tools import DailyInput, InvalidDate, date_mentions

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
# The consultation timezone is a confirmation the agent loop saves before the day is dated.
TIMEZONE = re.compile(
    r"时区|UTC|GMT|当地时间|北京时间|按.{0,8}时间|在国外|现居|现在住在|我在[^，。]{0,6}(?:国|市|州)"
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
CONVENTIONS = {
    "daily_seed": "每日一牌的抽法",
    "no_exact_events": "当天没有精确相位",
    "unknown_time": "出生时间未知",
}
SAFETY_FALLBACK = "这类问题牵涉重大的现实决定，请结合专业意见再做判断。"
SECTION_ORDER = ("流日", "流日（换日后）", "流日与本命", "当天的相位", "每日一牌", "流日五行")


def chinese(keywords) -> list[str]:
    """Keywords a reader can read: the aspects' entries carry English keys among them."""
    return [k for k in keywords or [] if re.search(r"[\u4e00-\u9fff]", k)]


class Daily(System):
    name = "daily"
    kept = "当天的计算结果"

    # ---- ① intent ------------------------------------------------------------------------

    def detect(self, runtime, message):
        session = runtime.session
        selected = session.state.get("selected_systems")
        if selected not in (None, ["daily"]) or session.pinned_reading_id:
            return None
        run = runtime.store.unfinished_pipeline_run(session.user_id)
        if (
            run
            and run["stage"] in RESUMABLE
            and run["state"].get("system") == "daily"
            and (CONTINUE.search(message) or message.strip() == run["state"]["question"].strip())
        ):
            return Intent("daily", "resume", run=run)
        question = self.question(message)
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
        return Intent("daily", "new") if self.ready(runtime, question) else None

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

    def ready(self, runtime, question: str) -> bool:
        """Whether the calculation can run on the profile as it is, without asking anything."""
        session = runtime.session
        if TIMEZONE.search(question) or self.target(session, question) is None:
            return False
        if any(
            consultation_timezone_evidence(text, session, session.profile.get("tz"))
            for text in (question,)
        ):
            return False
        if not session.profile.get("birth_local_dt"):
            return False
        try:
            birth, _ = runtime.plugins["daily"].inputs(DailyInput(date="2000-01-01"), session)
        except NeedsInput:
            return False
        # The day is dated in the calendar's timezone and computed in the profile's; they agree
        # unless a consultation timezone is pending, which the agent loop confirms and saves.
        return (profile_timezone(session.profile) or birth["tz"]) == session.calendar_timezone

    # ---- ③ compute -----------------------------------------------------------------------

    async def compute(self, runner, run):
        session = runner.session
        day = self.target(session, run.question)
        results, _ = await runner.planned(
            [
                ("start_reading", {"question": run.question, "systems": ["daily"]}),
                ("daily_fortune", {"date": day}),
            ]
        )
        error = next((r for r in results if not r["ok"]), None)
        if error is not None:
            return failure(session, "tool_error", error.get("code"), error["error"])
        data = results[1]["data"]
        if data.get("status") == "needs_input":
            _, terminal = await runner.planned([("ask_user", {"question": data["question"]})])
            return terminal or failure(session, "tool_error", "ask_failed", data["question"])
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

        for match in re.finditer(r"(?<!\d)(\d{4})年(\d{1,2})月(\d{1,2})[日号]?", text):
            context = text[max(0, match.start() - 12) : match.end() + 8]
            if not re.search(r"今天|今日|当日|当天|日期|运势|解读|流日", context):
                continue
            value = f"{int(match[1]):04d}-{int(match[2]):02d}-{int(match[3]):02d}"
            if value != result["date"]:
                found.append(f"当天日期是{result['date']}，正文写成了{value}")
        return found

    # ---- readings written by code --------------------------------------------------------

    def degraded(self, session, facts, question_type, risk_text, followup, *, safety_only):
        result = self.result(session.state)
        safety = safety_for(risk_text)
        evidence = [{"ref_id": fact.alias} for fact in facts]
        if safety_only:
            return {
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
        return {
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
