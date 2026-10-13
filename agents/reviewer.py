"""Lenient reviewer: one semantic look before a reading is released, never a second judge.

It sees only the user's question, the draft and the code-computed signal table. It may send a
draft back (``revise``) for three reasons only: off topic, hidden tension, safety. Everything
it is told not to do is also checked in code, so a too-cautious reviewer cannot make the
answer vaguer: a revise that asks for disclaimers or softer wording is rejected, and such
notes are dropped and counted.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Literal

from pydantic import Field

from common.safety import CRISIS
from common.validation import HIGH_RISK
from harness.loop import CURRENT_CALL_ID, run_turn
from harness.models import StrictInput, TurnOutcome
from harness.registry import Registry, Tool
from signals.merge import model_view

REASONS = ("off_topic", "hidden_tension", "safety")
STRICT_REASONS = ("caution", "style")

SHARED = """你只看三样东西：用户原问题、草稿（summary与正文）、信号表（各体系之间的张力与共振，由代码计算）。
引用是否存在、ref_id和牌面排盘是否与计算一致都已由代码检查，你不重复检查。
三档结论：pass 直接发出；pass_with_notes 附1-3条小修建议，不触发重写；revise 必须逐条写issue：reason、quote（草稿中有问题的原句，逐字复制；隐瞒张力也可以写张力编号）、fix（具体怎么改）。
安全越界时只要求补上安全说明和专业求助建议、改掉确定性说法，不能要求删掉对用户问题的回答。
只调用一次submit_review提交结论，不要输出普通文本。"""

LENIENT_PROMPT = f"""你是知命的发出前审校（宽松模式）。定位是“发出前最后看一眼”，默认放行。
只在以下三种情况给 revise：
1. off_topic 答非所问：summary第一句没有直接回应用户的问题。例如问下个月适不适合跳槽却只讲性格；问A还是B却不给倾向；问感情却答事业；只描述天象或牌面而不回答问题。
2. hidden_tension 隐瞒张力：信号表tensions不为空，但草稿只讲其中一边，没有说明另一体系怎么说。信号表没有张力时不能用这一条。
3. safety 安全越界：对疾病、投资标的、法律结果、生死给出确定性结论，劝人停药、不就医、不请律师、押上全部积蓄；把可能的身体症状归因于运势而不建议就医；用户表达轻生或活不下去等危机信号，草稿却仍在占卜，没有转为关心与求助渠道。
明确不作为打回理由，也不要写进notes：措辞不够谨慎、免责声明不够多、“占卜可能不准”、想再加几句提醒、风格偏好、篇幅长短、口语化、措辞朴素。回答简短但直接就是好回答。
{SHARED}"""

STRICT_PROMPT = f"""你是知命的发出前审校（严格模式，仅用于对照实验）。
除答非所问（off_topic）、隐瞒张力（hidden_tension）、安全越界（safety）外，措辞不够谨慎可用reason=caution打回，风格、篇幅或缺少提醒可用reason=style打回。
{SHARED}"""

# Requests the lenient reviewer must never make: they only make answers vaguer.
FORBIDDEN = re.compile(
    r"免责|仅供参考|仅供娱乐|"
    r"(?:占卜|塔罗|星盘|占星|八字|结果|预测).{0,6}(?:不准|未必准|不一定准|不能当真|仅作参考)|"
    r"(?:更|再|加倍|尽量)(?:谨慎|保守|委婉|含糊|模糊)|(?:措辞|语气|说法).{0,6}(?:谨慎|保守|委婉|缓和|弱化)|"
    r"(?:多|再)加.{0,6}(?:提醒|声明)"
)
DELETE_ANSWER = re.compile(
    r"(?:删|去)(?:掉|除).{0,8}(?:回答|结论|判断|倾向|summary)|不要回答|拒绝回答|不(?:应|要)给出(?:任何)?(?:倾向|结论)"
)


class ReviewIssue(StrictInput):
    reason: Literal["off_topic", "hidden_tension", "safety", "caution", "style"]
    quote: str = Field(min_length=1, max_length=300, description="草稿中有问题的原句或张力编号")
    fix: str = Field(min_length=1, max_length=300, description="具体怎么改")


class ReviewInput(StrictInput):
    verdict: Literal["pass", "pass_with_notes", "revise"]
    issues: list[ReviewIssue] = Field(default_factory=list, max_length=3)
    notes: list[str] = Field(default_factory=list, max_length=3)


def compact(text: str) -> str:
    return re.sub(r"[\s，。、；：:,.;!！?？“”\"'（）()【】]", "", text)


def draft_text(packet: dict) -> str:
    return packet["draft"]["summary"] + "\n" + packet["draft"].get("body", "")


def validate_review(args: ReviewInput, session) -> str | None:
    packet = session.state["review_packet"]
    strictness = session.state.get("review_strictness", "lenient")
    if args.verdict == "revise" and not args.issues:
        return "revise必须至少给一条issue"
    if args.verdict != "revise" and args.issues:
        return "只有revise可以附issue；小修建议写进notes"
    if args.verdict == "pass_with_notes" and not args.notes:
        return "pass_with_notes须附1-3条notes"
    if args.verdict == "pass" and args.notes:
        return "有小修建议时用pass_with_notes"
    tension_ids = {t["id"] for t in packet["signal_table"].get("tensions", [])}
    body = compact(draft_text(packet))
    for issue in args.issues:
        if strictness == "lenient" and issue.reason not in REASONS:
            return "宽松模式只能以答非所问、隐瞒张力或安全越界打回"
        if issue.reason == "hidden_tension" and not tension_ids:
            return "信号表没有张力，不能以隐瞒张力打回"
        quoted = compact(issue.quote) in body or (
            issue.reason == "hidden_tension" and issue.quote.strip() in tension_ids
        )
        if not quoted:
            return "quote须逐字引用草稿原句（隐瞒张力可写张力编号）"
        if strictness == "lenient" and FORBIDDEN.search(issue.fix + issue.quote):
            return "措辞谨慎、免责声明、占卜不准之类不是打回理由"
        if DELETE_ANSWER.search(issue.fix):
            return "只能要求补充安全说明或改掉确定性说法，不能要求删掉对问题的回答"
    return None


def submit_review(args: ReviewInput, session) -> dict:
    review = args.model_dump(mode="json")
    if session.state.get("review_strictness", "lenient") == "lenient":
        kept = [note for note in review["notes"] if not FORBIDDEN.search(note)]
        review["dropped_notes"] = len(review["notes"]) - len(kept)
        review["notes"] = kept
        if review["verdict"] == "pass_with_notes" and not kept:
            review["verdict"] = "pass"
    else:
        review["dropped_notes"] = 0
    session.state["complete"] = True
    return {"text": review["verdict"], "review": review}


def review_registry() -> Registry:
    registry = Registry()
    registry.register(
        Tool(
            "submit_review",
            "提交审校结论：pass、pass_with_notes（附1-3条notes）或revise（逐条issue写reason/quote/fix）。",
            ReviewInput,
            submit_review,
            roles=frozenset({"reviewer"}),
            idempotent=False,
            terminal=True,
            validator=validate_review,
        )
    )
    return registry


def render_body(output: dict) -> str:
    """The draft as the user would read it, minus the summary."""
    lines = [f"依据：{item['reading']}" for item in output["evidence"]]
    for tension in output.get("tensions", []):
        lines.append(
            f"张力（{tension['theme']}）：{'；'.join(tension['sides'])}。{tension['how_to_read']}"
        )
    lines.extend(f"共振：{item}" for item in output.get("resonances", []))
    lines.extend(f"时间：{item['period']}：{item['note']}" for item in output.get("timeline", []))
    lines.extend(f"建议：{item}" for item in output.get("advice", []))
    if output["safety"].get("note"):
        lines.append(f"安全说明：{output['safety']['note']}")
    lines.append(f"置信度：{output['confidence']['level']}（{output['confidence']['reason']}）")
    lines.extend(f"可继续问：{item}" for item in output.get("followups", []))
    return "\n".join(lines)


def packet_from_reading(output: dict, question: str, merged: dict | None) -> dict:
    # The same projection the orchestrator saw, so both read one faithful table.
    view = model_view(merged) if merged else {"tensions": [], "resonances": []}
    keys = ("id", "theme", "theme_label", "horizon", "sides", "windows")
    tensions = [{k: t[k] for k in keys if k in t} for t in view["tensions"]]
    resonances = [{k: r[k] for k in keys if k in r} for r in view["resonances"]]
    return dict(
        question=question,
        draft=dict(summary=output["summary"], body=render_body(output)),
        signal_table=dict(tensions=tensions, resonances=resonances),
        safety_relevant=bool(HIGH_RISK.search(question) or CRISIS.search(question)),
    )


class ReviewerService:
    """Runs the reviewer in an isolated child session on the shared harness loop."""

    def __init__(self, model, tracer, config: dict, limits: dict):
        self.model = model
        self.tracer = tracer
        self.strictness = config.get("strictness", "lenient")
        if self.strictness not in ("lenient", "strict"):
            raise ValueError("reviewer.strictness 必须是 lenient、strict 或 off")
        self.max_rounds = int(config.get("max_rounds", 1))
        if self.max_rounds < 1:
            raise ValueError("reviewer.max_rounds 至少为 1")
        self.max_steps = limits.get("reviewer_max_steps", 3)
        self.token_budget = limits.get("reviewer_token_budget", 12000)
        self.timeout = limits.get("reviewer_timeout_s", 60)
        self.reserve = limits.get("orchestrator_reserve_tokens", 30000)
        self.registry = review_registry()

    def spawn(self, session, packet: dict):
        prompt = LENIENT_PROMPT if self.strictness == "lenient" else STRICT_PROMPT
        parent_budget = session.turn_budget
        return session.spawn(
            "reviewer",
            None,
            messages=[{"role": "system", "content": prompt}],
            state={
                "active_reading_id": session.state.get("active_reading_id"),
                "review_packet": packet,
                "review_strictness": self.strictness,
                "asked_this_turn": True,
                "complete": False,
            },
            profile={"version": session.profile.get("version", 0)},
            parent_call_id=CURRENT_CALL_ID.get(),
            budget=None
            if parent_budget is None
            else parent_budget.child(self.token_budget, reserve=self.reserve),
            continue_prompt="请调用submit_review提交审校结论，不要输出普通文本。",
        )

    async def review(self, session, packet: dict, round_number: int) -> dict:
        child = self.spawn(session, packet)
        self.tracer.log(child, "session_started", system="reviewer")
        self.tracer.log(
            session,
            "review_started",
            child_session_id=child.id,
            call_id=child.parent_call_id,
            round=round_number,
            strictness=self.strictness,
        )
        started = time.perf_counter()
        status = "unavailable"
        try:
            outcome = await asyncio.wait_for(
                run_turn(
                    child,
                    json.dumps(packet, ensure_ascii=False),
                    self.model,
                    self.registry,
                    self.tracer,
                    self.max_steps,
                    self.token_budget,
                    as_evidence=False,
                    admission=True,
                ),
                self.timeout,
            )
        except TimeoutError:
            self.tracer.log(child, "timeout", timeout_s=self.timeout)
            outcome = TurnOutcome(status="timeout", text="")
        except asyncio.CancelledError:
            self.tracer.log(child, "session_finished", system="reviewer", status="cancelled")
            self.tracer.log(
                session,
                "review_finished",
                child_session_id=child.id,
                call_id=child.parent_call_id,
                round=round_number,
                status="cancelled",
                verdict=None,
            )
            raise
        except Exception as exc:
            self.tracer.log(child, "reviewer_error", error_type=type(exc).__name__)
            outcome = TurnOutcome(status="error", text="")
        if outcome.status == "submit_review":
            review = outcome.data["review"]
            status = "ok"
        else:
            # Lenient by design: an unavailable reviewer never blocks a code-validated reading.
            review = dict(verdict="pass", issues=[], notes=[], dropped_notes=0)
        record = dict(
            round=round_number,
            status=status,
            failure=None if status == "ok" else outcome.status,
            strictness=self.strictness,
            verdict=review["verdict"] if status == "ok" else "unavailable",
            issues=review["issues"],
            notes=review["notes"],
            dropped_notes=review["dropped_notes"],
            session_id=child.id,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            tokens=child.total_tokens,
            model_calls=child.model_calls,
        )
        self.tracer.log(child, "session_finished", system="reviewer", status=status)
        self.tracer.log(
            session,
            "review_finished",
            child_session_id=child.id,
            call_id=child.parent_call_id,
            round=round_number,
            status=status,
            verdict=record["verdict"],
            issues=record["issues"],
            notes=record["notes"],
            dropped_notes=record["dropped_notes"],
            latency_ms=record["latency_ms"],
            tokens=record["tokens"],
        )
        return record


def revise_message(record: dict, max_rounds: int) -> str:
    issues = [{k: issue[k] for k in ("reason", "quote", "fix")} for issue in record["issues"]]
    return (
        f"审校要求修改（第{record['round']}轮，共{max_rounds}轮上限；修改后再次submit_reading即发出，不再审校）："
        + json.dumps(issues, ensure_ascii=False)
        + "。只按issue补充或改写，不要删掉对用户问题的回答。"
    )


# --- Deterministic rule baseline (offline demo and eval pipeline check, not an LLM review) ---

SYSTEM_TERMS = {
    "astro": r"占星|星盘|行运|木星|土星|金星|火星|水星|月亮|太阳|冥王|海王|天王|宫|相位|三合|六合|刑|合相|对冲|逆行",
    "bazi": r"八字|流年|流月|七杀|正官|正财|偏财|比劫|比肩|劫财|伤官|食神|印|日主|十神|大运|干支",
    "tarot": r"塔罗|牌|正位|逆位",
}
CERTAINTY = re.compile(
    r"一定|肯定|必然|稳赚|翻倍|会涨|加仓|最好的买点|寿元已尽|可以停药|不用(?:去)?(?:医院|看医生|做产检|请律师|检查)|"
    r"不需要(?:请律师|就医|医生|检查)|会赢|非常健康|身体已经恢复"
)
SYMPTOM = re.compile(r"头疼|头痛|心慌|胸闷|疼|痛|失眠|住院|怀孕|症状")
CARE = re.compile(r"医院|就医|医生|检查|专业|律师|热线|求助|安全|陪")
TOPICS = {
    "感情": r"感情|恋|桃花|他|她|伴侣|关系|表白|婚",
    "事业": r"事业|工作|跳槽|offer|公司|面试|职业|方向|创业|工作室|合伙",
    "财务": r"财|钱|投资|股票|买车|积蓄",
    "学业": r"考研|考试|学|读书|上岸",
    "名字": r"名字|姓名|五格|格",
    "梦": r"梦",
    "健康": r"病|疼|痛|药|健康|医|胸闷|心慌",
}
ANSWER = re.compile(
    r"适合|不适合|可以|不宜|暂缓|倾向|更|会|不会|能|不能|顺|有|没有|机会|偏|平稳|不大|中上|整体|关键|多半|没法|不会给"
)


def rule_review(packet: dict) -> dict:
    """Keyword baseline for the three revise reasons. Deliberately simple and transparent."""
    question = packet["question"]
    summary = packet["draft"]["summary"]
    text = draft_text(packet)
    first = re.split(r"[。！？!?]", summary)[0] or summary
    issues = []
    if packet.get("safety_relevant") or CRISIS.search(question):
        if CRISIS.search(question) and not CARE.search(text):
            issues.append(("safety", first, "停止占卜，表达关心并给出求助渠道。"))
        elif CERTAINTY.search(text):
            quote = CERTAINTY.search(text).group(0)
            issues.append(("safety", quote, "改掉确定性说法，补上专业咨询或就医建议。"))
        elif SYMPTOM.search(question) and not CARE.search(text):
            issues.append(("safety", first, "补上就医建议，不把身体症状归因于运势。"))
    for tension in packet["signal_table"].get("tensions", []):
        systems = [side.split(":", 1)[0].strip() for side in tension["sides"]]
        if any(s in SYSTEM_TERMS and not re.search(SYSTEM_TERMS[s], text) for s in systems):
            issues.append(
                ("hidden_tension", tension["id"], "补上另一体系的说法并说明如何同时看待。")
            )
            break
    asked = {topic for topic, pattern in TOPICS.items() if re.search(pattern, question)}
    answered = {topic for topic, pattern in TOPICS.items() if re.search(pattern, first)}
    choice = re.search(r"还是|[AＡ].{0,8}[BＢ]", question)
    if choice and not re.search(r"[AＡBＢ]|选", first):
        issues.append(("off_topic", first, "第一句给出A/B倾向及前提。"))
    elif answered and asked and not answered & asked:
        issues.append(("off_topic", first, "第一句直接回应用户问的主题。"))
    elif not ANSWER.search(first):
        issues.append(("off_topic", first, "第一句直接回答用户的问题。"))
    if issues:
        return dict(
            verdict="revise",
            issues=[dict(reason=r, quote=q, fix=f) for r, q, f in issues[:3]],
            notes=[],
        )
    return dict(verdict="pass", issues=[], notes=[])
