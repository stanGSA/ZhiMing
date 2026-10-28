from __future__ import annotations

import json
import re

from agents.reviewer import packet_from_reading, revise_message
from common.domain_rules import rules_for
from common.evidence import calculation_evidence_texts
from common.input_evidence import (
    clock_in,
    gender_evidence,
    normalized_gender,
    solar_time_choice,
    supported_birth,
)
from common.location import consultation_timezone_evidence
from common.schemas import (
    LOOKUP_KINDS,
    AskInput,
    EmptyInput,
    LookupInput,
    ProfileInput,
    Reading,
    ReadInput,
    StartInput,
)
from common.validation import validate_reading
from harness.models import ToolResult
from harness.registry import Tool
from harness.session import valid_timezone
from knowledge.kb import KnowledgeBase
from plugins.base import MEANING_FIELDS
from signals.merge import fingerprint, merge_signals, model_view, undisclosed

SYSTEM_NAMES = {"astro": r"占星|星盘|星座", "bazi": r"八字|命理|四柱", "tarot": r"塔罗|牌"}
PREFER = r"更信|更相信|更看重|侧重|偏好|以.{0,4}为主|多看|优先"
DISCOUNT = r"不太信|不怎么信|不信|少看|淡化|不看重|参考就好"
NEGATED_PREFER = (
    r"(?:不|没有|并不|并没有|别|不是)(?:很|太)?(?:更信|更相信|更看重|偏好|侧重|优先|多看)"
)
NEGATED_DISCOUNT = rf"(?:不是|并非|并不|不|没有|别|不要)(?:很|太)?(?:{DISCOUNT})"
CLAUSE = re.compile(r"[，,。；;！!？?、\n]|而且|而是|而|但是|但|可是|不过|然而")
# What an ask_user question may not ask again once the profile holds it, unless a tool asked
# for it in this turn (needs_input) or the user is correcting it.
REASK = {
    "gender": r"性别|男(?:性|生)?还是女|女(?:性|生)?还是男",
    "birth_date": r"出生(?:日期|年月日)|生日|哪年|几月几日",
    "birth_place": r"出生地|在哪(?:里|儿)?出生|出生(?:的)?城市",
}
CORRECTION = re.compile(r"记错|更正|改一下|改成|不对|搞错|纠正|重新确认")


def pending_input(session) -> bool:
    """A tool or specialist in this turn asked for user input (so a clarifying ask is legit)."""
    last_user = max((i for i, m in enumerate(session.messages) if m["role"] == "user"), default=-1)
    for message in session.messages[last_user + 1 :]:
        if message["role"] != "tool":
            continue
        try:
            payload = json.loads(message["content"])
        except (TypeError, ValueError):
            continue
        data = payload.get("data") or {}
        report = data.get("report") or {}
        if (
            data.get("status") == "needs_input"
            or data.get("candidates")
            or report.get("status") == "needs_input"
            or payload.get("code") == "missing_profile"
        ):
            return True
    return False


def known_fields(profile: dict) -> set[str]:
    known = set()
    if profile.get("gender"):
        known.add("gender")
    if profile.get("birth_local_dt"):
        known.add("birth_date")
    if profile.get("birth_place") or profile.get("location_id"):
        known.add("birth_place")
    return known


def stance(clause: str) -> int | None:
    """+1 prefer, -1 discount, None when the clause states no clear preference."""
    if re.search(NEGATED_PREFER, clause) or re.search(NEGATED_DISCOUNT, clause):
        return None
    if re.search(DISCOUNT, clause):
        return -1
    if re.search(PREFER, clause):
        return 1
    return None


