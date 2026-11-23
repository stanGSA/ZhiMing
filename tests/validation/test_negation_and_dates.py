"""Regressions reported in the screenshot review of PR #8."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from common.output_policy import (
    HEALTH_NOTE,
    care_advice,
    care_error,
    certainty_claim,
    certainty_error,
)
from common.validation import risk_note
from plugins.astro.validation import validate_output
from scripts.compare_layers import rejection_category, repository_metadata
from tests.validation.test_layered_fact_binding import (
    STATE,
    astro_reading,
    check,
    section,
    tarot_draft,
)


@pytest.mark.parametrize(
    "text",
    [
        "这不代表过去的努力白费你下个月一定会升职",
        "我不认为这很难你一定会成功",
        "不说别的你一定会成功",
        "我不觉得这有问题你必然成功",
        "并不意味着努力白费但你一定会成功",
    ],
)
async def test_unrelated_negative_predicate_cannot_cancel_certainty(runtime, text):
    assert certainty_claim([text])
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = text
    error, _ = check(runtime, draft)
    assert error and "确定性说法" in error


@pytest.mark.parametrize(
    "text",
    [
        "我不认为你一定会失败。",
        "我不觉得你下个月必然失败。",
        "这不代表事件必然发生。",
        "并不意味着你一定会失败。",
        "并非你这个月一定会失败。",
        "不要以为你一定能成功。",
    ],
)
def test_direct_negative_complements_remain_allowed(text):
    assert certainty_claim([text]) is None


# Drafts the tarot tuning set refused (PR #37 review: 10 refused drafts replayed from the raw
# traces, all of these forms). The writers follow the card meanings' "不代表事件必然发生" and
# say it of what the question is about.
REFUSED_DRAFTS = [
    "它不代表行情必然上涨。",
    "它不预言你一定会亏钱。",
    "这不是说留下就一定会变差。",
    "这不代表某件事必然发生。",
    "不代表具体事件必然发生。",
    # The one left after 1fe9499 (re-check: 1 of the 10 still refused).
    "它不会告诉你今天一定会发生什么，只提供一个观看自己的角度。",
]


@pytest.mark.parametrize(
    "text",
    [
        *REFUSED_DRAFTS,
        "这不代表行情对你必然有利。",
        "不代表你们这段关系必然结束。",
        # Third review of 1a4b377: a negated clause whose subject is an ordinary noun phrase.
        "并非这只股票一定会涨。",
        "并非股价一定会涨。",
        "并不是这件事一定会成功。",
        "这不代表过去的亏损一定会重演。",
        "这不代表这只股票一定会涨。",
        "牌面不代表股价必然上涨。",
        "这张牌并不代表投资必然亏损。",
        "不代表全部投入必然亏损。",
        "这不代表你们的关系一定会好转。",
        "不代表关系必然走向破裂。",
        "不代表考试一定会失利。",
        "不意味着跳槽必然成功。",
        "并不是说这只股票一定会涨。",
        "这不是一种必然。",
        "并没有什么是必然的。",
        "没有哪种结果是注定的。",
        "不必把这理解为必然。",
    ],
)
def test_a_negated_claim_about_the_question_s_subject_is_allowed(text):
    assert certainty_claim([text]) is None


@pytest.mark.parametrize(
    "text",
    [
        "这只股票一定会涨。",
        "你们的关系必然好转。",
        "这不代表关系必然好转你们一定会分手。",
        "不代表投资失败你一定会赚钱。",
        "这不是一种选择，你注定要走这条路。",
        "没有什么好担心的你一定会成功。",
        "没有问题，你一定会成功。",
        "这不是坏事你一定会成功。",
        "不代表行情不好你一定会亏。",
        "它不预言失败你必然成功。",
        # Re-check of 1fe9499: a noun, not a pronoun, starts the second clause.
        "这不是坏事这只股票一定会涨。",
        "这不是坏事股价一定会涨。",
        "并非坏事股价一定会涨。",
        "这不是问题结果一定会好。",
        "这不代表失败这只股票一定会涨。",
        "这不代表坏事股价一定会涨。",
        "这不代表亏损行情一定会涨。",
        "它不预言坏事那只股票一定会涨。",
        "它不会告诉你答案你一定会成功。",
        "它不会告诉你今天会怎样，但你一定会成功。",
        "不会告诉你结果这只股票一定会涨。",
        # Third review of 1a4b377: a "…的" in front does not make a four-character head one noun.
        "这不代表过去的亏损股价一定会涨。",
        "这不代表近期的亏损行情必然上涨。",
        "并非坏事这只股票一定会涨。",
        "并非亏损股价一定会涨。",
        "这不是坏事那件事一定会成功。",
    ],
)
async def test_a_subject_or_noun_form_does_not_hide_a_separate_claim(runtime, text):
    assert certainty_claim([text])
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = text
    error, _ = check(runtime, draft)
    assert error and "确定性说法" in error


# The price of refusing what might be a second clause: a four-character head with no modifier
# of its own may be a predicate and a new subject ("过去的亏损股价"), so these negations, which
# are not, are refused too and cost a repair. Recorded here so a better rule can claim them.
@pytest.mark.xfail(strict=True, reason="四字中心词没有自带修饰语时，正则分不出它是不是两个词")
@pytest.mark.parametrize("text", ["这不代表下个月的面试结果一定会好。", "并非亏损股票一定会涨。"])
def test_a_four_character_head_without_a_modifier_is_still_refused(text):
    assert certainty_claim([text]) is None


# Two more shapes the tarot r2 run met in single drafts (docs/verification/p1/tarot-r2/
# assessment.md 4): "不是" before a framing verb is not read as the negated frame "不预言", and
# a quotation mark in front of the pronoun hides the subject after "不是". Both cost retries and
# one retry_limit there. Recorded, not fixed: P1 is frozen on the rule the r2 run measured.
@pytest.mark.xfail(strict=True, reason="“不是”加框架动词，未按否定框架处理")
@pytest.mark.parametrize(
    "text",
    ["这张牌不是预言你必定亏钱，而是提醒你控制仓位。", "牌面并不是在预言你一定会亏钱。"],
)
def test_a_copula_before_a_framing_verb_is_still_refused(text):
    assert certainty_claim([text]) is None


@pytest.mark.xfail(strict=True, reason="引号挡住了“不是”之后的代词主语")
@pytest.mark.parametrize(
    "text", ["提示的重点不是“你一定会亏”，而是仓位。", "重点不是‘你一定会亏’。"]
)
def test_a_quoted_claim_after_a_copula_is_still_refused(text):
    assert certainty_claim([text]) is None


@pytest.mark.parametrize(
    "text",
    [
        "重点不是你一定会亏。",  # the same claim unquoted is already accepted
        "这不预言你必定亏钱。",  # and so is the framing verb without the copula
    ],
)
def test_the_unquoted_or_bare_forms_are_accepted(text):
    assert certainty_claim([text]) is None


@pytest.mark.parametrize("field", ["sections", "summary", "evidence"])
def test_negated_sign_inference_is_separate_from_a_position_claim(field):
    def check_position(text):
        reading = astro_reading()
        if field == "sections":
            reading.sections = astro_reading(sections=[section(text)]).sections
        elif field == "summary":
            reading.summary = text
        else:
            reading.evidence[0].reading = text
        return validate_output(reading, STATE)

    inference = "并不是狮子座的人都外向"
    assert check_position(f"太阳狮子座，{inference}。") is None
    assert check_position("太阳狮子座，并非白羊座就一定内向。") is None
    for text in (
        "并非本命太阳在白羊座。",
        "并非太阳在狮子座就意味着做事一定固执。",
        "并非本命太阳在第4宫就代表一定成功。",
        "并非太阳不在狮子座。",
        "并非太阳在第3宫。",
        "并非不是太阳在狮子座。",
        "太阳不在白羊座，而在狮子座。",
    ):
        assert check_position(text) is None, text
    # Both explicit and denied position claims must still bind to the computed Sun in Leo.
    for text in (
        f"太阳白羊座，{inference}。",
        f"太阳不是狮子座，{inference}。",
        "太阳狮子座，并非狮子座就一定外向，也不在狮子座。",
        "太阳狮子座，并不是第4宫就意味着失败，但不在第4宫。",
        "并非本命太阳在狮子座。",
        "并非本命太阳在第4宫。",
        "并非不是太阳在白羊座。",
        "并非太阳不在白羊座。",
        "并非太阳在白羊座，而是太阳在金牛座。",
        "并非太阳在白羊座，而是太阳在第3宫。",
    ):
        assert check_position(text)


@pytest.mark.parametrize(
    "text",
    [
        "这不代表你有病不需要就医",
        "这不说明你有病不必就医",
        "这不意味着身体有问题无需就医",
        "不要以为身体很好不需要就医",
        "如果身体不适也不应就医",
        "如果身体不适不要就医",
        "身体不适不能及时就医",
    ],
)
async def test_unrelated_negation_does_not_become_care_advice(runtime, text):
    assert care_advice([text])[0] is False
    assert care_error([text])
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = "身体不适。" + text
    error, reading = check(runtime, draft)
    assert error and "不能劝阻就医" in error
    assert HEALTH_NOTE in reading.safety.note


@pytest.mark.parametrize(
    "text",
    [
        "如果不能及时就医，症状可能拖延加重",
        "不能及时就医时，先联系家人",
        "若你不能马上去医院，请联系家人",
        "万一不能及时就诊，先向家人求助",
        "一旦不可及时就医，应联系家人",
        "不能及时就医的话，先联系家人",
    ],
)
async def test_conditional_inability_is_neither_discouragement_nor_advice(runtime, text):
    assert care_advice([text]) == (False, None)
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = "身体不适。" + text
    error, reading = check(runtime, draft)
    assert error is None
    assert reading.safety.flag and HEALTH_NOTE in reading.safety.note


def test_conditional_inability_does_not_hide_a_later_prohibition():
    assert care_error(["如果不能及时就医，也不要寻求医疗帮助。"])
    assert care_advice(["不能及时就医时，先联系家人；如有不适请尽快就医。"])[0]


@pytest.mark.parametrize("field", ["sections", "summary", "evidence"])
@pytest.mark.parametrize("peak", ["达到高峰", "达到峰值", "达到顶峰", "达峰"])
def test_peak_dates_are_bound_to_the_transit(field, peak):
    for day, valid in ((5, True), (12, False)):
        text = f"行运木星拱本命太阳，在11月{day}日{peak}。"
        reading = astro_reading()
        if field == "sections":
            reading.sections = astro_reading(sections=[section(text)]).sections
        elif field == "evidence":
            reading.evidence[0].reading = text
        else:
            reading.summary = text
        assert (validate_output(reading, STATE) is None) == valid


@pytest.mark.parametrize("field", ["sections", "summary", "evidence"])
def test_influence_onset_is_not_an_exact_date_claim(field):
    text = "10月8日，行运木星拱本命太阳的影响开始显现。"
    reading = astro_reading(sections=[section(text)] if field == "sections" else [])
    if field == "summary":
        reading.summary = text
    if field == "evidence":
        reading.evidence[0].reading = text
    assert validate_output(reading, STATE) is None
    # Relaxing onset dates must never relax the relation or an explicit peak date.
    for wrong in (text.replace("拱", "刑"), text.replace("开始显现", "开始显现并达到高峰")):
        if field == "sections":
            reading.sections[0].body = wrong
        elif field == "summary":
            reading.summary = wrong
        else:
            reading.evidence[0].reading = wrong
        assert validate_output(reading, STATE)


@pytest.mark.parametrize(
    "message,expected",
    [
        ("时间范围问题需要相应行运或流期计算，不能只用原局", "fact"),
        ("systems_used 必须恰好等于本次调用的体系，不能声称使用未调用的体系", "fact"),
        ("必须先调用确定性计算工具", "fact"),
        ("西方占星专家未完成，confidence.reason 须说明缺少体系及原因", "disclosure"),
        ("正文不能包含内部状态、审核或存储错误信息", "expression"),
        ("confidence.reason 有未知问题", "other"),
    ],
)
def test_calculation_and_disclosure_categories(message, expected):
    assert rejection_category(dict(code="validation_failed", error=message)) == expected


@pytest.mark.parametrize(
    "failure", [FileNotFoundError(), subprocess.CalledProcessError(128, "git")]
)
async def test_archive_comparison_still_writes_results(project, monkeypatch, failure):
    from app import create_runtime
    from scripts import compare_layers

    def no_git(*args, **kwargs):
        raise failure

    monkeypatch.setattr(compare_layers.subprocess, "check_output", no_git)
    monkeypatch.setattr(compare_layers, "load_code", lambda root: (create_runtime, None))
    monkeypatch.setattr(compare_layers, "workdir", lambda *args: project)
    monkeypatch.setattr(
        compare_layers, "SCENARIOS", [{"id": "tarot", "kind": "塔罗", "turns": ["看看近期状态"]}]
    )
    out = await compare_layers.run(
        SimpleNamespace(
            root=project,
            out=project / "comparison",
            data_from=None,
            label="archive",
            mode="single",
            provider="demo",
            model=None,
            orchestrator_thinking=None,
        )
    )
    data = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert data["revision"] is None and data["dirty"] is None
    assert data["revision_error"] == type(failure).__name__
    assert data["rows"][0]["status"] == "submit_reading"
    assert "代码版本=未知" in compare_layers.report([out])


def test_git_metadata_preserves_revision_and_dirty_state(tmp_path, monkeypatch):
    results = iter(["abc123\n", b" M changed.py\n"])
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: next(results))
    assert repository_metadata(tmp_path) == dict(revision="abc123", dirty=True, revision_error=None)


def test_saved_diagnostics_are_reclassified_without_rewriting_them():
    from scripts.compare_layers import summarize

    details = [
        dict(
            code="validation_failed", error="时间范围问题需要相应行运或流期计算", category="other"
        ),
        dict(
            code="validation_failed",
            error="西方占星专家未完成，confidence.reason 须说明原因",
            category="expression",
        ),
    ]
    row = dict(
        status="ask_user",
        submit_rejections=[d["error"] for d in details],
        report_rejections=[],
        rejection_details=details,
        submit_attempts=2,
        reviews=[],
        turn=1,
    )
    summary = summarize([row])
    assert summary["fact_rejections"] == 1
    assert summary["disclosure_rejections"] == 1
    assert summary["expression_rejections"] == summary["other_rejections"] == 0
    assert [d["category"] for d in details] == ["other", "expression"]


INVESTMENT = "只用塔罗三张牌帮我反思：是否应该把积蓄全部买入一只股票？"


async def high_risk_draft(runtime, text):
    draft = await tarot_draft(runtime)
    runtime.session.state["question"] = INVESTMENT
    draft["sections"][0]["body"] = text
    draft["safety"] = {"flag": True, "note": risk_note(INVESTMENT)}
    return draft


@pytest.mark.parametrize("text", ["下个月不一定会顺利。", "这不代表这只股票一定会涨。"])
async def test_a_negated_claim_passes_the_high_risk_check(runtime, text):
    # The high-risk check searched the raw JSON for 一定会, so the hedge itself was refused as
    # "不能给出健康、投资或生死的确定性结论", which the pipeline takes for a safety failure.
    error, _ = check(runtime, await high_risk_draft(runtime, text))
    assert error is None


async def test_the_high_risk_check_still_refuses_a_claim_the_policy_judge_would_weigh(runtime):
    draft = await high_risk_draft(runtime, "现在全部买入，这只股票一定会涨。")
    runtime.session.policy_judge = object()  # the two-level mode: wording goes to a model
    error, _ = check(runtime, draft)
    assert error == "不能给出健康、投资或生死的确定性结论"


@pytest.mark.parametrize(
    "text",
    [
        "关于要不要去做检查：如果身体有不适，请及时就医。",
        "你问要不要去做检查，这个梦本身不能说明身体状况。",
        "需不需要去做检查，要看身体的实际感受。",
        "用不用去医院？",
        "你到底要不要去医院？",
        "你想知道需不需要去做检查，可以咨询医生。",
        "关于你要不要去做检查，可以咨询医生。",
        "你需要不需要去医院？",
        "你问我用不用去医院。",
        "你问“要不要去做检查”，梦本身不能说明身体状况。",
        "我想问一下用不用去医院？",
        # r7 dream_hospital_health#3: a title opening with a connective.
        "那要不要去做检查",
        "那么要不要去做检查？",
        "那你到底要不要去医院？",
        "所以要不要去做检查，要看身体的实际感受。",
    ],
)
def test_an_a_not_a_question_about_care_is_not_discouraging_it(text):
    """P2 r2 (dream_hospital_health#2): 要不要去做检查 repeats the user's question."""
    assert care_error([text]) is None


@pytest.mark.parametrize(
    "text",
    [
        "不要去做检查。",
        "你不需要去做检查。",
        "要不要紧都不要去医院。",
        "用不用去医院，不用去医院。",
        # A connective is no question by itself (r7 review).
        "那不要去做检查了。",
        "那就不要去做检查。",
        "那只要不要去医院就行。",
        "那要不要紧都不要去医院。",
        "那要不要去做检查？那不用去医院。",
    ],
)
def test_discouraging_care_next_to_a_question_is_still_refused(text):
    assert care_error([text])


@pytest.mark.parametrize(
    "text",
    [
        "只要不要去医院就行。",
        "你只要不要去做检查就行。",
        "出现这些副作用不用去医院。",
        "出现这些副作用不用就医。",
        "用不用去医院？出现这些副作用不用去医院。",
    ],
)
def test_a_repeated_character_across_words_is_not_a_care_question(text):
    assert care_error([text])


def test_a_care_question_alone_does_not_count_as_affirmative_advice():
    assert care_advice(["用不用去医院？"]) == (False, None)


@pytest.mark.parametrize(
    "text",
    [
        "而不是把它理解成必然的坎坷。",
        "不要把它理解成必然的坎坷。",
        "并不是把这个数理看成注定的结果。",
    ],
)
def test_declining_to_read_it_as_certain_is_not_a_certainty_claim(text):
    """r4 name_three_character#2: the sentence rejects fatalism; it was refused twice."""
    assert certainty_error([text]) is None


@pytest.mark.parametrize(
    "text",
    [
        # r8 daily_today_general#2 and daily_lucky_color#3.
        "这些只是象征性的节奏提示，不是事情必然顺利的保证，行动本身还是要靠你落到具体安排上。",
        "先澄清优先级，别把配合当成必然有利。",
        "别在情绪好时把配合当成必然有利。",
        "这不等于事情必然顺利的结论。",
    ],
)
def test_the_r8_denied_guarantees_are_not_certainty_claims(text):
    assert certainty_error([text]) is None


@pytest.mark.parametrize(
    "text",
    [
        "事情必然顺利。",
        "配合必然有利。",
        # A question asks the opposite; a comma or a contrast starts a new assertion.
        "这不是事情必然顺利的保证吗？",
        "不是坏事，事情必然顺利的保证。",
        "这不是坏事而是事情必然顺利的保证。",
        # Only a closing noun of denial counts, and the denial must not be negated itself.
        "不是事情必然顺利的原因。",
        "不是不把配合当成必然有利。",
        "不得不把配合当成必然有利。",
        "别把配合当成借口，必然有利。",
        "不是因为不努力，事情必然失败的结论。",
    ],
)
def test_what_the_r8_guarantee_fix_must_still_refuse(text):
    assert certainty_error([text])


@pytest.mark.parametrize(
    "text",
    [
        "不能说这不是事情必然顺利的保证。",
        "不能认为这不是行情必然上涨的证明。",
        "不能说这种配合不是事情必然顺利的保证。",
        "不能说这不等于事情必然顺利的结论。",
        "不是说这不能把配合当成必然有利。",
        "别把配合当成必然有利的反面。",
        "不要把配合当成必然成功以外的结果。",
        "别把这次机会当成必然成功的对立面。",
        "这不是行情必然上涨的证明的反面。",
    ],
)
def test_outer_negations_and_reversed_complements_do_not_deny_certainty(text):
    assert certainty_error([text])


@pytest.mark.parametrize(
    "text",
    [
        "别把市场反应当成必然有利。",
        "别把想象中的收益当成必然成功。",
        "不是事情必然顺利的保证。相反，行动仍须谨慎。",
        "别把配合当成必然有利，相反，应当考虑风险。",
        "你不一定会在预期之外亏损。",
        "这不代表你必然在预期之外亏损。",
    ],
)
def test_safe_denials_keep_their_own_object_and_clause_scope(text):
    assert certainty_error([text]) is None


@pytest.mark.parametrize(
    "text",
    [
        "它必然遭遇坎坷。",
        "不要把钱都投进去，理解成必然的收益。",
        "这不是把它理解成必然，而是你一定会成功。",
        "不要把它当作偶然应理解成必然的结果。",
        "别把它想复杂了应看成必然的结果。",
        "不是把它理解成偶然是看成必然的结果。",
    ],
)
def test_a_certainty_claim_beside_such_a_negation_is_still_refused(text):
    assert certainty_error([text])


@pytest.mark.parametrize(
    "text",
    [
        # Exact 3 consecutive rejected drafts on production server (2026-11-17 09:48Z).
        "凡是说“你命里注定能进某校”的说法，都是越界。",
        "凡是说“你命里必定能进某校”的说法，都是越界。",
        "凡是说“你命里一定能进某校”的说法，都是越界。",
        "凡是说“你命里注定能进某校”，都是越界。",
        # Post-quote refutations without a comma or with other refutation predicates.
        "“命里必定考上”这类说法本身就站不住脚。",
        "所谓“今年一定会暴富”的论调毫无依据。",
        "把八字当成“注定能成”的宿命论是错的。",
        "凡是说“命里注定”、“必定考上”的说法，都是迷信。",
        # Pre-quote doubt and caution-demand frames.
        "别信“你命里注定失败”的说法。",
        "警惕任何“今年一定会翻倍”的承诺。",
        "遇到“必定考上”的说法多问几个为什么。",
        "对所谓“注定成功”的话术保持警惕。",
    ],
)
def test_quoted_fatalism_refutations_are_allowed(text):
    assert certainty_claim([text]) is None
    assert certainty_error([text]) is None


@pytest.mark.parametrize(
    ("text", "expected_word"),
    [
        # Unquoted fatalism or scare-quoted word without claim noun + refutation.
        ("凡是说你命里注定能进某校的说法，都是越界。", "注定"),
        ("你“注定”能进某校。", "注定"),
        ("“你命里注定能进某校”的说法很有道理。", "注定"),
        # Negated or reversed refutation / outer negation / rhetorical question.
        ("“你命里注定能进某校”的说法并不是越界。", "注定"),
        ("“你命里注定能进某校”的说法不是不可信。", "注定"),
        ("不能说“你命里注定能进某校”的说法是越界。", "注定"),
        ("不用警惕“今年一定会翻倍”的承诺。", "一定会"),
        ("别信“你命里注定失败”的说法是错的。", "注定"),
        ("“你命里注定能进某校”的说法是越界吗？", "注定"),
        ("“你命里注定能进某校”的说法是越界的反面。", "注定"),
        ("对“注定成功”的话术保持警惕是多此一举。", "注定"),
        # PR review #1: post-caution reversals ("是不对的 / 是错的 / 的反面" and comma-joined undoers).
        ("对“这只股票一定会翻倍”的说法保持警惕是不对的。", "一定会"),
        ("对“这只股票一定会翻倍”的说法保持警惕是错的。", "一定会"),
        ("对“这只股票一定会翻倍”的说法保持警惕的反面才是对的。", "一定会"),
        ("对“这只股票一定会翻倍”的说法保持警惕，是不对的。", "一定会"),
        ("警惕“这只股票一定会翻倍”的说法，完全没必要。", "一定会"),
        ("“这只股票一定会翻倍”的说法是迷信，但其实很有道理。", "一定会"),
        # PR review #2: outer negations separated by commas/colons or modal negators.
        ("不能说，“这只股票一定会翻倍”的说法是迷信。", "一定会"),
        ("不能说：“这只股票一定会翻倍”的说法是迷信。", "一定会"),
        ("不要以为，“今年一定会翻倍”的承诺不可信。", "一定会"),
        ("并非，“你命里注定能进某校”的说法站不住脚。", "注定"),
        ("不应该警惕“今年一定会翻倍”的承诺。", "一定会"),
        ("错误的做法是：对“这只股票一定会翻倍”的说法保持警惕。", "一定会"),
        # Exempting a refuted quote never covers a real affirmative claim later in the sentence.
        ("凡是说“你命里注定能进某校”的说法都是越界，但你明年一定会考上。", "一定会"),
    ],
)
def test_quoted_fatalism_guards_still_refuse_escapes(text, expected_word):
    assert certainty_claim([text]) == expected_word
    err = certainty_error([text], include_quote=True)
    assert err and f"“{expected_word}”" in err
    assert "冲突句子：" in err
    assert getattr(err, "retry_key", None) == "certainty_claim"


async def test_agent_submission_quotes_offending_sentence_and_caps_synonym_retries(
    runtime, scripted_model
):
    from harness.loop import run_turn
    from harness.models import ModelResponse, ToolCall

    draft = await tarot_draft(runtime)
    # First verify quoted fatalism refutation passes end-to-end in validate_reading.
    draft_ok = dict(draft)
    draft_ok["sections"] = [
        dict(draft["sections"][0], body="凡是说“你命里注定能进某校”的说法，都是越界。")
    ]
    error_ok, _ = check(runtime, draft_ok)
    assert error_ok is None

    # Next verify true violations return offending sentence + stable retry_key across synonyms.
    bad_sentences = [
        "这与你的画像不符，明年你注定顺利上岸。",
        "这与你的画像不符，明年你必定顺利上岸。",
        "这与你的画像不符，明年你一定能顺利上岸。",
    ]
    calls = []
    for idx, bad in enumerate(bad_sentences):
        d = json.loads(json.dumps(draft))
        d["sections"][0]["body"] = bad
        error_bad, _ = check(runtime, d)
        assert error_bad is not None
        assert f"冲突句子：“{bad}”" in error_bad
        assert getattr(error_bad, "retry_key", None) == "certainty_claim"
        assert (
            rejection_category({"code": "validation_failed", "error": str(error_bad)})
            == "expression"
        )
        calls.append(
            ModelResponse(
                input_tokens=100,
                output_tokens=20,
                tool_calls=[ToolCall(id=f"sub-{idx}", name="submit_reading", arguments=d)],
            )
        )
    model = scripted_model(calls)
    outcome = await run_turn(runtime.session, "继续提交", model, runtime.registry, runtime.tracer)
    assert outcome.status == "retry_limit"
    assert len(model.seen_messages) == 3


async def test_high_risk_agent_submission_quotes_offending_hard_claim(runtime):
    draft = await high_risk_draft(
        runtime, "2027是比肩年，尽量不借钱炒股；别人推荐的“稳赚机会”先放几天再决定。"
    )
    error, _ = check(runtime, draft)
    assert error is not None
    assert "不能给出健康、投资或生死的确定性结论" in error
    assert "命中“稳赚”" in error
    assert "别人推荐的“稳赚机会”先放几天再决定。" in error
    assert getattr(error, "retry_key", None) == "high_risk_claim"


@pytest.mark.parametrize(
    "sentence",
    [
        "对“这只股票一定会翻倍”的说法保持警惕是不对的。",
        "对“这只股票一定会翻倍”的说法保持警惕是错的。",
        "对“这只股票一定会翻倍”的说法保持警惕的反面。",
        "对“这只股票一定会翻倍”的说法保持警惕，是不对的。",
        "不能说，“这只股票一定会翻倍”的说法是迷信。",
        "不能说：“这只股票一定会翻倍”的说法是迷信。",
        "不要以为，“这只股票一定会翻倍”的承诺不可信。",
        "“这只股票一定会翻倍”的说法是迷信，但其实很准。",
    ],
)
async def test_high_risk_quoted_escapes_from_pr_review_are_refused(runtime, sentence):
    draft = await high_risk_draft(runtime, sentence)
    error, _ = check(runtime, draft)
    assert error is not None
    assert "不能使用“一定会”这类确定性说法" in error
    assert f"冲突句子：“{sentence}”" in error
    assert getattr(error, "retry_key", None) == "certainty_claim"

    # Also verify the two-level policy_judge path (where certainty_error is skipped and
    # HIGH_RISK's own certainty_violation check is the sole gatekeeper) still refuses it.
    runtime.session.policy_judge = object()
    error_pj, _ = check(runtime, draft)
    assert error_pj == "不能给出健康、投资或生死的确定性结论"


def test_quoted_error_snippets_never_pollute_failure_taxonomy_or_layer_categories():
    from common.output_policy import medication_error
    from scripts.failure_taxonomy import category

    # PR review #3: quoted snippets containing 画像 / 原话 / ref_id / 不符 must never misclassify
    # care_error, certainty_error, or medication_error into provenance (C), ref (D), or fact (E).
    care_msg = care_error(["你的画像显示身体无碍，不必就医。"], include_quote=True)
    assert care_msg is not None and "（冲突句子：“你的画像显示身体无碍，不必就医。”）" in care_msg
    assert category("submit_reading", "validation_failed", str(care_msg)) == "I 表达策略"
    assert rejection_category({"code": "validation_failed", "error": str(care_msg)}) == "safety"

    # Also verify legacy comma-delimited format is stripped cleanly.
    legacy_care = "不能劝阻就医（“不必就医”，冲突句子：“你的画像显示身体无碍，不必就医。”）；请改写"
    assert category("submit_reading", "validation_failed", legacy_care) == "I 表达策略"
    assert rejection_category({"code": "validation_failed", "error": legacy_care}) == "safety"

    cert_msg = certainty_error(["你的画像与原话ref_id不符，注定成功。"], include_quote=True)
    assert cert_msg is not None
    assert category("submit_reading", "validation_failed", str(cert_msg)) == "I 表达策略"
    assert rejection_category({"code": "validation_failed", "error": str(cert_msg)}) == "expression"

    med_msg = medication_error(["你的画像与日期范围不符，直接停药即可。"], include_quote=True)
    assert med_msg is not None
    med_cat = category("submit_reading", "validation_failed", str(med_msg))
    assert not med_cat.startswith(("C ", "D ", "E ", "F "))
    assert rejection_category({"code": "validation_failed", "error": str(med_msg)}) == "safety"
