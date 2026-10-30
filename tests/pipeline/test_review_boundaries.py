"""The boundaries PR #35's review found open, each with the review's own counterexample."""

import pytest

from app import create_runtime
from common.validation import HIGH_RISK, RISKS, risk_note
from harness.models import ModelResponse
from pipeline.render import safety_for
from tests.pipeline.drafts import QUESTION, Composer, cards_in, followup_answer, good

RISKY = "只用塔罗三张牌帮我反思：是否应该把积蓄全部买入一只股票？"
DECISION = "A是留在当前公司，B是接受新offer，只用塔罗二选一牌阵看看。"


@pytest.fixture
def make(project):
    runtimes = []

    def build(*drafts, user_id="boundary-user"):
        composer = Composer(*drafts)
        runtime = create_runtime(
            root=project, user_id=user_id, seed=42, model=composer, mode="pipeline"
        )
        events = []
        runtime.tracer.listeners.append(events.append)
        runtimes.append(runtime)
        return runtime, composer, events

    yield build
    for runtime in runtimes:
        runtime.close()


def seated(where: str, alias_index: int, form: str):
    """A good draft plus one sentence that seats the card of ``alias_index`` at ``where``."""

    def draft(messages):
        alias = list(cards_in(messages))[alias_index]
        sentence = form.format(where=where, card=f"{{{{{alias}}}}}")
        return good(messages).replace("【建议】", f"【分层】补充\n{sentence}\n【建议】", 1)

    return draft


# ---- 1. a placeholder in the wrong position ----------------------------------------------


@pytest.mark.parametrize(
    "form",
    ["{where}位的{card}很关键。", "{card}落在{where}位，提醒你放慢。", "{where}位上是{card}。"],
)
async def test_a_placeholder_seated_in_another_position_is_repaired(make, form):
    runtime, composer, _ = make(seated("现在", 0, form), good)
    outcome = await runtime.turn(QUESTION)
    info = outcome.data["pipeline"]
    assert info["repairs"] == 1, info
    assert "现在位是【" in info["problems"][0][0]
    # The repair names each number with its position.
    assert "R2=现在位【" in composer.seen[1][0][-1]["content"]


async def test_a_placeholder_in_its_own_position_passes(make):
    runtime, _, _ = make(seated("现在", 1, "{where}位置上的{card}提醒你放慢。"))
    outcome = await runtime.turn(QUESTION)
    assert outcome.data["pipeline"]["repairs"] == 0


async def test_decision_positions_are_checked(make):
    runtime, _, _ = make(seated("选 A", 2, "A选项的{card}说明了它的代价。"), good)
    outcome = await runtime.turn(DECISION)
    assert outcome.data["pipeline"]["repairs"] == 1
    assert "选 A位是【" in outcome.data["pipeline"]["problems"][0][0]


# ---- 2. routing: other systems and new questions ---------------------------------------


async def test_another_system_after_tarot_goes_to_the_agent_loop(make):
    reply = ModelResponse(text="请告诉我你的出生时间。", input_tokens=10, output_tokens=5)
    runtime, composer, events = make(good, reply)
    await runtime.turn(QUESTION)
    events.clear()
    outcome = await runtime.turn("请用八字解释日主是什么意思？")
    assert outcome.status == "text"
    assert composer.seen[-1][1], "the agent loop offers its tools"
    assert not [e for e in events if e["event"] == "pipeline_stage"]


@pytest.mark.parametrize("same_session", [True, False])
async def test_a_new_tarot_question_is_not_a_follow_up(make, same_session):
    runtime, _, _ = make(good, good)
    first = await runtime.turn(QUESTION)
    target = runtime if same_session else make(good)[0]
    outcome = await target.turn("请用塔罗看看我刚才面试的结果。")
    assert outcome.data["pipeline"]["kind"] == "new"
    assert outcome.data["reading_id"] != first.data["reading_id"]


# ---- 3, 4. safety of follow-ups and one rule for risk ------------------------------------


