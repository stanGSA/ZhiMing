from pathlib import Path
from typing import Literal

from pydantic import Field

from harness.models import StrictInput
from harness.registry import Tool
from knowledge.kb import KnowledgeBase
from plugins.base import MEANING_FIELDS, Signal
from plugins.tarot.draw import draw_tarot, valid_picks
from plugins.tarot.validation import validate_output


class DrawInput(StrictInput):
    spread: Literal["single", "three_card", "decision"]
    question: str = Field(min_length=1, max_length=2000)


def check_spread(args: DrawInput, session) -> str | None:
    if session.state.get("requested_spread") and args.spread != session.state["requested_spread"]:
        return "必须使用用户明确指定的牌阵"
    picks = session.state.get("picks")
    if picks and not valid_picks(picks, args.spread):
        return f"用户已从牌堆中选了{len(picks)}张牌，牌阵须与之相符"
    return None


class TarotPlugin:
    validate_output = staticmethod(validate_output)

    name = "tarot"
    required_profile = set()
    themes = {"career", "relationship", "self", "finance"}
    kb_partition = "tarot"
    eval_dir = Path(__file__).parent / "evals"

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        self.tools = [
            Tool(
                "draw_tarot",
                "抽塔罗牌：单张、过去现在未来三张、A/B 决策三张。本次只允许抽一次。",
                DrawInput,
                self.draw,
                roles=frozenset({"orchestrator", "tarot"}),
                partition="tarot",
                dependency="active_reading_id",
                exclusive_key="tarot_drawn",
                validator=check_spread,
                model_result=lambda data: {k: v for k, v in data.items() if k != "signals"},
            )
        ]

    def extract_signals(self, results: list[dict]) -> list[Signal]:
        signals = []
        rule = self.kb.rules("tarot")
        for result in results:
            for card in result["cards"]:
                orientation = "reversed" if card["reversed"] else "upright"
                entry = self.kb.lookup("tarot", "card", f"{card['card_id']}:{orientation}")
                if entry is None:
                    raise ValueError("牌面缺少释义")
                ref = (
                    f"tarot:{result['reading_id']}:pos{card['pos']}:{card['card_id']}:{orientation}"
                )
                for theme, valence in entry["theme_map"].items():
                    signals.append(
                        Signal(
                            ref_id=ref,
                            system="tarot",
                            theme=theme,
                            valence=valence,
                            strength=rule["position_strength"][result["spread"]][card["pos"] - 1],
                            horizon=rule["horizon"],
                            keywords=tuple(entry["keywords"]),
                            kb_ref=entry["ref_id"],
                            rule_version=rule["version"],
                            review_status=entry["review_status"],
                        )
                    )
        return signals

    def draw(self, args: DrawInput, session) -> dict:
        result = draw_tarot(
            args.spread, args.question, session.state["seed"], session.state.get("picks")
        )
        result["reading_id"] = session.state["active_reading_id"]
        result["kb_version"] = self.kb.version
        signals = self.extract_signals([result])
        for card in result["cards"]:
            orientation = "reversed" if card["reversed"] else "upright"
            card["meaning_key"] = f"{card['card_id']}:{orientation}"
            card["ref_id"] = f"tarot:{result['reading_id']}:pos{card['pos']}:{card['meaning_key']}"
            entry = self.kb.lookup("tarot", "card", card["meaning_key"])
            card["meaning"] = {k: entry[k] for k in MEANING_FIELDS}
            session.state["kb_refs"].add(entry["ref_id"])
        session.state["tarot_result"] = result
        session.state["signals"].extend(signal.model_dump(mode="json") for signal in signals)
        session.state["allowed_refs"].update(s.ref_id for s in signals)
        session.state["facts"].extend(c["name"] for c in result["cards"])
        session.state["kb_version"] = self.kb.version
        return {**result, "signals": session.state["signals"]}
