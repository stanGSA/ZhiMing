"""Post-merge regressions: recovery, source semantics and visible disclosures."""

import pytest

from common.tools import render_reading
from plugins.daily.tools import requested_date
from tests.test_week6 import ask, with_birth
from tests.test_week6_review import EXPLAIN, submission
from tests.test_week23_integration import invoke

ANCHOR = "2026-10-14"


@pytest.mark.parametrize("correction", ["刚才写错了，改成2026-02-28。", "2026-02-28"])
async def test_invalid_daily_date_can_be_corrected_in_same_reading(runtime, correction):
    runtime.session.calendar_anchor = ANCHOR
    with_birth(runtime)
    await ask(runtime, "帮我看2026-02-30的运势")
    identity = runtime.session.state["active_reading_id"]
    rejected = await invoke(runtime, "daily_fortune", {"date": "2026-02-28"})
    assert not rejected.ok and "不存在" in rejected.error
    runtime.session.append_user(correction)
    result = await invoke(runtime, "daily_fortune", {"date": "2026-02-28"})
    assert result.ok and result.data["date"] == "2026-02-28"
    assert runtime.session.state["active_reading_id"] == identity


async def test_latest_date_correction_wins_even_in_one_message(runtime):
    runtime.session.calendar_anchor = ANCHOR
    with_birth(runtime)
    await ask(runtime, "看2026-02-30，不对，改成2026-02-28的运势。")
    assert (await invoke(runtime, "daily_fortune", {"date": "2026-02-28"})).ok
    runtime.session.append_user("改成2026-02-31。")
    rejected = await invoke(runtime, "daily_fortune", {"date": "2026-02-28"})
    assert not rejected.ok and "不存在" in rejected.error


async def test_incidental_today_keeps_daily_target_and_explicit_change_updates_it(runtime):
    runtime.session.calendar_anchor = ANCHOR
    with_birth(runtime)
    await ask(runtime, "明天运势怎么样？")
    assert (await invoke(runtime, "daily_fortune", {"date": "2026-10-15"})).ok
    runtime.session.append_user("不用重算，我今天只是想问刚才那张牌。")
    assert requested_date(runtime.session) == "2026-10-15"
    runtime.session.append_user("我今天补充一下，出生于1996-05-10 08:30。")
    assert requested_date(runtime.session) == "2026-10-15"
    runtime.session.append_user("不要改成今天。")
    assert requested_date(runtime.session) == "2026-10-15"
    runtime.session.append_user("那改成后天呢？")
    assert requested_date(runtime.session) == "2026-10-16"


async def dream_lookup(runtime, message, *pairs):
    await ask(runtime, message)
    return await invoke(
        runtime,
        "lookup_dream_symbols",
        {"symbols": [{"phrase": phrase, "symbol": symbol} for phrase, symbol in pairs]},
    )


@pytest.mark.parametrize(
    "phrase,symbol",
    [("手机飛到我手里", "飞机"), ("手机飞到我手里", "飞机"), ("火烧到车旁边", "火车")],
)
async def test_literal_phrase_does_not_justify_reassembled_noun(runtime, phrase, symbol):
    result = await dream_lookup(runtime, "梦见" + phrase, (phrase, symbol))
    assert not result.ok and "不是原文" in result.error
    assert not runtime.session.state["signals"]


@pytest.mark.parametrize(
    "phrase,symbol",
    [("牙齿一颗一颗掉下来", "掉牙"), ("被一条大狗追", "被追"), ("一条大狗", "狗")],
)
async def test_controlled_dream_normalisations_still_work(runtime, phrase, symbol):
    result = await dream_lookup(runtime, "梦见" + phrase, (phrase, symbol))
    assert result.ok and [h["key"] for h in result.data["hits"]] == [symbol]