async def test_a_follow_up_to_a_high_risk_question_carries_its_safety_note(make):
    runtime, _, _ = make(good, followup_answer)
    await runtime.turn(RISKY)
    outcome = await runtime.turn("第二张牌具体什么意思？不要重新抽牌。")
    assert outcome.status == "submit_reading", outcome.text
    assert outcome.data["pipeline"]["repairs"] == 0
    safety = outcome.data["reading"]["safety"]
    assert safety["flag"] and "投资建议" in safety["note"]


def test_recognising_a_risk_and_writing_its_note_share_one_rule():
    question = "只用塔罗看看，我要不要借钱去做期货？"
    assert HIGH_RISK.search(question)
    assert safety_for(question) == {"flag": True, "note": risk_note(question)}
    assert "投资建议" in risk_note(question)
    for _, pattern, _ in RISKS:
        for word in pattern.split("|"):
            assert risk_note(f"关于{word}的问题") and HIGH_RISK.search(word), word


async def test_a_draft_that_keeps_failing_a_safety_rule_ends_in_a_safety_reply(make):
    def certain(messages):
        return good(messages).replace(
            "近期事业整体平稳，可以按计划推进。", "现在全部买入一定会赚钱。"
        )

    runtime, _, _ = make(certain, certain)
    outcome = await runtime.turn(RISKY)
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["degraded"] == "safety"
    reading = outcome.data["reading"]
    assert reading["sections"] == [] and "不根据牌面给出判断" in reading["summary"]
    assert reading["safety"]["flag"]


# ---- 5. the model boundary: budget and missing usage ------------------------------------


async def test_an_exhausted_budget_writes_the_reading_by_code(make):
    runtime, composer, events = make(good)
    runtime.token_budget = 0
    outcome = await runtime.turn(QUESTION)
    assert composer.seen == [], "no model call beyond the budget"
    assert any(e["event"] == "budget_denied" for e in events)
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["degraded"] == "keywords"


async def test_a_response_without_usage_is_not_used(make):
    def unmetered(messages):
        return ModelResponse(text=good(messages), usage_available=False)

    runtime, _, _ = make(unmetered)
    outcome = await runtime.turn(QUESTION)
    assert outcome.status == "usage_unavailable"
    user = runtime.session.user_id
    assert runtime.store.recent_readings(user) == []
    assert runtime.store.unfinished_pipeline_run(user)["stage"] == "computed"


# ---- 6. how a reading was written is kept with it ---------------------------------------


async def test_repairs_and_degrading_are_saved_with_the_reading(make):
    runtime, _, _ = make("没有格式。", "还是没有格式。", followup_answer)
    first = await runtime.turn(QUESTION)
    user = runtime.session.user_id
    saved = runtime.store.get_reading(user, first.data["reading_id"])
    assert saved["pipeline_json"]["degraded"] == "keywords"
    assert saved["pipeline_json"]["repairs"] == 1
    second = await runtime.turn("第二张牌具体什么意思？不要重新抽牌。")
    response = runtime.store.get_response(user, second.data["response_id"])
    assert response["pipeline_json"]["kind"] == "followup"
    assert response["pipeline_json"]["degraded"] is None
    (exported,) = runtime.store.export_user(user)["readings"]
    assert exported["pipeline"]["degraded"] == "keywords"
    assert exported["responses"][0]["pipeline"]["kind"] == "followup"
    # The agent loop's readings carry no pipeline record.
    assert "pipeline_run" not in runtime.session.state


async def test_a_run_stopped_after_a_failed_draft_resumes_at_its_repair(make):
    runtime, _, _ = make("没有格式。", RuntimeError("connection reset"))
    await runtime.turn(QUESTION)
    run = runtime.store.unfinished_pipeline_run(runtime.session.user_id)
    assert run["stage"] == "composed" and run["state"]["drafts"] == ["没有格式。"]
    later, composer, events = make(good)
    outcome = await later.turn("继续")
    assert outcome.status == "submit_reading"
    # One call, the repair: the failed draft was not written again.
    assert [e["purpose"] for e in events if e["event"] == "model_response"] == ["repair"]
    assert "格式：缺少【摘要】" in composer.seen[0][0][-1]["content"]
    assert outcome.data["pipeline"]["repairs"] == 1
