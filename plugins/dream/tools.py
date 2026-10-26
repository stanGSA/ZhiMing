import hashlib
import json
from pathlib import Path

from pydantic import Field

from harness.models import StrictInput
from harness.registry import Tool
from plugins.base import MEANING_FIELDS, Signal, meaning_view
from plugins.dream.match import DreamMatcher
from plugins.dream.validation import validate_output


class DreamSymbol(StrictInput):
    phrase: str = Field(
        min_length=1, max_length=40, description="用户梦境描述中逐字出现的连续原文片段"
    )
    symbol: str = Field(
        min_length=1,
        max_length=12,
        description="由该片段规范化的意象，如片段“牙齿一颗一颗掉下来”→“掉牙”；词典外的词照抄原文",
    )


class DreamInput(StrictInput):
    symbols: list[DreamSymbol] = Field(
        min_length=1,
        max_length=12,
        description="从梦境描述抽出的意象，每项带原文片段；不加入用户没说的内容",
    )


class DreamPlugin:
    name = kb_partition = "dream"
    required_profile = set()
    themes = {"self", "career", "relationship", "finance"}
    eval_dir = Path(__file__).parent / "evals"

    def __init__(self, kb, threshold: float | None = None):
        self.kb = kb
        rule = kb.rules("dream")
        self.matcher = DreamMatcher(kb.db, kb.version, threshold or rule["match_threshold"])
        self.tools = [
            Tool(
                "lookup_dream_symbols",
                "解梦：传入从梦境描述抽出的意象，按同义词表→包含→BM25匹配知识库条目，返回命中与未命中。"
                "未命中的意象不得解读；梦境只反映心理感受，不预言现实事件。",
                DreamInput,
                self.lookup,
                partition="dream",
                roles=frozenset({"orchestrator", "dream"}),
                dependency="active_reading_id",
                validator=self.validate,
                model_result=self.project,
            )
        ]

    def validate_output(self, reading, state):
        return validate_output(reading, state, self.matcher)

    def validate(self, args, session):
        messages = session.user_messages[session.state.get("question_message_index", 0) :]
        for item in args.symbols:
            if not any(item.phrase in message for message in messages):
                return f"原文片段“{item.phrase}”须逐字来自用户的梦境描述"
            if not self.matcher.supported(item.phrase, item.symbol):
                return (
                    f"意象“{item.symbol}”不是原文“{item.phrase}”的规范说法；"
                    "已知意象须由原文写出或明显缩写，词典外的词须照抄原文"
                )
        return None

    @staticmethod
    def project(data):
        return {
            **{k: v for k, v in data.items() if k != "interpretations"},
            "interpretations": [
                dict(
                    ref_id=i["ref_id"],
                    fact=i["fact"],
                    meaning=meaning_view(i["meaning"]),
                )
                for i in data["interpretations"]
            ],
        }

    def extract_signals(self, results):
        rule = self.kb.rules(self.name)
        signals = []
        for result in results:
            for item in result["interpretations"]:
                entry = item["meaning"]
                themes = [t for t, v in entry["theme_map"].items() if v]
                for theme in themes or ["self"]:
                    signals.append(
                        Signal(
                            ref_id=item["ref_id"],
                            system=self.name,
                            theme=theme,
                            valence=entry["theme_map"].get(theme, 0.0),
                            strength=rule["strength"] if themes else 0.0,
                            horizon=rule["horizon"],
                            keywords=tuple(entry["keywords"]),
                            kb_ref=entry["ref_id"],
                            rule_version=rule["version"],
                            review_status=entry["review_status"],
                        )
                    )
        return signals

    def lookup(self, args, session):
        result = self.match_symbols([(item.phrase, item.symbol) for item in args.symbols])
        signals = self.extract_signals([result])
        state = session.state
        old = {s["ref_id"] for s in state["signals"]}
        state["signals"].extend(s.model_dump(mode="json") for s in signals if s.ref_id not in old)
        state["allowed_refs"].update(s.ref_id for s in signals)
        state["kb_refs"].update(s.kb_ref for s in signals)
        state["kb_version"] = self.kb.version
        key = f"dream_result:{result['dream_id']}"
        state[key] = result
        state.setdefault("calculations", {})[key] = result
        return result

    def match_symbols(self, items):
        """Hits, misses and their knowledge entries for (phrase, symbol) pairs; no session."""
        hits, misses = [], []
        for phrase, symbol in items:
            match = {**self.matcher.match(symbol), "phrase": phrase}
            if match["key"] is None:
                if match["query"] not in misses:
                    misses.append(match["query"])
            elif match["key"] not in [h["key"] for h in hits]:
                hits.append(match)
        payload = json.dumps(
            [self.kb.version, [[phrase, symbol] for phrase, symbol in items]], ensure_ascii=False
        )
        dream_id = "dr" + hashlib.sha256(payload.encode()).hexdigest()[:12]
        result = dict(
            dream_id=dream_id,
            hits=hits,
            misses=misses,
            method="synonym → contains → bm25(bigram)+dice; vector fallback disabled",
            threshold=self.matcher.threshold,
            interpretations=[],
        )
        for hit in hits:
            entry = self.matcher.entries[hit["key"]]
            result["interpretations"].append(
                dict(
                    ref_id=f"dream:{dream_id}:{hit['key']}",
                    fact=f"symbol:{hit['key']}",
                    kind="symbol",
                    key=hit["key"],
                    horizon="psyche",
                    timeframe=None,
                    matched_from=hit["query"],
                    phrase=hit["phrase"],
                    meaning={k: entry[k] for k in MEANING_FIELDS},
                )
            )
        for key in (
            ("psyche_only",)
            + (("unmatched",) if misses else ())
            + (("no_symbol",) if not hits else ())
        ):
            entry = self.kb.lookup(self.name, "convention", key)
            result["interpretations"].append(
                dict(
                    ref_id=f"dream:{dream_id}:{key}",
                    fact=f"convention:{key}",
                    kind="convention",
                    key=key,
                    horizon="psyche",
                    timeframe=None,
                    meaning={k: entry[k] for k in MEANING_FIELDS},
                )
            )
        return result