@pytest.mark.parametrize(
    "summary",
    [
        "无人机未收录，但蛇象征变化。",
        "无人机未收录但蛇象征变化。",
        "蛇象征变化，无人机未收录。",
        "蛇的出现象征变化。",
        "蛇这个形象通常代表变化。",
        "「大蛇」代表变化，无人机未收录。",
    ],
)
async def test_unmatched_notice_does_not_exempt_another_symbol(runtime, summary):
    result = await dream_lookup(runtime, "梦见狗和无人机。", ("狗", "狗"), ("无人机", "无人机"))
    ref = result.data["interpretations"][0]["ref_id"]
    value = submission("dream", [{"ref_id": ref, "reading": "狗代表陪伴。"}], summary)
    submitted = await invoke(runtime, "submit_reading", value)
    assert not submitted.ok and "不是本次命中" in submitted.error
    assert not runtime.store.get_reading(
        runtime.session.user_id, runtime.session.state["active_reading_id"]
    )


@pytest.mark.parametrize(
    "summary",
    ["无人机未收录，不作解读；狗代表陪伴。", "蛇这次不在描述里，不作解读；狗代表陪伴。"],
)
async def test_scoped_abstention_and_grounded_interpretation_are_allowed(runtime, summary):
    result = await dream_lookup(runtime, "梦见狗和无人机。", ("狗", "狗"), ("无人机", "无人机"))
    ref = result.data["interpretations"][0]["ref_id"]
    submitted = await invoke(
        runtime,
        "submit_reading",
        submission("dream", [{"ref_id": ref, "reading": "狗代表陪伴。"}], summary),
    )
    assert submitted.ok


async def name_draft(runtime):
    await ask(runtime, "帮我看赵杰这个名字。")
    result = await invoke(runtime, "analyze_name", {"surname": "赵", "given": "杰"})
    return submission(
        "name",
        [{"ref_id": result.data["interpretations"][1]["ref_id"], "reading": "人格26。"}],
        "赵杰人格26，体现成长的可能。",
    )


@pytest.mark.parametrize("hidden", ["confidence", "safety", "followups", "resonances"])
async def test_name_disclosure_must_be_in_rendered_text(runtime, hidden):
    value = await name_draft(runtime)
    if hidden == "confidence":
        value[hidden] = {"level": "low", "reason": EXPLAIN}
    elif hidden == "safety":
        value[hidden] = {"flag": False, "note": EXPLAIN}
    else:
        value[hidden] = [EXPLAIN]
    submitted = await invoke(runtime, "submit_reading", value)
    assert not submitted.ok and "多种写法" in submitted.error
    value["advice"] = [EXPLAIN]
    accepted = await invoke(runtime, "submit_reading", value)
    assert accepted.ok and EXPLAIN in accepted.data["text"]
    stored = runtime.store.get_reading(runtime.session.user_id, accepted.data["reading_id"])
    assert EXPLAIN in render_reading(stored["output_json"])


@pytest.mark.parametrize(
    "explanation",
    [
        "杰的笔画已经确认，王12画，李8画。",
        "杰默认傑12画，王8画，请确认。",
        "杰默认傑12画，原字杰8画，写法已经确认。",
        "杰默认按杰8画，备选傑12画，请确认。",
    ],
)
async def test_name_disclosure_binds_forms_counts_and_pending_confirmation(runtime, explanation):
    value = await name_draft(runtime)
    value["advice"] = [explanation]
    submitted = await invoke(runtime, "submit_reading", value)
    assert not submitted.ok and "多种写法" in submitted.error


async def test_confirmed_name_form_no_longer_requires_disclosure(runtime):
    await ask(runtime, "我叫赵杰，证件写的是原字杰，不用繁体。")
    result = await invoke(
        runtime, "analyze_name", {"surname": "赵", "given": "杰", "forms": {"杰": "杰"}}
    )
    ref = result.data["interpretations"][1]["ref_id"]
    value = submission("name", [{"ref_id": ref, "reading": "人格22。"}], "赵杰人格22。")
    assert (await invoke(runtime, "submit_reading", value)).ok


async def test_calculated_confirmation_prompt_is_visible_after_submission(runtime):
    await ask(runtime, "帮我看赵杰这个名字。")
    result = await invoke(runtime, "analyze_name", {"surname": "赵", "given": "杰"})
    value = submission(
        "name",
        [{"ref_id": result.data["interpretations"][1]["ref_id"], "reading": "人格26。"}],
        "赵杰人格26。",
        advice=result.data["confirmation_prompts"],
    )
    submitted = await invoke(runtime, "submit_reading", value)
    assert submitted.ok
    assert all(prompt in submitted.data["text"] for prompt in result.data["confirmation_prompts"])
