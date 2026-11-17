"""Bazi pilot r20 findings (docs/verification/p3/bazi-pilot-r20/review-claude.md), fixed in r21.

Known escapes, all passed by every check:

- Investment #2, dated layers: “只用亏得起的小部分去验证判断” and (owner, 2026-11-17) “先补齐应急金、
  核实负债和收入稳定性，再谈是否小额参与”. r12–r20 refused such wordings one by one; the owner
  decided on 2026-11-17 that an investment reading's dated layers and summary offer no entry of any
  amount or pace unless something denies it.
- Luck cycles #3: “再往后到第4步大运己未（……）就是第5步大运”, a step equated with another number.
- Career #3: “首步大运己丑（1998年交运，2008年换下一步）已走到后半段” in 2026 (丁亥 from 2018). The
  timing sheet's only luck-cycle fact was the start and the first cycle (r13, r15, r18 alike); the
  owner decided on 2026-11-17 to fix it at the source and to check a named cycle against the
  sequence, not wording by wording.

Guards next to each change: what still passes (the right value, a denial, another time, the r20
answers that passed) and what is still refused (another item in the sentence, a denial turned
back, an outer negation, a degree word, a double negation, a turn that states it again).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import create_runtime
from pipeline.bazi import TRADE_PROBLEM, Bazi
from plugins.bazi.tools import BaziPlugin
from tests.pipeline.drafts import Composer
from tests.pipeline.test_bazi_pilot_r5 import CASES, has
from tests.pipeline.test_bazi_pilot_r10 import TYPED_PROFILE
from tests.pipeline.test_runner_bazi import aliases, facts_in, written

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/bazi_pilot_r20_review.json").read_text(encoding="utf-8")
)
CLOCK = datetime(2026, 11, 16, 16, 44, tzinfo=UTC)  # the r20 pipeline run
NOW = "写成了现在所处的大运"
ENTRY = "有日期的一层和摘要不能建议投入任何数额"
DATED = "4月到8月：起伏偏大，克制“全押”的念头"


@pytest.fixture
def run_at(project):
    runtimes = []

    async def build(case_id, *drafts):
        case = CASES[case_id]
        composer = Composer(*drafts)
        runtime = create_runtime(
            root=project,
            user_id=f"r21-{case_id}",
            seed=7,
            model=composer,
            mode="pipeline",
            clock=lambda: CLOCK,
        )
        runtimes.append(runtime)
        profile = case.get("profile") or TYPED_PROFILE
        runtime.store.update_profile_fields(f"r21-{case_id}", profile, "合成测试资料")
        runtime.session.profile = runtime.store.get_profile(f"r21-{case_id}")
        runtime.session.refresh_calendar(CLOCK)
        outcome = await runtime.turn(case["question"])
        if outcome.status == "ask_user":
            outcome = await runtime.turn(case["clarification"])
        assert outcome.status == "submit_reading", outcome.text
        return runtime, outcome, composer

    yield build
    for runtime in runtimes:
        runtime.close()


def problems(session, text: str) -> list[str]:
    return Bazi(None).problems([text], session)


def findings(session, title: str, body: str, summary: str = "整体平稳。") -> list[str]:
    args = {"summary": summary, "sections": [{"title": title, "body": body, "ref_ids": []}]}
    return [p for p, _ in Bazi(None).section_findings(args, [], session)]


def traded(found: list[str]) -> bool:
    """Refused as an entry, or by the earlier rule for recommended paces (BATCH_RECOMMENDED)."""
    return entered(found) or TRADE_PROBLEM in found


def entered(found: list[str]) -> bool:
    return any(ENTRY in p for p in found)


@pytest.fixture
async def money(run_at):
    runtime, *_ = await run_at("bazi_pilot_investment_risk", written)
    return runtime.session


@pytest.fixture
async def luck(run_at):
    runtime, *_ = await run_at("bazi_pilot_dayun", written)
    return runtime.session


@pytest.fixture
async def career(run_at):
    runtime, *_ = await run_at("bazi_pilot_next_month_career", written)
    return runtime.session


# ---- an investment reading's dated layers and summary offer no entry --------------------------


@pytest.mark.parametrize("key", ["trial", "later"])
async def test_the_r20_entries_in_dated_layers_are_refused(money, key):
    assert entered(findings(money, FIXTURE[f"{key}_title"], FIXTURE[key]))


@pytest.mark.parametrize(
    "body",
    [
        "这段时间可以少量参与。",
        "建议拿出一小部分资金试水。",
        "这段时间适合用小额去验证判断。",
        "先核实收入，然后再考虑投入。",
        "等应急金补齐后，才谈得上参与。",
        "这段时间以分散配置为主。",
        "可以考虑定投。",
        "这几个月适合轻仓入场。",
        # Another item in the sentence.
        "先核实财务，再少量买入。",
        # A denial, then the entry stated.
        "不是全投，而是分批买入。",
        # An outer negation.
        "不能说不建议分批买入。",
        # A degree word inserted.
        "这段时间更加适合小额参与。",
        # A double negation.
        "并非不能小额参与。",
        # A turn that states it again.
        "不要急着买入，但可以少量试水。",
        # A plain denial turned back.
        "不能说不参与。",
        "这段时间不是说你不能参与市场，而是别全押。",
        # A description, then a recommendation in its own clause.
        "容易被消息带动，可以先少量试水。",
    ],
)
async def test_entries_in_a_dated_layer_are_refused(money, body):
    assert traded(findings(money, DATED, body)), body


@pytest.mark.parametrize(
    "body",
    [
        "这段时间不建议分批买入。",
        "别急着加仓。",
        "不要拿积蓄去试水。",
        "如果你正想分批买入，先停下来核对预算。",
        "容易被人拉着一同加码。",
        "要不要分批，取决于你的承受能力。",
        "比小额试水更重要的是先留足应急金。",
        "小额参与也不合适。",
        "先核实收入和负债，做好预算，留足应急金。",
        "大额投入前先核实清楚。",
        "把应急金单独留出一部分。",
        "这个月注意力容易分散。",
        "这段时间适合补理财知识，暂缓做决定。",
        # A plain denial; impulses and temptations described; an entry held back.
        "把不能亏的钱划出来，它不参与任何行情。",
        "市场消息多，手一快就加仓。",
        "最典型的表现就是：听朋友一句推荐就加仓、看到别人赚了就追。",
        "容易表现成听到消息就想动，或者把钱分散到好几个听来的“机会”里。",
        "那种“再不上车就晚了”的感觉会格外强。",
        "若你正被周围人带动，先设一个冷静期，任何加码决定都推迟几天再谈。",
        "建议把重大加仓动作往后放一放。",
        "身边亲友对钱的话题参与变多。",
    ],
)
async def test_restraint_in_a_dated_layer_passes(money, body):
    assert not traded(findings(money, DATED, body)), body


async def test_the_r20_layers_without_an_entry_pass(money):
    for layer in FIXTURE["investment_layers"]:
        flagged = [
            sentence
            for problem, sentence in Bazi(None).section_findings(
                {"summary": "整体平稳。", "sections": [{**layer, "ref_ids": []}]}, [], money
            )
            if ENTRY in problem or problem == TRADE_PROBLEM
        ]
        expected = [FIXTURE[k] for k in ("trial", "later") if FIXTURE[k] in layer["body"]]
        assert flagged == expected, layer["case"] + layer["title"]


async def test_an_entry_in_the_summary_is_refused(money):
    found = findings(money, "这段时间的节奏", "先核实。", summary="明年适合小额参与，先核实财务。")
    assert entered(found)
    for summary in FIXTURE["investment_summaries"]:
        assert not traded(findings(money, "这段时间的节奏", "先核实。", summary=summary))


async def test_an_undated_layer_is_left_to_the_other_checks(money):
    assert not traded(findings(money, "你的财务底色", "可以少量参与。"))


async def test_the_sheet_states_the_rule(run_at):
    _, _, composer = await run_at("bazi_pilot_investment_risk", written)
    sheet = composer.seen[0][0][1]["content"]
    assert "摘要和写了时间的每一层都不建议投入任何数额" in sheet


async def test_an_entry_is_repaired_before_submission(run_at):
    def trial(messages):
        draft = written(messages)
        return draft.replace(
            "提示你把精力放在长期目标上。", "提示你只用亏得起的小部分去验证判断。", 1
        )

    _, outcome, composer = await run_at("bazi_pilot_investment_risk", trial, written)
    assert len(composer.seen) == 2
    assert entered(outcome.data["pipeline"]["problems"][0])


# ---- a named cycle read as a stage of the sequence --------------------------------------------


async def test_the_r20_first_cycle_as_now_is_refused(career):
    assert has(problems(career, FIXTURE["first_as_now"]), NOW)


@pytest.mark.parametrize(
    "text",
    [
        "首步大运己丑已走到后半段。",
        "你目前在第1步大运己丑的后半段。",
        "第2步大运戊子正处在中段。",
        # Another item in the sentence.
        "流年丙午主竞争，首步大运己丑已走到后半段。",
        # An outer negation.
        "不能说现在不在首步大运己丑。",
        # A degree word.
        "现在不完全是首步大运己丑这一步。",
        # A turn that states it again.
        "现在不是首步大运己丑，但其实还是首步大运己丑。",
    ],
)
async def test_another_cycle_as_now_is_refused(career, text):
    assert has(problems(career, text), NOW), text


@pytest.mark.parametrize(
    "text",
    [
        "首步大运己丑早已过去。",
        "1998年6月26日起运（出生后7年4个月0天），首步大运己丑（1998年交运，2008年换下一步）。",
        "现在走的是第3步大运丁亥，已走到后半段。",
        "现在不是首步大运己丑。",
        "首步大运己丑之后，又走了戊子。",
        "首步大运己丑、现在的第3步大运丁亥都带着学习的主题。",
        "第3步大运丁亥（2018年交运，2028年换下一步）已走到后半段。",
    ],
)
async def test_the_current_or_another_time_passes(career, text):
    assert not has(problems(career, text), NOW), text


async def test_the_r20_answers_without_that_error_pass(career, luck, run_at):
    trait, *_ = await run_at("bazi_pilot_trait", written)
    for section in FIXTURE["career_sections"]:
        assert not has(problems(career, section["body"]), NOW), section["case"]
    for section in FIXTURE["luck_sections"]:
        session = luck if section["case"].startswith("bazi_pilot_dayun") else trait.session
        found = problems(session, section["body"])
        assert not has(found, NOW) and not has(found, "不是第"), section["case"]


async def test_the_r20_step_equated_with_another_is_refused(luck):
    assert has(problems(luck, FIXTURE["equated_step"]), "第4步大运是己未，不是第5步")


@pytest.mark.parametrize(
    "text, words",
    [
        ("第4步大运己未就是第5步。", "不是第5步"),
        ("第2步大运丁巳即第3步大运。", "不是第3步"),
        ("第4步大运己未（2023年交运，2033年换下一步）也就是第5步大运。", "不是第5步"),
    ],
)
async def test_steps_equated_with_another_are_refused(luck, text, words):
    assert has(problems(luck, text), words), text


@pytest.mark.parametrize(
    "text",
    [
        "第1步大运丙辰（1993年交运，2003年换下一步）是第1步。",
        "第4步大运己未之后是第5步大运庚申。",
        "第4步大运己未不是第5步。",
    ],
)
async def test_a_step_equated_with_itself_or_denied_passes(luck, text):
    assert not has(problems(luck, text), "不是第"), text


# ---- the current cycle is a fact of its own --------------------------------------------------


@pytest.mark.parametrize(
    "case_id, text",
    [
        ("bazi_pilot_next_month_career", "第3步大运丁亥（2018年交运，2028年换下一步）"),
        ("bazi_pilot_trait", "第3步大运己巳（2017年交运，2027年换下一步）"),
    ],
)
async def test_timing_and_trait_sheets_give_the_current_cycle(run_at, case_id, text):
    _, _, composer = await run_at(case_id, written)
    facts = facts_in(composer.seen[0][0])
    assert [t for _, label, t in facts if label == "当前大运"] == [text]
    # The start keeps its own fact, the only one labelled 大运.
    assert len([a for a, label, _ in facts if label == "大运"]) == 1


async def test_the_luck_cycle_sheet_and_the_model_result_are_unchanged(run_at):
    _, _, composer = await run_at("bazi_pilot_dayun", written)
    labels = {t: label for _, label, t in facts_in(composer.seen[0][0])}
    assert labels["第4步大运己未（2023年交运，2033年换下一步）"] == "大运"
    assert "当前大运" not in labels.values()
    runtime, _, _ = await run_at("bazi_pilot_next_month_career", written)
    # The chart result the model reads keeps its facts, so every R-number stays as it was.
    chart = runtime.session.state["bazi_result"]
    assert any(i["fact"].startswith("dayun_current:") for i in chart["interpretations"])
    shown = BaziPlugin.project(chart)["interpretations"]
    assert shown and not any(i["fact"].startswith("dayun_current:") for i in shown)


def citing(label: str, extra: str):
    def draft(messages):
        (alias,) = aliases(messages, label)
        return written(messages, extra=f"{{{{{alias}}}}}{extra}")

    return draft


async def test_the_current_cycle_cited_as_now_is_accepted_first(run_at):
    _, _, composer = await run_at(
        "bazi_pilot_next_month_career", citing("当前大运", "已走到后半段。")
    )
    assert len(composer.seen) == 1


async def test_the_start_cited_as_now_is_repaired(run_at):
    _, outcome, composer = await run_at(
        "bazi_pilot_next_month_career", citing("大运", "已走到后半段。"), written
    )
    assert len(composer.seen) == 2
    assert any(NOW in p for p in outcome.data["pipeline"]["problems"][0])
