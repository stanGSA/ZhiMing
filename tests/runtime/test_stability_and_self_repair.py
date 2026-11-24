"""Regression tests for the three-layer reading stability and self-repair architecture.

Covers:
1. Layer 1: lookup_meaning circuit-breaker + DB candidate keys, Reading mechanical auto-assembly,
   and plain-text implicit clarification normalization into ask_user.
2. Layer 2: paired inner ASCII quote recovery in CJK prose across all tool calls, quoted fatalism
   refutation exemptions + adversarial guards, tarot hypothetical card exemptions, bazi temporal
   pillar prefixes, astro transit-vs-natal disambiguation hints, multi-error single-pass
   aggregation, and taxonomy quote-stripping.
3. Layer 3: patch_reading partial draft repair (including section_patches, shared 3-strike bucket,
   reviewer revise, and multi-agent tension disclosure) and decoupled repair_steps reserve.
"""

from __future__ import annotations

import copy
import json

import pytest

from agents.demo import DemoModel
from app import create_runtime
from common.output_policy import care_error, certainty_error
from common.schemas import Evidence, Reading, Section
from harness.json_arguments import parse_arguments
from harness.loop import run_turn
from harness.models import ModelResponse, ToolCall
from plugins.astro.validation import validate_output as validate_astro_facts
from plugins.bazi.validation import validate_output as validate_bazi_facts
from plugins.tarot.validation import validate_output as validate_tarot_facts
from scripts.compare_layers import rejection_category
from scripts.failure_taxonomy import category as taxonomy_category
from tests.plugins.test_astro_bazi_integration import invoke

QUESTION = "接下来三个月工作推进要注意什么？"


class Replay:
    def __init__(self, steps):
        self.steps = iter(steps)
        self.shown = []

    async def chat(self, messages, tools):
        self.shown.append((copy.deepcopy(messages), copy.deepcopy(tools)))
        return next(self.steps)


def call_step(index: int, name: str, **arguments) -> ModelResponse:
    return ModelResponse(
        input_tokens=100,
        output_tokens=20,
        tool_calls=[ToolCall(id=f"call-{index}", name=name, arguments=arguments)],
    )


def text_step(text: str) -> ModelResponse:
    return ModelResponse(input_tokens=80, output_tokens=20, text=text, tool_calls=[])


def tool_names_in(schema_list: list[dict]) -> set[str]:
    return {t["function"]["name"] for t in schema_list}


# ---------------------------------------------------------------------------
# Layer 2a: JSON inner-quote recovery across all tool calls
# ---------------------------------------------------------------------------


def test_parse_arguments_repairs_paired_prose_quotes_and_rejects_broken_json():
    raw_mid = '{"question": "请问拿到"Offer"之后要不要去？"}'
    parsed_mid, repaired_mid = parse_arguments(raw_mid)
    assert repaired_mid is True
    assert parsed_mid == {"question": '请问拿到"Offer"之后要不要去？'}

    raw_end = '{"body": "这一步重点看"Offer""}'
    parsed_end, repaired_end = parse_arguments(raw_end)
    assert repaired_end is True
    assert parsed_end == {"body": '这一步重点看"Offer"'}

    raw_start = '{"body": ""A/B"两个方向先核实预算"}'
    parsed_start, repaired_start = parse_arguments(raw_start)
    assert repaired_start is True
    assert parsed_start == {"body": '"A/B"两个方向先核实预算'}

    for broken in ('{"body":"a"broken"}', '{"body":"a" "other":1}', '{"body":"unterminated'):
        with pytest.raises((ValueError, TypeError)):
            parse_arguments(broken)


