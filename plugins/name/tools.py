from pathlib import Path

from pydantic import Field

from common.time_utils import NeedsInput
from harness.models import StrictInput, ToolResult
from harness.registry import Tool
from plugins.base import Signal
from plugins.context import MeaningPlugin
from plugins.name.strokes import UnihanMissing
from plugins.name.validation import ambiguity_prompt, validate_output
from plugins.name.wuge import COMPOUND_SURNAMES, ELEMENTS, GRIDS, analyze, shuli

HAN = r"[㐀-䶿一-鿿豈-﫿]"


class NameInput(StrictInput):
    surname: str = Field(min_length=1, max_length=2, description="姓；复姓如欧阳为两个字")
    given: str = Field(min_length=1, max_length=3, description="名")
    forms: dict[str, str] = Field(
        default_factory=dict,
        description='可选：用户确认的写法，如{"杰":"傑"}；只在用户明确说明写法时填写',
    )
    bazi_id: str | None = Field(
        default=None, description="可选：本记录已计算的八字编号，用于并列五行计数"
    )


class NamePlugin(MeaningPlugin):
    validate_output = staticmethod(validate_output)

    name = kb_partition = "name"
    id_key = "name_id"
    required_profile = set()
    themes = {"self", "career", "relationship", "finance"}
    eval_dir = Path(__file__).parent / "evals"

    def __init__(self, kb, store):
        self.kb, self.store = kb, store
        self.tools = [
            Tool(
                "analyze_name",
                "姓名五格：康熙笔画、天人地外总五格与81数理、三才五行；有本记录bazi_id时并列原局五行计数。"
                "两个名字各调用一次。有多种写法的字返回默认值与备选，须向用户说明；查不到的字返回needs_input。",
                NameInput,
                self.analyze,
                partition="name",
                roles=frozenset({"orchestrator", "name"}),
                dependency="active_reading_id",
                validator=self.validate,
                model_result=self.project,
            )
        ]

    @staticmethod
    def validate(args, session):
        import re

        full = args.surname + args.given
        if not re.fullmatch(f"{HAN}+", full):
            return "姓名只能包含汉字"
        text = " ".join(session.user_messages)
        if full not in text and full != session.profile.get("name"):
            return "姓名必须来自用户原话或画像，不能猜测或改写"
        if len(args.surname) == 2 and args.surname not in COMPOUND_SURNAMES and "复姓" not in text:
            return "双字姓须是常见复姓或由用户说明是复姓"
        if (
            len(args.surname) == 1
            and len(args.given) >= 2
            and args.surname + args.given[0] in COMPOUND_SURNAMES
            and not re.search(r"不是复姓|单姓", text)
        ):
            return (
                f"疑似复姓“{args.surname + args.given[0]}”，请按复姓拆分；用户说明是单姓时再按单姓"
            )
        for char, form in args.forms.items():
            if char not in full:
                return "forms只能确认本名字中的字"
            if form == char:
                if not re.search(r"原字|本字|简体|不(?:用|转|写)繁体|就写", text):
                    return f"保留“{char}”本字计算须有用户原话确认"
            elif form not in text:
                return f"写法“{form}”须由用户原话确认"
        if args.bazi_id and args.bazi_id != session.state.get("bazi_id"):
            return "bazi_id须是本记录已计算的八字"
        return None

    @staticmethod
    def project(data):
        if data.get("status") == "needs_input":
            return data
        result = {k: v for k, v in data.items() if k not in ("interpretations",)}
        result["chars"] = [
            {k: c[k] for k in ("char", "role", "form", "strokes", "alternatives", "notes")}
            for c in data["chars"]
        ]
        result["interpretations"] = [
            dict(
                ref_id=i["ref_id"],
                fact=i["fact"],
                meaning=dict(text=i["meaning"]["text"], reviewed=i["meaning"]["reviewed"]),
            )
            for i in data["interpretations"]
        ]
        return result

    def compound_keys(self, result, kind, key, fact):
        if kind == "shuli":
            return [("grid", fact.split(":")[0])]
        if kind == "sancai":
            return [("element", element) for element in dict.fromkeys(key)]
        return []

    def extract_signals(self, results):
        rule = self.kb.rules(self.name)
        signals = []
        for result in results:
            for item in result["interpretations"]:
                entry = self.kb.lookup(self.name, item["kind"], item["key"])
                if item["kind"] == "shuli":
                    grid = item["fact"].split(":")[0]
                    themes = rule["grid_themes"][grid]
                    strength = rule["strength"].get(grid, 0.0)
                elif item["kind"] == "sancai":
                    themes = [t for t, v in entry["theme_map"].items() if v]
                    strength = rule["strength"]["sancai"]
                else:
                    themes, strength = [], 0.0
                strength = min(strength, rule["max_strength"])
                # A fact without a directional theme is still citable as a neutral signal.
                for theme in themes or ["self"]:
                    signals.append(
                        Signal(
                            ref_id=item["ref_id"],
                            system=self.name,
                            theme=theme,
                            valence=entry["theme_map"].get(theme, 0.0) if themes else 0.0,
                            strength=strength if themes else 0.0,
                            horizon=rule["horizon"],
                            keywords=tuple(entry["keywords"]),
                            kb_ref=entry["ref_id"],
                            kb_refs=tuple(item["meaning"]["component_refs"]),
                            rule_version=rule["version"],
                            reviewed=item["meaning"]["reviewed"],
                        )
                    )
        return signals

    def analyze(self, args, session):
        try:
            result = analyze(args.surname, args.given, args.forms)
        except UnihanMissing as exc:
            return ToolResult.failure("data_missing", str(exc))
        except ValueError as exc:
            return ToolResult.failure("validation_failed", str(exc))
        if result["status"] != "ok":
            chars = "、".join(f"“{c}”" for c in result["unknown"])
            return NeedsInput(
                "unknown_name_char",
                f"无法确定{chars}的康熙笔画，请确认这个字的写法（可提供繁体或常用异体）；不会猜测笔画。",
                result["unknown"],
            ).result()
        result["confirmation_prompts"] = [
            ambiguity_prompt(result, item) for item in result["ambiguities"]
        ]
        if args.bazi_id:
            chart = self.store.get_calculation("bazi", session.user_id, args.bazi_id)
            if not chart:
                return ToolResult.failure("ownership_denied", "bazi_id不属于当前用户")
            counts = dict.fromkeys(ELEMENTS, 0)
            for element in result["sancai"]["key"]:
                counts[element] += 1
            result["bazi_comparison"] = dict(
                bazi_id=args.bazi_id,
                sancai_element_count=counts,
                bazi_wuxing_count=chart.get("wuxing_count"),
                day_master=chart.get("day_master"),
                note="只并列三才五行与原局天干地支五行计数；不判喜用神，不建议据此改名或补五行",
            )
        atoms = [
            (
                f"{grid}:{result['grids'][grid]}",
                "shuli",
                str(shuli(result["grids"][grid])),
                "trait",
                None,
            )
            for grid in GRIDS
        ]
        atoms.append(
            (f"三才:{result['sancai']['key']}", "sancai", result["sancai"]["key"], "trait", None)
        )
        atoms.append(("笔画规则", "convention", "stroke_rule", "trait", None))
        if result["compound_surname"]:
            atoms.append(("复姓", "convention", "compound_surname", "trait", None))
        for item in result["ambiguities"]:
            atoms.append((f"写法:{item['char']}", "convention", "ambiguous_form", "trait", None))
        if args.bazi_id:
            atoms.append(("八字对照", "convention", "bazi_compare", "trait", None))
        return self.attach(result, atoms, session, f"name_result:{result['name_id']}")
