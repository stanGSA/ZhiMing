"""Name analysis in the pipeline (plan P2.2).

The names come from the user's own words, letter by letter: code reads them from quotes and
the usual phrasings ("看看张伟这个名字", "叫王小明", "名字：欧阳子涵"), or the profile's name
for "我的名字"; one model call without tools (plan §3.4) is made only when code finds none.
Every name is checked as analyze_name's own validator checks it, compound surnames included,
and each of at most two names is calculated once. The grids, their numbers and the 三才
configuration reach the reader only through placeholders; a character with several written
forms is computed with its default form and code asks the user, in the advice, to confirm.
"""

from __future__ import annotations

import json
import re

from harness.failures import failure
from harness.refs import short
from pipeline import compose
from pipeline.factsheet import Fact, shorten
from pipeline.intent import CONTINUE, Intent
from pipeline.render import safety_for
from pipeline.state import RESUMABLE
from pipeline.system import System
from plugins.name.input_evidence import ORIGINAL_FORM, single_surname
from plugins.name.tools import HAN, NameInput, NamePlugin
from plugins.name.validation import FATALISM, check_claims, name_results
from plugins.name.wuge import COMPOUND_SURNAMES

NAME = re.compile(r"名字|姓名|五格|三才|笔画|数理")
# Naming a child, renaming and marriage matching are outside the name feature (domain rules).
OUT_OF_SCOPE = re.compile(r"起名|取名|改名|合婚|配对")
OTHER = re.compile(
    r"塔罗|牌阵|抽[一二两三]?张|[一二两三单]张牌|八字|四柱|命盘|占星|星盘|星座|行运|本命|"
    r"解梦|梦见|梦到|梦境|做梦|噩梦|运势|流日|流年|大运"
)
# A written form the user states (原字, 繁体, 写作…) is a confirmation analyze_name needs as
# ``forms``; the agent loop handles it until P3 moves confirmations into code.
FORMS = re.compile(
    rf"{ORIGINAL_FORM.pattern}|繁体|异体|写作|写成|证件上|(?:用|按|计|算).{{0,8}}[\d一二三四五六七八九十]+画"
)
REFERS_TO_READING = re.compile(
    r"(?:上一条|上一次|上次|刚才|之前|前面|那次|原来)(?:那个|这个|那次|那条|的)?"
    r"(?:名字|姓名|解读|记录|分析)|原记录|[这那]段解读|(?:你|刚才)(?:说|提到)的"
)
OWN_NAME = re.compile(r"我的名字|我名字|我的姓名|本人(?:的)?名字")
QUOTED = re.compile(rf"[“\"「『《]({HAN}{{2,4}})[”\"」』》]")
END = r"(?=这个名字|这个姓名|这名字|的名字|的姓名|这两个|[一二三四五六七八九十\d]+个名字|哪个|和|与|跟|、|还是|[，,。？?！!\s]|$)"
LEAD = (
    r"看看|看一下|看下|分析一下|分析|算算|算一下|测测|测一下|评估一下|评估|比较一下|比较|"
    r"对比一下|对比|评一下|请问|叫做|名叫|叫|名字是|姓名是|名字为|姓名为|名字[：:]|姓名[：:]"
)
INTRODUCED = re.compile(rf"(?:{LEAD}|^)({HAN}{{2,4}}?){END}")
# What may stand right before a name: the start, punctuation, a lead-in or a conjunction.
BEFORE_NAME = re.compile(rf"(?:^|[^㐀-䶿一-鿿豈-﫿]|{LEAD}|是|为|和|与|跟|还是)$")
SECOND = re.compile(rf"(?:和|与|跟|、|还是)({HAN}{{2,4}}?){END}")
# Code reads names conservatively: a pronoun, a demonstrative, a question word, a particle or
# a request verb means the phrasing was misread (“看看我的名字” is not 看看我), and a name it
# cannot read is left to the model call.
NOT_A_NAME = re.compile(
    r"[我你您他她它这那哪谁么的了吗呢吧啊看析算测评叫问帮请]|名字|姓名|一下|两个"
)
# Common single surnames. A name code reads without quotes must start with one of them or with
# a compound surname; anything else (“想知道这个名字”, “小明”) goes to the model call.
SURNAMES = frozenset(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶"
    "程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付傅方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺"
    "顾毛郝龚邵万钱严覃武戴莫孔向汤常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹申欧耿"
    "关兰焦俞左柳甘祝包宁尚符舒阮柯纪梅童凌毕单季裴霍涂成苗谷盛曲翁冉骆蓝路游辛靳管柴蒙鲍华"
    "喻祁蒲房滕屈饶解牟艾尤阳时穆农司卓古吉缪简车项连芦麦褚娄窦戚岑景党宫费卜冷晏席卫米柏宗"
    "瞿桂全佟应臧闵苟邬边卞姬师和仇栾隋商刁沙荣巫寇桑郎甄丛仲虞敖巩明佘池查麻苑迟邝"
)
# “李一和这个名字”: a name right before 这个名字 is read as the longest one that is a name.
ANCHOR = re.compile(r"这个名字|这个姓名|这名字|的名字|的姓名")
MAX_NAMES = 2
NO_NAME = "请告诉我要分析的完整姓名（姓和名），例如“张伟”；比较两个名字时请把两个都写出来。"
TOO_MANY = "一次最多比较两个名字，请告诉我想先看哪两个。"
CONFIRM = "确认写法"
SAFETY_FALLBACK = "这类问题牵涉重大的现实决定，请结合专业意见再做判断。"
COMPARE = re.compile(r"比较|对比|两个名字|这两个")