def weights_validator(value, evidence: str) -> str | None:
    """Every changed weight must follow the user's own stance on that very system.

    The evidence is split into clauses; a system's stance comes only from clauses that name
    that system and no other, so "我更信八字，不太信占星" supports bazi > 1 and astro < 1 but
    never the reverse, and a negated preference ("不更信八字") supports nothing.
    """
    if not isinstance(value, dict) or not value:
        return "体系权重须为 {体系: 权重} 对象"
    clauses = [c for c in CLAUSE.split(evidence) if c.strip()]
    stances_by_clause = [stance(c) for c in clauses]
    # "更信八字而不是占星" is an explicit comparison; a bare "不是" elsewhere
    # (e.g. "八字不是唯一依据") is not evidence of distrust.
    for index, clause in enumerate(clauses):
        if index and stances_by_clause[index - 1] == 1:
            for names in SYSTEM_NAMES.values():
                if re.fullmatch(rf"\s*不是(?:{names})\s*", clause) and not re.search(
                    names, clauses[index - 1]
                ):
                    stances_by_clause[index] = -1
    for system, weight in value.items():
        if system not in SYSTEM_NAMES:
            return f"未知体系：{system}"
        if type(weight) not in (int, float) or not 0.5 <= weight <= 2:
            return "体系权重须在0.5到2之间"
        if weight == 1:
            continue
        own = [
            index
            for index, c in enumerate(clauses)
            if re.search(SYSTEM_NAMES[system], c)
            and not any(re.search(SYSTEM_NAMES[o], c) for o in SYSTEM_NAMES if o != system)
        ]
        if not own:
            if any(re.search(SYSTEM_NAMES[system], c) for c in clauses):
                return "一句话同时提到多个体系时无法判断偏好，请分别说明对每个体系的看法"
            return "调整权重的体系必须在用户原话中出现"
        stances = {stances_by_clause[index] for index in own} - {None}
        if len(stances) != 1:
            return f"原话对{system}没有明确且一致的偏好（注意否定说法）"
        wanted = stances.pop()
        if weight > 1 and wanted != 1:
            return "提高权重须有针对该体系的“更信/更看重”原话"
        if weight < 1 and wanted != -1:
            return "降低权重须有针对该体系的“不太信/少看”原话"
    return None


NUMERALS = "一二三四五六"


def evidence_count_line(output: dict) -> str:
    return (
        f"解读依据：共 {len(output['evidence'])} 条计算事实"
        "（网页解读面板可展开查看；命令行输入 /evidence 查看）"
    )


def render_evidence(output: dict) -> str:
    return "\n".join(f"- {item['reading']}" for item in output["evidence"])


def render_reading(output: dict) -> str:
    """Plain text for the CLI and the chat bubble: verdict, layered analysis, then actions.

    The evidence appendix of a layered reading is shown only as a count; the full items stay
    in the saved record (web panel, /evidence). Readings saved before sections existed keep
    their original layout, evidence first.
    """
    sections = output.get("sections") or []
    lines = [output["summary"]]
    for index, section in enumerate(sections):
        lines.extend(["", f"{NUMERALS[index]}、{section['title']}", section["body"]])
    if not sections:
        lines.extend(["", "依据："])
        lines.extend(f"- {item['reading']}" for item in output["evidence"])
    if output["advice"]:
        title = "行动建议：" if sections else "可以考虑："
        lines.extend(["", title, *[f"- {item}" for item in output["advice"]]])
    if output.get("timeline"):
        lines.extend(
            [
                "",
                "时间安排：",
                *[f"- {item['period']}：{item['note']}" for item in output["timeline"]],
            ]
        )
    if output.get("resonances"):
        lines.extend(["", "彼此呼应：", *[f"- {item}" for item in output["resonances"]]])
    if output.get("tensions"):
        lines.extend(
            [
                "",
                "不同视角：",
                *[
                    f"- {item['theme']}：{'；'.join(item['sides'])}。{item['how_to_read']}"
                    for item in output["tensions"]
                ],
            ]
        )
    if output.get("closing"):
        lines.extend(["", output["closing"]])
    if sections:
        lines.extend(["", evidence_count_line(output)])
    lines.extend(
        [
            "",
            "解读置信度："
            + {"low": "低", "medium": "中", "high": "高"}[output["confidence"]["level"]],
        ]
    )
    if output["safety"]["flag"] and output["safety"]["note"]:
        lines.append(output["safety"]["note"])
    lines.append("仅供参考与自我反思。")
    return "\n".join(lines)