async def test_openai_model_repairs_prose_quotes_for_patch_reading(monkeypatch):
    from types import SimpleNamespace

    from harness.llm import OpenAIModel

    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    model = OpenAIModel("synthetic")

    fake_tc = SimpleNamespace(
        id="tc-1",
        function=SimpleNamespace(
            name="patch_reading",
            arguments='{"summary": "拿到"Offer"之后先把现实条件核实清楚。"}',
        ),
    )
    fake_choice = SimpleNamespace(
        message=SimpleNamespace(content="", tool_calls=[fake_tc]),
        finish_reason="tool_calls",
    )
    fake_usage = SimpleNamespace(
        prompt_tokens=50,
        completion_tokens=15,
        prompt_tokens_details=None,
        completion_tokens_details=None,
    )
    fake_resp = SimpleNamespace(choices=[fake_choice], usage=fake_usage, model="synthetic")

    async def fake_create(**_kwargs):
        return fake_resp

    monkeypatch.setattr(model.client.chat.completions, "create", fake_create)
    try:
        response = await model.chat([{"role": "user", "content": "你好"}], [])
    finally:
        await model.close()
    assert len(response.tool_calls) == 1
    tc = response.tool_calls[0]
    assert tc.argument_error is False
    assert tc.arguments_repaired is True
    assert tc.arguments == {"summary": '拿到"Offer"之后先把现实条件核实清楚。'}


# ---------------------------------------------------------------------------
# Layer 2b: Policy & plugin regex false-positive exemptions + adversarial guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "别轻信“命里注定发大财”的说法，先把眼前项目落地。",
        "别相信“今年一定会暴富”的说法。",
        "所谓“包过、一定会升职”的话术往往是迷信。",
        "推进不顺时，所谓“命里注定失败”的说法往往是迷信。",
        "听到「今年必然翻倍」的承诺，要保持清醒。",
        "不要迷信『铁定稳赚』的论调。",
    ],
)
def test_certainty_error_allows_explicitly_refuted_short_quotes(text):
    assert certainty_error([text]) is None


@pytest.mark.parametrize(
    "text",
    [
        "“谨慎行事”，今年一定会升职，“失败预言”的说法是迷信。",
        "“谨慎行事，今年一定会升职，“失败预言”的说法是迷信。",
        "我不认为“你今年一定会升职”的说法是迷信。",
        "我并不觉得，“你今年一定会升职”的说法是迷信。",
        "不必警惕“你今年一定会升职”的说法。",
        "别相信“你今年一定会升职”的说法是迷信。",
        "不能说，“今年一定会翻倍”的说法是迷信。",
        "难道“今年一定会升职”是迷信吗？",
        "“今年一定会升职”的说法听起来像迷信，但其实很准。",
        "俗话说“命里注定有贵人”，这次你可以放心冲。",
        "接下来三个月你一定会升职加薪。",
    ],
)
def test_certainty_error_blocks_unrefuted_or_adversarial_quotes_with_sentence_snippet(text):
    err = certainty_error([text])
    assert err is not None
    assert "冲突原句" in err
    assert getattr(err, "retry_key", None) == "certainty_claim"


def test_care_error_attaches_sentence_snippet_and_stable_retry_key():
    err = care_error(["最近脾胃偏弱，只是小毛病不用去医院检查，自己多喝热水就行。"])
    assert err is not None
    assert "冲突原句" in err
    assert getattr(err, "retry_key", None) == "discourage_care"


