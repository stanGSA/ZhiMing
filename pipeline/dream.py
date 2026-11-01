"""Dream interpretation in the pipeline (plan P2.1).

The symbols are read from the user's own words. Code finds the dictionary's aliases first; one
model call without tools (plan §3.4) then picks the dream's symbols, each with the phrase it
comes from, so a symbol the dictionary lacks is still named and reported as unmatched instead
of slipping past the checks. Code keeps only phrases found verbatim and symbols that are a
controlled normalisation of them (DreamMatcher.supported), exactly as the lookup's own validator
does. One lookup follows. Only matched symbols are interpreted; code writes the sentence about
the unmatched ones, and the whole reading when nothing matched.
"""

from __future__ import annotations

import json
import re

from common.output_policy import care_error, certainty_error
from harness.failures import failure
from harness.refs import short
from pipeline import compose
from pipeline.factsheet import CAVEAT, Fact, shorten
from pipeline.intent import CONTINUE, Intent
from pipeline.render import safety_for
from pipeline.state import RESUMABLE
from pipeline.system import System
from plugins.dream.match import NORMALISATIONS
from plugins.dream.validation import text_error

DREAM = re.compile(r"梦见|梦到|梦里|梦中|做梦|做了.{0,8}梦|噩梦|梦境|解梦|的梦")
# Another system named outside the dream page makes the question that system's, or several's.
OTHER = re.compile(
    r"塔罗|牌阵|抽[一二两三]?张|[一二两三单]张牌|八字|四柱|命盘|占星|星盘|星座|行运|本命|"
    r"姓名|名字|五格|运势|流日|流年|大运"
)
# A follow-up about a saved dream reading stays with the agent loop in P2.
REFERS_TO_READING = re.compile(
    r"(?:上一条|上一次|上次|刚才|之前|那次|原来)(?:那次|那条|的)?(?:解梦|解读|记录)|原记录"
)
MAX_SYMBOLS = 12
NO_DREAM = "请描述一下梦里的内容：出现了哪些人、物或场景，发生了什么，醒来时是什么感受。"
UNMATCHED_TITLE = "词典没有收录的意象"
SAFETY_FALLBACK = "这类问题牵涉健康或其他重大的现实决定，请结合专业意见再做判断。"