def common_tools(store, kb: KnowledgeBase, mode: str = "single", reviewer=None) -> list[Tool]:
    def start_validator(args, session):
        if session.pinned_reading_id:
            return "本次正在追问指定历史解读，请使用read_reading，不要开启新记录。"
        current = session.user_messages[-1]
        if (
            session.state.get("tarot_drawn")
            and not session.state.get("complete")
            and not re.search(r"重抽|重新抽|重新占", current)
        ):
            return "当前抽牌尚未提交，请先完成当前记录；重抽必须用户明确要求"
        return None

    def start(args, session):
        previous = None
        if args.parent_reading_id:
            previous = store.get_reading(session.user_id, args.parent_reading_id)
            if previous is None:
                return ToolResult.failure("missing_reading", "关联的记录不属于当前用户")
        reading_id = session.start_reading(args.question)
        if previous:
            # Cross-session revisit or correction: link explicitly, keep the old reading as is.
            session.state["parent_reading_id"] = previous["reading_id"]
        request = session.user_messages[-1]
        session.state["question_source"] = request
        spread = (
            "decision"
            if re.search(r"二选一|决策牌阵|A/B", request)
            else "three_card"
            if re.search(r"三张|三牌", request)
            else "single"
            if re.search(r"单张|一张", request)
            else None
        )
        session.state["systems"] = session.state.get("systems") or args.systems
        spread = session.state.get("selected_spread") or args.requested_spread or spread
        session.state["requested_spread"] = spread
        result = {"reading_id": reading_id, "question": args.question, "requested_spread": spread}
        result["systems"] = session.state.get("systems")
        result["domain_rules"] = rules_for(
            session.state.get("systems") or ["astro", "bazi", "tarot", "name", "dream", "daily"]
        )
        if previous:
            result["previous_reading"] = previous_view(previous)
        return result

    def previous_view(row) -> dict:
        merged = row.get("merge_json") or {}
        output = row["output_json"]
        return dict(
            reading_id=row["reading_id"],
            question=row["question"],
            created_at=row["created_at"],
            summary=output.get("summary"),
            systems_used=row["systems_used"],
            timeline=output.get("timeline", []),
            tensions=output.get("tensions", []),
            timeframe=(row.get("calculations_json") or {}).get("timeframe"),
            merge=model_view(merged) if "tensions" in merged else None,
        )

    def merged_for(session) -> dict:
        """The cross-system table for the current signals and weights (cached per state)."""
        state = session.state
        signals = state.get("signals", [])
        weights = session.profile.get("system_weights") or {}
        tz = state.get("timeframe_tz") or session.profile.get("consultation_tz") or "Asia/Shanghai"
        key = json.dumps([fingerprint(signals), weights, tz], sort_keys=True)
        if state.get("merge_key") == key and state.get("merge"):
            return state["merge"]
        try:
            rule = kb.rules("merge")
        except ValueError:
            rule = None  # A knowledge edition built before week 5: fall back to defaults.
        state["merge"] = merge_signals(signals, rule, weights, tz)
        state["merge_key"] = key
        return state["merge"]

    def merge_tool(args, session):
        state = session.state
        if state.get("response_mode") == "followup":
            # A follow-up explains what the reading said: never recompute with today's weights
            # or rules. A new evaluation is a new reading linked to the old one.
            snapshot = state.get("merge_snapshot")
            if not snapshot:
                return ToolResult.failure(
                    "missing_snapshot",
                    "该历史记录没有保存合并表；需要重新评估请开新记录并关联旧记录",
                )
            return {"merge": model_view(snapshot), "snapshot": True}
        if not state.get("signals"):
            return ToolResult.failure("missing_signals", "本记录还没有任何体系的信号")
        return {"merge": model_view(merged_for(session))}

    def get_profile(args, session):
        session.profile = store.get_profile(session.user_id)
        if session.birth_binding:
            session.profile.update(session.birth_binding["profile"])
        session.refresh_calendar()
        return {"profile": session.profile}

    def profile_validator(args, session):
        if session.birth_binding and args.field in session.birth_binding["profile"]:
            if args.value != session.birth_binding["profile"][args.field]:
                return "出生资料已绑定本次表单，请先修改表单后再开始新的解读。"
        if not any(args.evidence in message for message in session.user_messages):
            return "evidence 必须是用户原话的连续子串"
        if args.field in ("zishi_rule", "calendar_input"):
            terms = {
                "next_day": r"23(?:点|:00).*换日|子初换日|next_day",
                "same_day": r"(?:0点|0:00|零点).*换日|子正换日|same_day",
                "solar": r"公历|阳历|solar",
                "lunar": r"农历|阴历|lunar",
            }
            allowed = {"next_day", "same_day"} if args.field == "zishi_rule" else {"solar", "lunar"}
            return (
                None
                if isinstance(args.value, str)
                and args.value in allowed
                and re.search(terms[args.value], args.evidence)
                else "历法与子时规则须有原话明确支持"
            )
        if args.field == "prefs_json" and isinstance(args.value, dict):
            if args.value == {"birth_data_is_synthetic": True} and re.search(
                r"合成资料|合成测试|虚构资料", args.evidence
            ):
                return None
            import json

            try:
                return None if json.loads(args.evidence) == args.value else "偏好JSON须与原话一致"
            except (ValueError, TypeError):
                return "偏好JSON须由原话提供；合成资料只支持birth_data_is_synthetic=true标记"
        if args.field == "gender":
            return (
                None
                if normalized_gender(args.value) in gender_evidence(args.evidence)
                else "性别规范值必须由原话明确支持"
            )
        if args.field == "birth_local_dt":
            return (
                None
                if supported_birth(args.value, args.evidence, len(str(args.value)) > 10)
                else "出生日期时刻须由原话规范化得到"
            )
        if args.field == "system_weights":
            return weights_validator(args.value, args.evidence)
        if args.field in ("lat", "lon", "location_id", "tz", "consultation_tz"):
            # The calendar and crisis contacts read both fields every turn: only IANA keys.
            if args.field in ("tz", "consultation_tz") and not valid_timezone(args.value):
                return "请使用有效IANA时区"
            if args.field == "consultation_tz":
                return (
                    None
                    if consultation_timezone_evidence(
                        args.evidence, session, session.profile.get("tz")
                    )
                    == args.value
                    and consultation_timezone_evidence(
                        [m for m in session.user_messages if args.evidence in m][-1],
                        session,
                        session.profile.get("tz"),
                    )
                    == args.value
                    else "咨询时区须有当前居住地或按该地时间的明确原话，并先解析地点"
                )
            resolved = any(
                location.get(args.field) == args.value
                for location in session.state.get("locations", {}).values()
            )
            explicit = str(args.value) in args.evidence
            if not (resolved or explicit):
                return "地理字段须来自已确认地点或原话"
            if args.field in ("lat", "lon") and (
                type(args.value) not in (int, float)
                or not -(90 if args.field == "lat" else 180)
                < args.value
                <= (90 if args.field == "lat" else 180)
            ):
                return "经纬度无效"
            return None
        if isinstance(args.value, str) and args.value not in args.evidence:
            return "字段值必须在 evidence 原话中，不允许臆测"
        if args.field == "name" and (
            not isinstance(args.value, str) or not 1 <= len(args.value) <= 100
        ):
            return "姓名字段需要有效字符串"
        if args.field in ("time_known", "true_solar_time"):
            if type(args.value) is not bool:
                return "该字段必须是布尔值"
            if args.field == "true_solar_time":
                if solar_time_choice(args.evidence) is not args.value:
                    return "真太阳时开关须由肯定或否定的完整原话确认"
                messages = [m for m in session.user_messages if args.evidence in m]
                if solar_time_choice(messages[-1]) is not args.value:
                    return "真太阳时开关与完整用户原话冲突或未明确"
                return None
            confirmations = (
                ("知道", "确定", "准确", "开启", "使用")
                if args.value
                else ("不知道", "不确定", "未知", "关闭", "不用")
            )
            if args.value and any(
                word in args.evidence for word in ("不知道", "不确定", "未知", "关闭", "不用")
            ):
                return "布尔字段与用户否定表达冲突"
            explicit_clock = (
                args.field == "time_known"
                and args.value is True
                and clock_in(args.evidence) is not None
            )
            if not explicit_clock and not any(word in args.evidence for word in confirmations):
                return "布尔字段需要用户原话明确确认"
        if not isinstance(args.value, (str, bool)):
            return "第一周画像写入仅支持有直接原话依据的字符串或布尔值"
        return None

    def update_profile(args, session):
        value = normalized_gender(args.value) if args.field == "gender" else args.value
        if args.field == "birth_local_dt":
            from datetime import datetime

            value = (
                datetime.fromisoformat(value).isoformat(sep=" ", timespec="minutes")
                if len(value) > 10
                else value
            )
        session.profile = store.update_profile(session.user_id, args.field, value, args.evidence)
        session.refresh_calendar()
        return {"profile": session.profile}

    def lookup(args, session):
        version = session.state.get("kb_lookup_version") or session.state.get("kb_version")
        lookup_kb = kb if not version or version == kb.version else KnowledgeBase(kb.path, version)
        try:
            entry = lookup_kb.lookup(args.system, args.kind, args.key)
            candidates = (
                lookup_kb.suggested_keys(args.system, args.kind, args.key) if entry is None else []
            )
        finally:
            if lookup_kb is not kb:
                lookup_kb.close()
        if entry is None:
            return ToolResult.failure(
                "missing_entry",
                "缺条目：精确 key 或同义词未命中"
                + lookup_hint(args, session)
                + ("；本版本有效key候选：" + "、".join(candidates) if candidates else "")
                + "。已有计算附带释义时直接使用；不要继续猜key。",
            )
        session.state.setdefault("kb_refs", set()).add(entry["ref_id"])
        # The model sees the review level, not who reviewed it.
        return {"entry": {k: v for k, v in entry.items() if k != "model_review"}}

    def lookup_hint(args, session) -> str:
        kinds = LOOKUP_KINDS[args.system]
        if args.kind not in kinds:
            return f"；{args.system}的kind只能是{'、'.join(kinds)}"
        if (args.system, args.kind) != ("tarot", "card"):
            return "；key须照抄工具结果中的meaning_key或key"
        cards = (session.state.get("tarot_result") or {}).get("cards", [])
        keys = "、".join(c["meaning_key"] for c in cards if c.get("meaning_key"))
        drawn = f"；本次牌面已随抽牌返回释义，无需再查：{keys}" if keys else ""
        return "；牌面key为card_id:upright或card_id:reversed，如cups_four:upright" + drawn

    def ask_validator(args, session):
        if session.state.get("asked_this_turn"):
            return "每轮最多追问一次"
        if pending_input(session) or CORRECTION.search(" ".join(session.user_messages[-1:])):
            return None
        known = known_fields(session.profile)
        repeated = [
            field
            for field, pattern in REASK.items()
            if field in known and re.search(pattern, args.question)
        ]
        if repeated:
            return (
                "画像已有这些资料，不要重复追问："
                + "、".join(repeated)
                + "；直接使用画像，用户主动更正时再更新"
            )
        return None

    def ask(args, session):
        session.state["asked_this_turn"] = True
        return {"text": args.question}

    def current_reading(session) -> dict:
        """This turn's reading lives in the session until submit_reading saves it.

        Show its facts and citable references without resetting anything, so a rejected
        draft is repaired from the same draw and calculations.
        """
        state = session.state
        texts = calculation_evidence_texts(state)
        names = {full: alias for alias, full in state.get("ref_alias", {}).items()}
        refs = sorted(
            state.get("allowed_refs", ()),
            key=lambda ref: (0, int(names[ref][1:]), "") if ref in names else (1, 0, ref),
        )
        pending = {
            system: facts
            for system, facts in state.get("specialist_facts", {}).items()
            if facts.get("signals")
        }
        tarot = state.get("tarot_result") or pending.get("tarot", {}).get("values", {}).get(
            "tarot_result"
        )
        if pending:
            stage = "needs_specialist_report"
            note = (
                "这些专家已保留计算事实，但报告尚未完成："
                + "、".join(sorted(pending))
                + "。请调用consult_specialist重试这些专家，复用原事实完成报告，不要重抽；"
                "尚未合并的事实不能直接提交，已有citable中的ref_id仍可使用。"
            )
        elif not refs:
            stage = "needs_calculation"
            next_step = (
                "继续consult_specialist咨询所选专家（每日运势使用daily_fortune）"
                if mode == "multi"
                else "继续调用所选体系的计算或抽牌工具"
            )
            note = (
                "本轮尚未完成计算，没有可提交的引用；请"
                + next_step
                + "，资料不足时先ask_user追问。"
            )
        else:
            stage = "ready_to_submit"
            note = (
                "本轮记录尚未提交入库，牌面与计算均已保留在会话中；"
                "evidence和sections只用citable中的ref_id，修正后直接submit_reading，"
                "不要重新抽牌或计算。"
            )
        return {
            "reading": dict(
                reading_id=state["active_reading_id"],
                question=state.get("question"),
                status="in_progress",
                recovery_stage=stage,
                pending_specialists=sorted(pending),
                systems=sorted({s["system"] for s in state.get("signals", [])}),
                tarot_json=tarot,
                chart_id=state.get("chart_id"),
                bazi_id=state.get("bazi_id"),
                citable=[{"ref_id": ref, "fact": texts.get(ref, "")} for ref in refs],
                note=note,
            )
        }

    def read(args, session):
        if session.pinned_reading_id and args.reading_id not in (None, session.pinned_reading_id):
            return ToolResult.failure(
                "reading_mismatch", "本次问题已绑定历史解读，不能切换到其他记录。"
            )
        reading_id = (
            session.pinned_reading_id or args.reading_id or session.state.get("active_reading_id")
        )
        if not reading_id:
            recent = store.recent_readings(session.user_id, limit=1)
            reading_id = recent[0]["reading_id"] if recent else None
        result = store.get_reading(session.user_id, reading_id) if reading_id else None
        if not result and reading_id and reading_id == session.state.get("active_reading_id"):
            return current_reading(session)
        if not result:
            return ToolResult.failure("missing_reading", "没有属于当前用户的占卜记录")
        # Older saved draws may predate inline meanings; use their pinned edition.
        tarot = result["tarot_json"] or {"cards": [], "seed": None}
        for card in tarot["cards"]:
            if "meaning" not in card:
                version_kb = (
                    kb
                    if result["kb_version"] == kb.version
                    else KnowledgeBase(kb.path, result["kb_version"])
                )
                try:
                    entry = version_kb.lookup("tarot", "card", card["meaning_key"])
                    card["meaning"] = {k: entry[k] for k in MEANING_FIELDS}
                finally:
                    if version_kb is not kb:
                        version_kb.close()
        session.cache.clear()
        # Replace, not update: nothing from the previously active reading may leak into the
        # restored one (calculations, specialist reports, consult caches).
        session.state = dict(
            asked_this_turn=session.state.get("asked_this_turn", False),
            ref_alias=session.state.get("ref_alias", {}),
            question_message_index=max(0, len(session.user_messages) - 1),
            specialist_reports=store.specialist_reports(session.user_id, result["reading_id"]),
        )
        session.state.update(
            active_reading_id=result["reading_id"],
            parent_reading_id=result["parent_reading_id"],
            question=result["question"],
            seed=tarot["seed"],
            tarot_result=result["tarot_json"],
            signals=result["signals_json"],
            facts=[c["name"] for c in tarot["cards"]],
            allowed_refs={s["ref_id"] for s in result["signals_json"]},
            kb_refs={
                ref for s in result["signals_json"] for ref in (s.get("kb_refs") or [s["kb_ref"]])
            },
            kb_version=result["kb_version"],
            kb_lookup_version=result["kb_version"],
            tarot_drawn=bool(tarot["cards"]),
            complete=False,
            response_mode="followup",
        )
        session.birth_context = result.get("birth_context_json") or None
        calculations = result.get("calculations_json") or {}
        session.state["calculations"] = calculations
        session.state.update(calculations)
        if calculations.get("daily_result"):
            # The daily card is a drawn card of this reading as well.
            session.state["facts"].append(calculations["daily_result"]["card"]["name"])
        for key in ("chart_id", "bazi_id"):
            if result.get(key):
                session.state[key] = result[key]
        # A follow-up explains the saved cross-system table, never a recomputed one: the full
        # snapshot is pinned to the session for merge_signals and the disclosure check.
        stored = result.get("merge_json") or {}
        if "tensions" in stored:
            session.state["merge_snapshot"] = stored
        result["merge"] = model_view(stored) if "tensions" in stored else None
        return {"reading": result}

    def validate_submit(args, session):
        error = validate_reading(args, session)
        if error or mode != "multi":
            return error
        state = session.state
        if state.get("response_mode") == "followup":
            # A follow-up may answer a narrow question, but it may not drop or contradict the
            # saved reading's disagreements: its tensions must still cover the snapshot.
            table = state.get("merge_snapshot")
            where = "原记录的张力不能在追问中丢失，须保留在tensions中："
        else:
            table = merged_for(session)
            where = (
                "信号表中的张力未披露，须写进tensions（theme、两边体系各自怎么说、how_to_read）："
            )
        missing = undisclosed(table, args) if table else []
        if missing:
            return where + "；".join(describe(t) for t in missing)
        return None

    def describe(tension) -> str:
        windows = [w["window"] for w in tension["windows"] if w["window"]]
        when = f"，日期：{'、'.join(windows[:5])}" if windows else ""
        return f"{tension['id']}（{tension['theme_label']}{when}：{' / '.join(tension['side_texts'])}）"

    def user_question(session) -> str:
        index = session.state.get("question_message_index", 0)
        messages = session.user_messages
        return messages[index] if 0 <= index < len(messages) else session.state["question"]

    async def submit(args, session):
        from memory.store import StaleBirthError

        try:
            store.check_birth_version(session)
        except StaleBirthError as exc:
            return ToolResult.failure("birth_version_conflict", str(exc))
        if session.policy_judge is not None:
            from common.output_policy import authored_texts

            failure = await session.policy_judge.check(authored_texts(args), session)
            if failure:
                return failure
        output = args.model_dump(mode="json")
        if output.get("verdict") is None:
            output.pop("verdict", None)
        state = session.state
        response_id = None
        review = None
        if state.get("response_mode") == "followup":
            response_id = store.save_response(session, output)
        else:
            merged = merged_for(session) if state.get("signals") else None
            notes = state.setdefault("review_notes", [])
            revisions = sum(note["verdict"] == "revise" for note in notes)
            # The reviewer runs automatically and cannot be skipped; after max_rounds revise
            # verdicts the next code-validated draft is released without another review.
            if reviewer is not None and revisions < reviewer.max_rounds:
                packet = packet_from_reading(output, user_question(session), merged)
                review = await reviewer.review(session, packet, len(notes) + 1)
                notes.append(review)
                if review["verdict"] == "revise":
                    return ToolResult.failure(
                        "review_revise", revise_message(review, reviewer.max_rounds)
                    )
            try:
                store.save_reading(
                    session,
                    output,
                    mode,
                    state.get("specialist_reports"),
                    merge=merged,
                    reviews=notes,
                )
            except StaleBirthError as exc:
                return ToolResult.failure("birth_version_conflict", str(exc))
        state["complete"] = True
        state["output"] = output
        return {
            "text": render_reading(output),
            "reading_id": state["active_reading_id"],
            "response_id": response_id,
            "reading": output,
            "review": None
            if review is None
            else {k: review[k] for k in ("round", "verdict", "notes", "status")},
            # Style and completeness findings recorded instead of rejected (kept in the trace).
            "warnings": list(state.get("output_warnings") or []),
        }

    all_roles = frozenset({"orchestrator", "tarot", "astro", "bazi", "name", "dream"})
    tools = [
        Tool(
            "start_reading",
            "新问题开始新记录。追问原牌面时不要调用。",
            StartInput,
            start,
            idempotent=False,
            validator=start_validator,
        ),
        Tool(
            "get_profile",
            "读取当前用户画像，不需要 user_id 参数。",
            EmptyInput,
            get_profile,
            idempotent=False,
        ),
        Tool(
            "update_profile",
            "仅保存用户明确提供的姓名、性别、出生日期地点、是否知道时辰、当前咨询时区、偏好JSON或体系权重；evidence须为原话连续片段。出生地经纬度/时区/location_id由resolve_location自动保存，公历口径、真太阳时与子时规则由成功排盘自动保存，不要在此写入。",
            ProfileInput,
            update_profile,
            validator=profile_validator,
        ),
        Tool(
            "lookup_meaning",
            "按 system/kind/key 精确查释义；不允许猜测缺失条目。",
            LookupInput,
            lookup,
            roles=all_roles,
            cache_state_keys=("kb_lookup_version", "kb_version"),
        ),
        Tool(
            "read_reading",
            "恢复已保存的历史牌面与释义，追问用submit_reading保存，禁止重抽；"
            "本轮尚未提交时返回当前牌面、可引用ref_id与recovery_stage，不重置；"
            "按note继续计算、复用保留事实完成专家报告，或修正后提交。",
            ReadInput,
            read,
            idempotent=False,
            model_result=lambda data: {
                "reading": {
                    k: v
                    for k, v in data["reading"].items()
                    if k
                    in (
                        "reading_id",
                        "question",
                        "status",
                        "recovery_stage",
                        "pending_specialists",
                        "systems",
                        "tarot_json",
                        "kb_version",
                        "output_json",
                        "calculations_json",
                        "chart_id",
                        "bazi_id",
                        "merge",
                        "citable",
                        "note",
                    )
                }
            },
        ),
        Tool(
            "ask_user",
            "信息不足时向用户追问，本轮结束。",
            AskInput,
            ask,
            terminal=True,
            idempotent=False,
            validator=ask_validator,
        ),
        Tool(
            "submit_reading",
            "提交完整解读或保存原牌追问：summary定调并直接回答，sections分层推演，advice行动建议，"
            "closing收尾；evidence仅填ref_id即可由代码渲染事实附录；verdict须与summary第一句一致。",
            Reading,
            submit,
            terminal=True,
            dependency="active_reading_id",
            validator=validate_submit,
        ),
    ]
    if mode == "multi":
        tools.append(
            Tool(
                "merge_signals",
                "合并本记录各体系信号，返回代码计算的共振与张力（主题、时间窗口、两边说法、ref_id）。"
                "两个及以上体系有报告后、submit_reading之前调用；张力必须逐条写进tensions。",
                EmptyInput,
                merge_tool,
                dependency="active_reading_id",
                idempotent=False,
            )
        )
    return tools