def split(full: str, text: str) -> tuple[str, str]:
    """(surname, given): a known compound surname unless the user says it is a single one."""
    if len(full) >= 3 and full[:2] in COMPOUND_SURNAMES and not single_surname(full, [text]):
        return full[:2], full[2:]
    return full[0], full[1:]


class Name(System):
    name = "name"
    kept = "姓名计算结果"

    # ---- ① intent ------------------------------------------------------------------------

    def detect(self, runtime, message):
        session = runtime.session
        selected = session.state.get("selected_systems")
        if selected not in (None, ["name"]) or session.pinned_reading_id:
            return None
        run = runtime.store.unfinished_pipeline_run(session.user_id)
        if (
            run
            and run["stage"] in RESUMABLE
            and run["state"].get("system") == "name"
            and (CONTINUE.search(message) or message.strip() == run["state"]["question"].strip())
        ):
            return Intent("name", "resume", run=run)
        if selected is None and (OTHER.search(message) or not NAME.search(message)):
            return None
        if OUT_OF_SCOPE.search(message) or FORMS.search(message):
            return None
        if REFERS_TO_READING.search(message):
            return None
        if not self.code_names(message, session.profile) and self.saved_name(runtime):
            # A message without a name of its own after a name reading asks about that one.
            return None
        return Intent("name", "new")

    @staticmethod
    def saved_name(runtime) -> bool:
        session, store = runtime.session, runtime.store
        state = session.state
        candidates = []
        if state.get("complete") and state.get("active_reading_id"):
            candidates.append(state["active_reading_id"])
        candidates += [row["reading_id"] for row in store.recent_readings(session.user_id, limit=1)]
        for reading_id in candidates:
            saved = store.get_reading(session.user_id, reading_id)
            if saved:
                return saved.get("systems_used") == ["name"]
        return False

    @staticmethod
    def code_names(text: str, profile: dict) -> list[str]:
        """Full names code reads from the message, in order; the profile's for “我的名字”.

        Merge quoted names, anchors and lead-ins in source order. Longest overlapping
        candidates win (李一和 is not 李一); quotes around a term or nickname are not names.
        """

        def plausible(name: str) -> bool:
            return bool(
                re.fullmatch(f"{HAN}{{2,4}}", name)
                and not NOT_A_NAME.search(name)
                and (name[0] in SURNAMES or name[:2] in COMPOUND_SURNAMES)
            )

        candidates = []
        excluded = []
        for match in QUOTED.finditer(text):
            before = text[: match.start()]
            if re.search(r"(?:称呼我|叫我|昵称(?:是|叫)?|小名(?:是|叫)?)[：:\s]*$", before):
                excluded.append(match.span(1))
            elif plausible(match[1]):
                candidates.append((*match.span(1), match[1]))
        # Keep offsets while letting both quoted and unquoted names use the same grammar.
        scanned = re.sub(r'[“”"「」『』《》]', " ", text)
        for anchor in ANCHOR.finditer(text):
            for size in (4, 3, 2):
                start = anchor.start() - size
                if start >= 0 and plausible(text[start : anchor.start()]):
                    if BEFORE_NAME.search(text[:start]):
                        candidates.append((start, anchor.start(), text[start : anchor.start()]))
                        break
        for pattern in (INTRODUCED, SECOND):
            for match in pattern.finditer(scanned):
                if plausible(match[1]):
                    candidates.append((*match.span(1), match[1]))
        kept = []
        for start, end, name in sorted(candidates, key=lambda c: (-(c[1] - c[0]), c[0])):
            if any(start < stop and end > begin for begin, stop in excluded):
                continue
            if not any(start < stop and end > begin for begin, stop, _ in kept):
                kept.append((start, end, name))
        found = [name for _, _, name in sorted(kept)]
        if not found and OWN_NAME.search(text) and profile.get("name"):
            found.append(profile["name"])
        return list(dict.fromkeys(found))

    def accepted(self, names, session) -> list[dict]:
        """Names analyze_name's own validator accepts, as its arguments."""
        kept = []
        for full in names:
            if not isinstance(full, str) or not re.fullmatch(f"{HAN}{{2,5}}", full):
                continue
            current = next((text for text in reversed(session.user_messages) if full in text), "")
            surname, given = split(full, current)
            try:
                args = NameInput(surname=surname, given=given)
            except ValueError:
                continue
            if (
                NamePlugin.validate(args, session) is None
                and {
                    "surname": surname,
                    "given": given,
                }
                not in kept
            ):
                kept.append({"surname": surname, "given": given})
        return kept

    async def extract(self, runner, run) -> tuple[list[dict], str]:
        from pipeline.runner import OutOfBudget

        session = runner.session
        found = self.accepted(self.code_names(run.question, session.profile), session)
        if found:
            return found, "code"
        try:
            text, truncated = await runner.ask(
                compose.name_extract_messages(run.question), "intent", run
            )
        except OutOfBudget:
            return [], "code"
        if truncated:
            return [], "model"
        try:
            items = json.loads(compose.json_object(text)).get("names")
        except (ValueError, AttributeError):
            return [], "model"
        if not isinstance(items, list):
            return [], "model"
        return self.accepted([str(item) for item in items], session), "model"

    # ---- ③ compute -----------------------------------------------------------------------

    async def compute(self, runner, run):
        from pipeline.runner import Stopped

        try:
            names, source = await self.extract(runner, run)
        except Stopped as stop:
            return stop.outcome
        runner.stage("extract", run_id=run.run_id, source=source, names=len(names))
        if len(names) > MAX_NAMES:
            return await self.ask(runner, TOO_MANY)
        if not names or (len(names) < 2 and COMPARE.search(run.question)):
            return await self.ask(runner, NO_NAME)
        results, _ = await runner.planned(
            [
                ("start_reading", {"question": run.question, "systems": ["name"]}),
                *(("analyze_name", name) for name in names),
            ]
        )
        error = next((r for r in results if not r["ok"]), None)
        if error is not None:
            return failure(runner.session, "tool_error", error.get("code"), error["error"])
        pending = next(
            (r["data"] for r in results[1:] if r["data"].get("status") == "needs_input"), None
        )
        if pending is not None:
            # A character with no known stroke count: never guessed, the user is asked.
            return await self.ask(runner, pending["question"])
        return None

    @staticmethod
    async def ask(runner, question: str):
        _, terminal = await runner.planned([("ask_user", {"question": question})])
        return terminal or failure(runner.session, "tool_error", "ask_failed", question)

    # ---- ④ fact sheet --------------------------------------------------------------------

    @staticmethod
    def results(state) -> list[dict]:
        return list(name_results(state).values())

    def facts(self, session):
        state = session.state
        results = self.results(state)
        several = len(results) > 1
        facts = []
        for result in results:
            owner = f"{result['full_name']}的" if several else ""
            for item in result["interpretations"]:
                if item["ref_id"] not in state.get("allowed_refs", ()):
                    continue
                label, text = self.label(result, item)
                alias = short(item["ref_id"], session)
                meaning = item.get("meaning") or {}
                keywords = "、".join(meaning.get("keywords") or [])
                general = shorten(meaning.get("text") or "", 160)
                line = (
                    f"{alias}｜{result['full_name']}｜{label}｜关键词：{keywords or '无'}"
                    f"｜一般含义：{general or '无'}"
                )
                facts.append(Fact(alias, item["ref_id"], label, owner + text, line))
        return facts

    @staticmethod
    def label(result: dict, item: dict) -> tuple[str, str]:
        """(how the fact sheet names a fact, the text code renders for its placeholder)."""
        kind, fact = item["kind"], item["fact"]
        if kind == "shuli":
            grid = fact.split(":")[0]
            number, value = result["grids"][grid], result["shuli"][grid]
            text = f"{grid}{number}"
            return (f"{text}（数理{value}）" if value != number else text), text
        if kind == "sancai":
            text = f"三才配置「{result['sancai']['key']}」"
            return text, text
        names = {
            "stroke_rule": "康熙笔画规则",
            "compound_surname": "复姓的算法",
            "bazi_compare": "八字对照",
        }
        if item["key"] == "ambiguous_form":
            text = f"“{fact.split(':', 1)[1]}”的写法"
            return f"约定：{text}", text
        text = names.get(item["key"], "约定")
        return f"约定：{text}", text

    def strokes(self, session) -> list[str]:
        """The stroke counts the writer may copy, one line per name."""
        lines = []
        for result in self.results(session.state):
            counts = "、".join(
                f"{c['char']}按{c['form']}{c['strokes']}画"
                if c["form"] != c["char"]
                else f"{c['char']}{c['strokes']}画"
                for c in result["chars"]
            )
            lines.append(f"{result['full_name']}的康熙笔画：{counts}")
        return lines

    # ---- ⑤ compose -----------------------------------------------------------------------

    def messages(self, run, facts, session, *, prior=None, extra=""):
        names = [result["full_name"] for result in self.results(session.state)]
        return compose.name_messages(run.question, names, facts, self.strokes(session), extra=extra)

    def question_type(self, run, session, followup):
        return "name"

    # ---- ⑥ verify ------------------------------------------------------------------------

    def problems(self, texts, session):
        results = name_results(session.state)
        bound = next(iter(results.values())) if len(results) == 1 else None
        found = [check_claims(text, bound, results) for text in texts]
        if FATALISM.search(" ".join(texts)):
            found.append("姓名数理是民间约定，不能作命运断言")
        found += self.wording_problems(texts, session)
        return list(dict.fromkeys(problem for problem in found if problem))

    def complete(self, args, session):
        """Code asks the user to confirm every character with several written forms."""
        prompts = [
            prompt
            for result in self.results(session.state)
            for prompt in result.get("confirmation_prompts") or []
        ]
        advice = [f"{CONFIRM}：{prompt}" for prompt in prompts]
        args["advice"] = [*advice, *(a for a in args["advice"] if a not in advice)]

    # ---- readings written by code --------------------------------------------------------

    def degraded(self, session, facts, question_type, risk_text, followup, *, safety_only):
        results = self.results(session.state)
        listed = "、".join(result["full_name"] for result in results)
        safety = safety_for(risk_text)
        evidence = [{"ref_id": fact.alias} for fact in facts]
        if safety_only:
            args = {
                "question_type": question_type,
                "systems_used": ["name"],
                "summary": f"这次分析了{listed}的五格。这个问题牵涉重大的现实决定，这次不作解读。"[
                    :200
                ],
                "sections": [],
                "evidence": evidence,
                "advice": ["先听专业意见：现实中的重要决定，请结合专业人士的意见。"],
                "closing": "",
                "confidence": {"level": "low", "reason": "这次没有给出数理解读。"},
                "safety": safety if safety["flag"] else {"flag": True, "note": SAFETY_FALLBACK},
            }
            self.complete(args, session)
            return args
        by_name = {}
        for fact in facts:
            by_name.setdefault(fact.ref.split(":")[1], []).append(fact)
        meanings = {
            item["ref_id"]: item.get("meaning") or {}
            for result in results
            for item in result["interpretations"]
        }
        sections = []
        for result in results:
            group = [
                fact
                for fact in by_name.get(result["name_id"], [])
                if not fact.label.startswith("约定")
            ]
            sentences = []
            for fact in group:
                keywords = "、".join(meanings.get(fact.ref, {}).get("keywords") or [])
                sentences.append(
                    f"{fact.text}，常见说法与{keywords}有关。" if keywords else f"{fact.text}。"
                )
            sentences.append("五格数理是民间约定，只作自我反思的参考。")
            sections.append(
                {
                    "title": f"{result['full_name']}的五格与三才",
                    "body": "".join(sentences)[:1200],
                    "ref_ids": [fact.alias for fact in group],
                }
            )
        args = {
            "question_type": question_type,
            "systems_used": ["name"],
            "summary": f"这次按康熙笔画分析了{listed}的五格与三才。下面先给出各项的一般说法，请当作自我反思的参考。"[
                :200
            ],
            "sections": sections,
            "evidence": evidence,
            "advice": ["当作参考：数理只是取名习俗，结合自己的实际感受看待。"],
            "closing": "",
            "confidence": {"level": "low", "reason": "这次只给出了数理的一般说法。"},
            "safety": safety,
        }
        self.complete(args, session)
        return args