class Dream(System):
    name = "dream"
    kept = "意象查询结果"

    @property
    def matcher(self):
        return self.runtime.plugins["dream"].matcher

    # ---- ① intent ------------------------------------------------------------------------

    def detect(self, runtime, message):
        session = runtime.session
        selected = session.state.get("selected_systems")
        if selected not in (None, ["dream"]) or session.pinned_reading_id:
            return None
        # An interrupted dream run continues on "继续" (or its own question) wherever it is.
        run = runtime.store.unfinished_pipeline_run(session.user_id)
        if (
            run
            and run["stage"] in RESUMABLE
            and run["state"].get("system") == "dream"
            and (CONTINUE.search(message) or message.strip() == run["state"]["question"].strip())
        ):
            return Intent("dream", "resume", run=run)
        if selected is None and (OTHER.search(message) or not DREAM.search(message)):
            return None
        if REFERS_TO_READING.search(message):
            return None
        return Intent("dream", "new")

    def candidates(self, text: str) -> list[dict]:
        """The dictionary's symbols found in the text by code: aliases and documented phrases."""
        found = [
            {"phrase": alias, "symbol": alias, "at": start}
            for start, _, alias, _ in self.matcher.spans(text)
        ]
        for key, rule in NORMALISATIONS.items():
            for match in rule.finditer(text):
                found.append({"phrase": match[0], "symbol": key, "at": match.start()})
        found.sort(key=lambda item: item["at"])
        return [{"phrase": f["phrase"], "symbol": f["symbol"]} for f in found]

    def accepted(self, items, question: str) -> list[dict]:
        """Phrases found verbatim in the question, each with a symbol it supports."""
        kept, seen = [], set()
        for item in items:
            if not isinstance(item, dict):
                continue
            phrase = str(item.get("phrase") or "").strip()
            symbol = str(item.get("symbol") or "").strip()
            if not phrase or len(phrase) > 40 or phrase not in question:
                continue
            if not symbol or len(symbol) > 12 or not self.matcher.supported(phrase, symbol):
                # An unsupported normalisation falls back to the user's own words.
                if len(phrase) > 12:
                    continue
                symbol = phrase
            if symbol in seen:
                continue
            seen.add(symbol)
            kept.append({"phrase": phrase, "symbol": symbol})
        return kept[:MAX_SYMBOLS]

    async def extract(self, runner, run) -> tuple[list[dict], str]:
        """(symbols, where they came from): the model's choice, or code's when it gives none."""
        from pipeline.runner import OutOfBudget

        candidates = self.candidates(run.question)
        messages = compose.dream_extract_messages(run.question, candidates)
        try:
            text, truncated = await runner.ask(messages, "intent", run)
        except OutOfBudget:
            return self.accepted(candidates, run.question), "code"
        if not truncated:
            try:
                items = json.loads(compose.json_object(text)).get("symbols")
            except (ValueError, AttributeError):
                items = None
            if isinstance(items, list):
                return self.accepted(items, run.question), "model"
        return self.accepted(candidates, run.question), "code"

    # ---- ③ compute -----------------------------------------------------------------------

    async def compute(self, runner, run):
        from pipeline.runner import Stopped

        try:
            symbols, source = await self.extract(runner, run)
        except Stopped as stop:
            return stop.outcome
        runner.stage("extract", run_id=run.run_id, source=source, symbols=len(symbols))
        if not symbols:
            _, terminal = await runner.planned([("ask_user", {"question": NO_DREAM})])
            return terminal or failure(runner.session, "tool_error", "ask_failed", NO_DREAM)
        results, _ = await runner.planned(
            [
                ("start_reading", {"question": run.question, "systems": ["dream"]}),
                ("lookup_dream_symbols", {"symbols": symbols}),
            ]
        )
        if not all(result["ok"] for result in results):
            error = next(r for r in results if not r["ok"])
            return failure(runner.session, "tool_error", error.get("code"), error["error"])
        return None

    # ---- ④ fact sheet --------------------------------------------------------------------

    @staticmethod
    def result(state) -> dict:
        found = [
            value
            for key, value in (state.get("calculations") or {}).items()
            if key.startswith("dream_result:")
        ]
        return found[-1] if found else {"hits": [], "misses": [], "interpretations": []}

    def facts(self, session):
        state = session.state
        facts = []
        for item in self.result(state)["interpretations"]:
            if item["kind"] != "symbol" or item["ref_id"] not in state.get("allowed_refs", ()):
                continue
            alias = short(item["ref_id"], session)
            meaning = item.get("meaning") or {}
            text = f"「{item['key']}」"
            keywords = "、".join(meaning.get("keywords") or [])
            general = shorten(CAVEAT.sub("", meaning.get("text") or ""), 160)
            line = (
                f"{alias}｜意象{text}｜原话：“{item.get('phrase') or item['matched_from']}”"
                f"｜关键词：{keywords or '无'}｜一般含义：{general or '无'}"
            )
            facts.append(Fact(alias, item["ref_id"], item["key"], text, line))
        return facts

    def convention(self, session, key: str) -> str | None:
        for item in self.result(session.state)["interpretations"]:
            if item["kind"] == "convention" and item["key"] == key:
                return short(item["ref_id"], session)
        return None

    def misses(self, session) -> list[str]:
        return list(self.result(session.state)["misses"])

    # ---- ⑤ compose -----------------------------------------------------------------------

    def messages(self, run, facts, session, *, prior=None, extra=""):
        return compose.dream_messages(run.question, facts, self.misses(session), extra=extra)

    def question_type(self, run, session, followup):
        return "dream"

    # ---- ⑥ verify ------------------------------------------------------------------------

    def problems(self, texts, session):
        """The dream rules and the shared wording rules, all at once.

        The shared ones (output_policy) would refuse the draft at submission anyway; listing
        them here keeps their wording, so a certainty claim on a high-risk question is still
        recognised as a safety failure after the dream rule has caught it as a prophecy.
        """
        result = self.result(session.state)
        hits = {hit["key"] for hit in result["hits"]}
        misses = set(result["misses"])
        found = [text_error(text, self.matcher, hits, misses) for text in texts]
        if session.policy_judge is None:  # with the judge, submission applies its own checks
            found += [certainty_error(texts), care_error(texts)]
        return list(dict.fromkeys(problem for problem in found if problem))

    def unmatched_section(self, session) -> dict | None:
        misses = self.misses(session)
        if not misses:
            return None
        # One sentence per symbol: an abstention covers the symbol it follows, not the next.
        body = "".join(f"「{miss}」未收录。" for miss in misses)
        body += "这些意象在解梦词典里没有对应条目，这次不作解读。"
        alias = self.convention(session, "unmatched")
        return {"title": UNMATCHED_TITLE, "body": body, "ref_ids": [alias] if alias else []}

    def complete(self, args, session):
        """Code reports the unmatched symbols; the writer never names them."""
        section = self.unmatched_section(session)
        if section is None:
            return
        if len(args["sections"]) < 6:
            args["sections"].append(section)
        else:
            last = args["sections"][-1]
            last["body"] = f"{last['body']}\n{section['body']}"
            last["ref_ids"] = list(dict.fromkeys([*last["ref_ids"], *section["ref_ids"]]))
        for alias in section["ref_ids"]:
            if {"ref_id": alias} not in args["evidence"]:
                args["evidence"].append({"ref_id": alias})

    # ---- readings written by code --------------------------------------------------------

    def template(self, session, facts, question_type, risk_text):
        """Nothing matched: there is nothing to interpret, so code says so and asks for more."""
        if facts:
            return None
        section = self.unmatched_section(session)
        refs = [self.convention(session, "no_symbol"), *(section["ref_ids"] if section else [])]
        summary = (
            "这次描述里的意象在解梦词典中都没有收录，这次不作解读。"
            if section
            else "这次描述里没有找到可以解读的梦境意象，这次不作解读。"
        )
        return "no_symbol", {
            "question_type": question_type,
            "systems_used": ["dream"],
            "summary": summary,
            "sections": [section] if section else [],
            "evidence": [{"ref_id": ref} for ref in dict.fromkeys(refs) if ref],
            "advice": ["补充细节：说说梦里印象最深的人、物或场景，以及醒来时的感受，再试一次。"],
            "closing": "",
            "confidence": {"level": "low", "reason": "这次没有可以解读的意象。"},
            "safety": safety_for(risk_text),
        }

    def degraded(self, session, facts, question_type, risk_text, followup, *, safety_only):
        listed = "".join(fact.text for fact in facts)
        safety = safety_for(risk_text)
        evidence = [{"ref_id": fact.alias} for fact in facts]
        if safety_only:
            return {
                "question_type": question_type,
                "systems_used": ["dream"],
                "summary": f"这个梦里命中的意象有{listed}。这个问题牵涉重大的现实处境，这次不作解读。"[
                    :200
                ],
                "sections": [],
                "evidence": evidence,
                "advice": ["先听专业意见：身体或现实中的担心，请交给相关专业人士评估。"],
                "closing": "",
                "confidence": {"level": "low", "reason": "这次没有给出意象解读。"},
                "safety": safety if safety["flag"] else {"flag": True, "note": SAFETY_FALLBACK},
            }
        meanings = {
            item["key"]: item.get("meaning") or {}
            for item in self.result(session.state)["interpretations"]
            if item["kind"] == "symbol"
        }
        sections = []
        for fact in facts:
            keywords = "、".join(meanings.get(fact.label, {}).get("keywords") or [])
            body = f"梦见{fact.text}。"
            if keywords:
                body += f"这个意象常和{keywords}有关，可以对照最近的心情和压力想一想。"
            sections.append({"title": fact.text, "body": body, "ref_ids": [fact.alias]})
        args = {
            "question_type": question_type,
            "systems_used": ["dream"],
            "summary": f"这个梦里命中的意象有{listed}。下面先给出它们一般反映的心理，请结合自己的感受对照。"[
                :200
            ],
            "sections": sections,
            "evidence": evidence,
            "advice": [
                "先记下来：醒来后把梦里的场景和感受写下来，看看和最近哪件事有关。",
                "再照顾情绪：留出一点时间休息，或和信任的人聊聊让你在意的事。",
            ],
            "closing": "",
            "confidence": {"level": "low", "reason": "这次只给出了意象的一般含义。"},
            "safety": safety,
        }
        self.complete(args, session)
        return args