def test_tarot_hypothetical_orientation_contrast_allowed_only_when_anchored():
    state = {
        "facts": ["宝剑二"],
        "tarot_result": {
            "cards": [
                {
                    "card_id": "swords_two",
                    "name": "宝剑二",
                    "reversed": True,
                    "label": "现状",
                }
            ]
        },
    }

    def make_reading(body: str, summary: str = "僵局正在松动。") -> Reading:
        return Reading(
            question_type="tarot",
            summary=summary,
            sections=[Section(title="现状梳理", body=body, ref_ids=["r1"])],
            evidence=[Evidence(ref_id="r1", reading="现状：【宝剑二】（逆位）")],
        )

    assert (
        validate_tarot_facts(
            make_reading(
                "本次落出宝剑二逆位，说明原本僵持的信息开始浮出水面。如果是宝剑二正位，反而容易继续回避。"
            ),
            state,
        )
        is None
    )
    assert (
        validate_tarot_facts(
            make_reading("牌面是宝剑二逆位。若是宝剑二正位的话，节奏会完全不同。"),
            state,
        )
        is None
    )
    with_followup = make_reading("本次牌面是宝剑二逆位，提示僵局松动。")
    with_followup.followups = ["宝剑二正位的话，我该怎么调整沟通方式？"]
    assert validate_tarot_facts(with_followup, state) is None
    # Unanchored hypothetical without naming the actual orientation is still rejected.
    unanchored = validate_tarot_facts(
        make_reading("如果是宝剑二正位，说明双方还在僵持。"),
        state,
    )
    assert unanchored is not None and "冲突片段" in unanchored
    # Correct orientation in summary must NOT exempt a wrong assertion or bare definition in body.
    cross_section_possessive = validate_tarot_facts(
        make_reading(
            "你手里的宝剑二正位表示双方仍在僵持，建议继续观望。",
            summary="宝剑二逆位提示局面松动。",
        ),
        state,
    )
    assert cross_section_possessive is not None and "方向错误" in cross_section_possessive
    cross_section_def = validate_tarot_facts(
        make_reading(
            "宝剑二正位表示双方仍在僵持，建议继续观望。",
            summary="宝剑二逆位提示局面松动。",
        ),
        state,
    )
    assert cross_section_def is not None and "方向错误" in cross_section_def
    # Claiming the hypothetical orientation was drawn is rejected.
    draw_claim = validate_tarot_facts(
        make_reading("宝剑二逆位提示变化；这次抽到了如果是宝剑二正位也一样。"),
        state,
    )
    assert draw_claim is not None


def test_bazi_temporal_flow_pillar_prefixes_distinguished_from_natal_pillars():
    state = {
        "calendar_anchor": "2026-02-10",
        "calendar_timezone": "Asia/Shanghai",
        "bazi_result": {
            "pillars": {
                "year": "辛巳",
                "month": "己亥",
                "day": "壬辰",
                "time": "乙巳",
            },
            "day_master": "壬",
            "time_known": True,
        },
        "bazi_period_result": {
            "tz": "Asia/Shanghai",
            "periods": [
                {
                    "start_utc": "2026-02-09T16:00:00+00:00",
                    "end_utc": "2026-02-10T16:00:00+00:00",
                    "pillars": {"year": "丙午", "month": "庚寅", "day": "甲子"},
                },
                {
                    "start_utc": "2026-02-10T16:00:00+00:00",
                    "end_utc": "2026-03-05T16:00:00+00:00",
                    "pillars": {"year": "丙午", "month": "庚寅", "day": "乙丑"},
                },
                {
                    "start_utc": "2026-03-05T16:00:00+00:00",
                    "end_utc": "2027-02-03T19:00:00+00:00",
                    "pillars": {"year": "丙午", "month": "辛卯", "day": "丙寅"},
                },
                {
                    "start_utc": "2027-02-03T19:00:00+00:00",
                    "end_utc": "2027-10-01T16:00:00+00:00",
                    "pillars": {"year": "丁未", "month": "壬寅", "day": "丁卯"},
                },
            ],
        },
    }

    def make_reading(body: str) -> Reading:
        return Reading(
            question_type="timing",
            summary="近期节奏偏快。",
            sections=[Section(title="流期观察", body=body, ref_ids=["r1"])],
        )

    assert (
        validate_bazi_facts(
            make_reading(
                "今年年柱丙午火势偏旺，明年年柱丁未承接转化；本月月柱庚寅木金交战，下月月柱辛卯更讲条理，今日日柱甲子宜稳步推进。"
            ),
            state,
        )
        is None
    )
    # Swapping 2026 (今年) and 2027 (明年) pillars must fail even though both exist in periods.
    swapped_years = validate_bazi_facts(
        make_reading("今年年柱丁未，明年年柱丙午。"),
        state,
    )
    assert swapped_years is not None and "流期柱位与对应日期干支不符" in swapped_years
    # Swapping 本月 and 下月 pillars must fail.
    swapped_months = validate_bazi_facts(
        make_reading("本月月柱辛卯，下月月柱庚寅。"),
        state,
    )
    assert swapped_months is not None and "流期柱位与对应日期干支不符" in swapped_months
    # Claiming 去年 (2025, not computed) with a computed pillar must fail.
    uncomputed_year = validate_bazi_facts(
        make_reading("去年年柱丙午火旺。"),
        state,
    )
    assert uncomputed_year is not None and "流期柱位与对应日期干支不符" in uncomputed_year
    # Natal pillar mismatch still fails.
    err = validate_bazi_facts(make_reading("原局年柱丙午火旺，做事容易急躁。"), state)
    assert err is not None
    assert "原局柱位与干支不符" in err
    assert "冲突片段" in err


