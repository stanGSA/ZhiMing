from __future__ import annotations

import json
import re
import uuid

from common.validation import HIGH_RISK
from harness.models import ModelResponse, ToolCall


class DemoModel:
    """Explicit offline fixture. No network, no claim of LLM interpretation quality."""

    def __init__(self, spread: str | None = None):
        self.spread = spread

    async def chat(self, messages, tools) -> ModelResponse:
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        question = messages[last_user]["content"]
        available = {t["function"]["name"] for t in tools}
        results = []
        for message in messages[last_user + 1 :]:
            if message["role"] == "tool":
                payload = json.loads(message["content"])
                results.append(payload)

        def call(name, arguments):
            if name not in available:
                return ModelResponse(text="离线演示缺少所需工具。")
            return ModelResponse(
                tool_calls=[ToolCall(id=uuid.uuid4().hex, name=name, arguments=arguments)]
            )

        if "submit_report" in available:
            return self.specialist(messages, results, call)
        if re.search(r"第二张|第一张|第三张|第[123]张|这张牌|什么意思|刚才.*牌", question):
            read = next(
                (r["data"].get("reading") for r in results if r["ok"] and "reading" in r["data"]),
                None,
            )
            if not read:
                return call("read_reading", {})
            index = (
                1
                if "第二" in question or "第2" in question
                else 2
                if "第三" in question or "第3" in question
                else 0
            )
            cards = read["tarot_json"]["cards"]
            if index >= len(cards):
                return ModelResponse(text="这次牌阵没有该牌位，请按实际牌位继续问。")
            card = cards[index]
            meaning = card.get("meaning") or next(
                (r["data"]["entry"] for r in results if r["ok"] and "entry" in r["data"]), None
            )
            if not meaning:
                return call(
                    "lookup_meaning",
                    {"system": "tarot", "kind": "card", "key": card["meaning_key"]},
                )
            output = dict(read["output_json"])
            output["summary"] = (
                f"第{index + 1}张是【{card['name']}】{'逆位' if card['reversed'] else '正位'}，表示需要留意{meaning['keywords'][0]}。"
            )
            output["evidence"] = [
                {"ref_id": card["ref_id"], "reading": f"{card['label']}：{meaning['text']}"}
            ]
            return call("submit_reading", output)
        start = next(
            (
                r
                for r in results
                if r["ok"] and "reading_id" in r["data"] and "cards" not in r["data"]
            ),
            None,
        )
        if not start:
            return call("start_reading", {"question": question})
        spread = self.choose_spread(question, start["data"].get("requested_spread"))
        if "consult_specialist" in available:
            return self.orchestrate(question, spread, results, call)
        draw = next((r["data"] for r in results if r["ok"] and "cards" in r["data"]), None)
        if not draw:
            return call("draw_tarot", {"spread": spread, "question": question})
        entries = {
            r["data"]["entry"]["key"]: r["data"]["entry"]
            for r in results
            if r["ok"] and "entry" in r["data"]
        }
        entries.update({c["meaning_key"]: c["meaning"] for c in draw["cards"] if "meaning" in c})
        missing = [card for card in draw["cards"] if card["meaning_key"] not in entries]
        if missing:
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        id=uuid.uuid4().hex,
                        name="lookup_meaning",
                        arguments={"system": "tarot", "kind": "card", "key": card["meaning_key"]},
                    )
                    for card in missing
                ]
            )
        evidence = [
            {
                "ref_id": card["ref_id"],
                "reading": f"{card['label']}：【{card['name']}】"
                f"{'逆位' if card['reversed'] else '正位'}。{entries[card['meaning_key']]['text']}",
            }
            for card in draw["cards"]
        ]
        return call(
            "submit_reading",
            self.submission(question, evidence, draw["spread"], decision_choice(draw)),
        )

    @staticmethod
    def submission(question, evidence, spread, choice) -> dict:
        safety = bool(HIGH_RISK.search(question))
        if safety:
            summary = "这个问题需要现实信息和专业判断，塔罗只能帮助梳理感受，不能据此作出医疗、投资或法律决定。"
        elif spread == "decision":
            summary = f"牌面更支持先核实{choice}的条件，再结合实际成本与目标做选择；这只是按规则生成的离线演示。"
        elif re.search(r"下个月.*跳槽", question):
            summary = "下个月有条件适合跳槽，前提是先核实岗位、薪资和试用期风险；这是离线演示建议。"
        else:
            summary = "建议先梳理现状，再做小步尝试；以下牌面提供反思线索。这是离线演示，尚未进行真实模型解读。"
        return {
            "question_type": "decision"
            if spread == "decision"
            else "timing"
            if re.search(r"下个月.*跳槽", question)
            else "tarot",
            "systems_used": ["tarot"],
            "summary": summary,
            "evidence": evidence,
            "resonances": [],
            "tensions": [],
            "timeline": [],
            "advice": [
                "列出当前选择的实际成本与可验证条件。",
                "先执行一个可撤回的小步骤，再观察反馈。",
            ],
            "confidence": {
                "level": "low",
                "reason": "释义为未人工审核的自写草稿；本次使用离线演示模型。",
            },
            "safety": {
                "flag": safety,
                "note": "请向相关专业人士咨询，不要根据牌面作出高风险决定。" if safety else "",
            },
            "followups": ["第二张牌具体什么意思？"],
        }

    def choose_spread(self, question, requested) -> str:
        return (
            self.spread
            or requested
            or (
                "single"
                if re.search(r"单张|一张", question)
                else "decision"
                if re.search(r"还是|[Aa].*[Bb]|二选一|要不要|该不该", question)
                else "three_card"
            )
        )

    def orchestrate(self, question, spread, results, call) -> ModelResponse:
        """Multi-agent mode: consult the tarot specialist, then write from its report only."""
        report = next(
            (r["data"]["report"] for r in results if r["ok"] and "report" in r["data"]), None
        )
        if report is None:
            return call(
                "consult_specialist",
                {"system": "tarot", "sub_question": question, "spread": spread},
            )
        if report["status"] != "ok":
            return ModelResponse(text="离线演示：塔罗专家没有返回有效报告。")
        evidence = [{"ref_id": p["ref_id"], "reading": p["text"]} for p in report["points"]]
        choice = re.search(r"倾向([AB])", report["answer"])
        return call(
            "submit_reading",
            self.submission(question, evidence, spread, choice[1] if choice else "A"),
        )

    def specialist(self, messages, results, call) -> ModelResponse:
        brief = next(
            json.loads(m["content"])
            for m in messages
            if m["role"] == "user" and m["content"].startswith("{")
        )
        if brief["system"] != "tarot":
            return ModelResponse(text="离线演示只支持塔罗专家。")
        draw = next((r["data"] for r in results if r["ok"] and "cards" in r["data"]), None)
        if not draw:
            spread = brief.get("spread") or self.choose_spread(brief["original_question"], None)
            return call("draw_tarot", {"spread": spread, "question": brief["original_question"]})
        points = [
            {
                "ref_id": card["ref_id"],
                "text": f"{card['label']}：【{card['name']}】"
                f"{'逆位' if card['reversed'] else '正位'}。{card['meaning']['text']}",
            }
            for card in draw["cards"]
        ]
        if draw["spread"] == "decision":
            choice = decision_choice(draw)
            answer = f"牌面更倾向{choice}，前提是先核实{choice}的实际条件；这是离线规则演示。"
        else:
            answer = "牌面提示先梳理现状，再小步尝试；这是离线规则演示。"
        return call(
            "submit_report",
            {
                "answer": answer,
                "points": points,
                "missing": [],
                "confidence": {
                    "level": "low",
                    "reason": "释义为未经人工审核的自写草稿；本次使用离线演示模型。",
                },
            },
        )


def decision_choice(draw) -> str | None:
    if draw["spread"] != "decision":
        return None
    values = [sum(c["meaning"]["theme_map"].values()) for c in draw["cards"][1:]]
    return "A" if values[0] >= values[1] else "B"