def test_astro_transit_vs_natal_aspect_disambiguation_hint_and_taxonomy():
    state = {
        "natal_result": {
            "time_known": True,
            "planets": [
                {"body_zh": "太阳", "sign_zh": "天蝎", "house": 10},
                {"body_zh": "土星", "sign_zh": "双子", "house": 5},
            ],
            "aspects": [],
        },
        "transit_result": {
            "events": [
                {
                    "transit_body": "Saturn",
                    "natal_body": "Sun",
                    "aspect": "square",
                    "exact_utc": "2026-11-12T04:00:00Z",
                    "exact_date": "2026-11-12",
                }
            ],
            "interpretations": [],
        },
    }
    reading = Reading(
        question_type="timing",
        summary="近期压力偏大。",
        sections=[
            Section(title="关键相位", body="太阳与土星呈四分相，推进节奏受阻。", ref_ids=["r1"])
        ],
    )
    err = validate_astro_facts(reading, state)
    assert err is not None
    assert "本命行星相位与本次计算不符" in err
    assert "冲突片段" in err
    assert "该相位属于本次行运事件" in err
    assert "行运土星" in err

    # Quote suffixes must not pollute rejection_category or failure_taxonomy.category.
    cert_with_astro_words = certainty_error(["这个星盘相位说明你今年一定会升职。"])
    assert rejection_category({"code": "validation_failed", "error": cert_with_astro_words}) == (
        "expression"
    )
    assert taxonomy_category("submit_reading", "validation_failed", cert_with_astro_words) == (
        "I 表达策略"
    )
    assert rejection_category({"code": "validation_failed", "error": err}) == "fact"
    assert taxonomy_category("submit_reading", "validation_failed", err) == "E 事实与计算不符"


# ---------------------------------------------------------------------------
# Layer 1 + Layer 2c + Layer 3: End-to-end runtime & loop tests
# ---------------------------------------------------------------------------


async def test_lookup_meaning_stops_after_two_misses_and_hides_on_daily(runtime):
    model = Replay(
        [
            call_step(0, "start_reading", question=QUESTION, systems=["tarot"]),
            call_step(1, "draw_tarot", spread="single", question=QUESTION),
            call_step(2, "lookup_meaning", system="astro", kind="transit", key="missing_one"),
            call_step(3, "lookup_meaning", system="astro", kind="transit", key="missing_two"),
            call_step(
                4,
                "submit_reading",
                question_type="tarot",
                summary="先把眼前最关键的一件事落地。",
                sections=[
                    {
                        "title": "先收敛战线",
                        "body": "把注意力放回可控的交付节奏上，核实优先级后再推进。",
                        "ref_ids": ["R1"],
                    }
                ],
                advice=["本周先列出最重要的一项交付并核实截止时间。"],
            ),
        ]
    )
    outcome = await run_turn(runtime.session, QUESTION, model, runtime.registry, runtime.tracer)
    assert outcome.status == "submit_reading"

    tool_msgs = [json.loads(m["content"]) for m in runtime.session.messages if m["role"] == "tool"]
    miss1, miss2 = tool_msgs[2], tool_msgs[3]
    assert miss1["code"] == "missing_entry"
    assert "本版本有效key候选：" in miss1["error"]
    assert miss2["code"] == "missing_entry"
    assert "本轮缺条目已达上限" in miss2["error"]
    # Before miss2 lookup_meaning was visible; on step 4 (after 2 misses) it was hidden.
    assert "lookup_meaning" in tool_names_in(model.shown[3][1])
    assert "lookup_meaning" not in tool_names_in(model.shown[4][1])

    # Auto-assembled mechanical fields on Reading:
    saved = outcome.data["reading"]
    assert saved["systems_used"] == ["tarot"]
    assert len(saved["evidence"]) == 1 and saved["evidence"][0]["reading"]
    assert saved["confidence"]["level"] == "low"
    assert "未经审核" in saved["confidence"]["reason"]
    assert saved["safety"] == {"flag": False, "note": ""}

    # Daily fortune hides lookup_meaning immediately once signals == {"daily"}.
    runtime.session.append_user("今天（2026年10月15日）运势怎么样？")
    assert (await invoke(runtime, "start_reading", dict(question="今天运势", systems=["daily"]))).ok
    assert (await invoke(runtime, "daily_fortune", dict(date="2026-10-15"))).ok
    assert "lookup_meaning" not in tool_names_in(runtime.registry.schemas(runtime.session))


async def test_implicit_clarification_normalizes_missing_birth_and_pending_input(project):
    rt_birth = create_runtime(root=project, user_id="clarify-birth", seed=42)
    try:
        model = Replay([text_step("为了准确排八字，请先提供你的出生年月日时、性别和出生地？")])
        out = await run_turn(
            rt_birth.session,
            "帮我排个八字看看今年事业发展",
            model,
            rt_birth.registry,
            rt_birth.tracer,
        )
        assert out.status == "ask_user"
        assert "出生" in out.text
    finally:
        rt_birth.close()

    # Pure conceptual question without missing birth data remains status="text".
    rt_chat = create_runtime(root=project, user_id="clarify-chat", seed=42)
    try:
        model_chat = Replay([text_step("三张牌阵通常用来观察过去、现在与接下来的发展脉络。")])
        out_chat = await run_turn(
            rt_chat.session,
            "什么是塔罗三张牌阵？",
            model_chat,
            rt_chat.registry,
            rt_chat.tracer,
        )
        assert out_chat.status == "text"
    finally:
        rt_chat.close()


async def test_validate_reading_aggregates_multiple_errors_and_patch_reading_repairs_locally(
    project,
    runtime,
):
    probe_rt = create_runtime(root=project, user_id="probe-draw", seed=42)
    try:
        probe_rt.session.append_user(QUESTION)
        assert (
            await invoke(probe_rt, "start_reading", dict(question=QUESTION, systems=["tarot"]))
        ).ok
        assert (await invoke(probe_rt, "draw_tarot", dict(spread="single", question=QUESTION))).ok
        card = probe_rt.session.state["tarot_result"]["cards"][0]
    finally:
        probe_rt.close()
    actual_ori = "逆位" if card["reversed"] else "正位"
    wrong_ori = "正位" if card["reversed"] else "逆位"

    keep_section_body = (
        "先把手中正在推进的事项按轻重缓急做一次梳理，优先把已经具备现实条件的环节闭环。"
    )
    model = Replay(
        [
            call_step(0, "start_reading", question=QUESTION, systems=["tarot"]),
            call_step(1, "draw_tarot", spread="single", question=QUESTION),
            call_step(
                2,
                "submit_reading",
                question_type="tarot",
                summary="短期先稳住节奏。",
                sections=[
                    {
                        "title": "牌面提示",
                        "body": f"本次{card['name']}{wrong_ori}说明接下来三个月你一定会升职。",
                        "ref_ids": ["R999"],
                    },
                    {
                        "title": "行动抓手",
                        "body": keep_section_body,
                        "ref_ids": ["R1"],
                    },
                ],
                advice=["本周核实关键节点的交付标准。"],
            ),
            call_step(
                3,
                "patch_reading",
                section_patches=[
                    {
                        "index": 0,
                        "body": f"本次{card['name']}{actual_ori}提示先把节奏放稳，逐步推进。",
                        "ref_ids": ["R1"],
                    }
                ],
            ),
        ]
    )
    outcome = await run_turn(runtime.session, QUESTION, model, runtime.registry, runtime.tracer)
    assert outcome.status == "submit_reading"

    tool_msgs = [json.loads(m["content"]) for m in runtime.session.messages if m["role"] == "tool"]
    rejected = tool_msgs[2]
    assert not rejected["ok"]
    # All three independent errors (citation + tarot orientation + certainty) reported together!
    assert "3 处校验问题" in rejected["error"]
    assert "R999" in rejected["error"]
    assert "牌面方向错误" in rejected["error"]
    assert "确定性说法" in rejected["error"]
    assert "patch_reading" in rejected["error"]

    # patch_reading was exposed on step 3 with constrained SectionPatch.ref_ids enum:
    patch_schema = next(t for t in model.shown[3][1] if t["function"]["name"] == "patch_reading")
    sec_patch_ref = patch_schema["function"]["parameters"]["$defs"]["SectionPatch"]["properties"][
        "ref_ids"
    ]
    enums = [branch["items"]["enum"] for branch in sec_patch_ref["anyOf"] if "items" in branch]
    assert enums == [["R1"]]

    # Section 1 remained untouched while Section 0 was repaired and persisted:
    saved_sections = outcome.data["reading"]["sections"]
    assert len(saved_sections) == 2
    assert saved_sections[1]["body"] == keep_section_body
    assert actual_ori in saved_sections[0]["body"]
    assert "last_reading_draft" not in runtime.session.state


async def test_synonym_swapping_across_submit_and_patch_hits_three_strike_limit(runtime):
    base = DemoModel.submission(
        QUESTION,
        [{"ref_id": "R1"}],
        "single",
        None,
        [{"title": "趋势观察", "body": "这个月你一定会拿到理想结果。", "ref_ids": ["R1"]}],
    )
    model = Replay(
        [
            call_step(0, "start_reading", question=QUESTION, systems=["tarot"]),
            call_step(1, "draw_tarot", spread="single", question=QUESTION),
            call_step(2, "submit_reading", **base),
            call_step(
                3,
                "patch_reading",
                section_patches=[{"index": 0, "body": "这个月你必定拿到理想结果。"}],
            ),
            call_step(
                4,
                "patch_reading",
                section_patches=[{"index": 0, "body": "这个月你注定拿到理想结果。"}],
            ),
        ]
    )
    outcome = await run_turn(runtime.session, QUESTION, model, runtime.registry, runtime.tracer)
    assert outcome.status == "retry_limit"


async def test_decoupled_repair_steps_activates_only_when_final_step_failed_submission(project):
    # Case 1: max_steps=3, repair_steps=2, step 2 had a rejected submit_reading -> step 3 repairs it.
    rt_ok = create_runtime(root=project, user_id="reserve-ok", seed=42)
    try:
        bad = DemoModel.submission(
            QUESTION,
            [{"ref_id": "R1"}],
            "single",
            None,
            [{"title": "核心观察", "body": "这个月一定会成功。", "ref_ids": ["R1"]}],
        )
        model_ok = Replay(
            [
                call_step(0, "start_reading", question=QUESTION, systems=["tarot"]),
                call_step(1, "draw_tarot", spread="single", question=QUESTION),
                call_step(2, "submit_reading", **bad),
                call_step(
                    3,
                    "patch_reading",
                    section_patches=[{"index": 0, "body": "这个月倾向逐步顺畅，先核实现实条件。"}],
                ),
            ]
        )
        out_ok = await run_turn(
            rt_ok.session,
            QUESTION,
            model_ok,
            rt_ok.registry,
            rt_ok.tracer,
            max_steps=3,
            repair_steps=2,
        )
        assert out_ok.status == "submit_reading"
        # During repair_only reserve (step 3), only submit_reading and patch_reading are offered:
        assert tool_names_in(model_ok.shown[3][1]) == {"submit_reading", "patch_reading"}
    finally:
        rt_ok.close()

    # Case 2: max_steps=3, repair_steps=2, no submission attempted -> stops at step 3 with step_limit.
    rt_limit = create_runtime(root=project, user_id="reserve-limit", seed=42)
    try:
        model_limit = Replay(
            [
                call_step(0, "start_reading", question=QUESTION, systems=["tarot"]),
                call_step(1, "draw_tarot", spread="single", question=QUESTION),
                call_step(2, "lookup_meaning", system="tarot", kind="position", key="single:1"),
            ]
        )
        out_limit = await run_turn(
            rt_limit.session,
            QUESTION,
            model_limit,
            rt_limit.registry,
            rt_limit.tracer,
            max_steps=3,
            repair_steps=2,
        )
        assert out_limit.status == "limit_reached"
        assert len(model_limit.shown) == 3
    finally:
        rt_limit.close()
