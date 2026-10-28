"""PR #5 review: the eight accept paths the first week 6 version let through."""

from datetime import date, timedelta

from agents.schemas import ReportInput
from agents.specialists import as_reading
from common.schemas import Reading
from plugins.name.wuge import analyze
from tests.plugins.test_astro_bazi_integration import invoke
from tests.plugins.test_name_dream_daily import LOW, ask, with_birth

ANCHOR = "2026-10-14"
TOMORROW = (date.fromisoformat(ANCHOR) + timedelta(days=1)).isoformat()


def submission(system, evidence, summary, **extra):
    return dict(
        question_type=system,
        systems_used=[system],
        summary=summary,
        evidence=evidence,
        confidence=LOW,
        safety=dict(flag=False, note=""),
        **extra,
    )


async def submit(runtime, value):
    return await invoke(runtime, "submit_reading", value)


# ---- 1. daily target date ---------------------------------------------------------------


async def test_birth_date_in_question_is_not_the_consultation_date(runtime):
    runtime.session.calendar_anchor = ANCHOR
    with_birth(runtime)
    await ask(runtime, "我出生于1996-05-10 08:30，成都，今天运势怎么样？")
    wrong = await invoke(runtime, "daily_fortune", dict(date="1996-05-10"))
    assert ANCHOR in wrong.error
    assert (await invoke(runtime, "daily_fortune", dict(date=ANCHOR))).ok


def test_birth_context_alone_marks_a_birth_date():
    # The profile does not hold this birth date yet: the wording alone must exclude it.
    from types import SimpleNamespace

    from plugins.daily.tools import requested_date

    def session(*messages):
        return SimpleNamespace(
            user_messages=list(messages),
            calendar_anchor=ANCHOR,
            profile={},
            state={"question_message_index": 0},
        )

    assert requested_date(session("我出生于1996-05-10 08:30，今天运势怎么样？")) == ANCHOR
    assert requested_date(session("我1996年5月10日08:30出生，明天呢？")) == TOMORROW
    assert requested_date(session("生日是5月10日，看看10月20日")) == "2026-10-20"
    assert requested_date(session("2026-10-20运势怎么样？")) == "2026-10-20"
    # A birth date written after the asked-for day must not override it.
    assert requested_date(session("今天运势怎么样？我是1996-05-10 08:30出生的")) == ANCHOR
    assert requested_date(session("明天呢？我生于1996年5月10日")) == TOMORROW


async def test_target_date_survives_a_birth_data_answer(runtime):
    runtime.session.calendar_anchor = ANCHOR
    await ask(runtime, "明天运势怎么样？")
    first = await invoke(runtime, "daily_fortune", dict(date=TOMORROW))
    assert first.data["code"] == "missing_birth_information"
    with_birth(runtime)
    runtime.session.append_user("成都出生，08:30。")
    assert TOMORROW in (await invoke(runtime, "daily_fortune", dict(date=ANCHOR))).error
    result = await invoke(runtime, "daily_fortune", dict(date=TOMORROW))
    assert result.ok and result.data["date"] == TOMORROW
    assert runtime.session.state["daily_target_date"] == TOMORROW
    runtime.session.append_user("那改成后天呢？")
    later = (date.fromisoformat(ANCHOR) + timedelta(days=2)).isoformat()
    assert later in (await invoke(runtime, "daily_fortune", dict(date=TOMORROW))).error


async def test_impossible_user_date_is_a_recoverable_failure(runtime):
    runtime.session.calendar_anchor = ANCHOR
    with_birth(runtime)
    await ask(runtime, "2026-02-30那天运势怎么样？")
    result = await invoke(runtime, "daily_fortune", dict(date=ANCHOR))
    assert not result.ok and "不存在" in result.error


# ---- 2-4. dream ------------------------------------------------------------------------


async def dream(runtime, message, *symbols):
    await ask(runtime, message)
    items = [dict(phrase=phrase, symbol=symbol) for phrase, symbol in symbols]
    return await invoke(runtime, "lookup_dream_symbols", dict(symbols=items))


async def test_symbol_needs_a_literal_phrase_and_controlled_mapping(runtime):
    mismatched = await dream(runtime, "梦见一部手机掉在地上。", ("手机", "飞机"))
    assert "不是原文" in mismatched.error
    invented = await invoke(
        runtime, "lookup_dream_symbols", dict(symbols=[dict(phrase="飞机", symbol="飞机")])
    )
    assert "逐字来自" in invented.error
    teeth = await dream(runtime, "梦到牙齿一颗一颗掉下来", ("牙齿一颗一颗掉下来", "掉牙"))
    assert [h["key"] for h in teeth.data["hits"]] == ["掉牙"]
    assert teeth.data["hits"][0]["phrase"] == "牙齿一颗一颗掉下来"


async def test_unquoted_unmatched_symbol_cannot_be_interpreted(runtime):
    result = await dream(runtime, "梦见一只小狗跟着我", ("一只小狗", "狗"))
    ref = result.data["interpretations"][0]["ref_id"]
    evidence = [dict(ref_id=ref, reading="梦见狗多与陪伴和友谊有关。")]
    for summary in (
        "蛇象征变化，提醒你反思近期状态。",
        "梦里的「蛇」代表转变。",
        "梦见蛇说明压力大。",
    ):
        rejected = await submit(runtime, submission("dream", evidence, summary))
        assert "不是本次命中" in rejected.error, summary
    # A synonym of the hit and an explicit not-in-dictionary note are fine.
    ok = "小狗代表陪伴；你担心的蛇这次不在描述里，不作解读。"
    assert (await submit(runtime, submission("dream", evidence, ok))).ok


async def test_timeline_is_checked_and_dream_has_no_event_timeline(runtime):
    result = await dream(runtime, "梦见一只小狗跟着我", ("一只小狗", "狗"))
    ref = result.data["interpretations"][0]["ref_id"]
    evidence = [dict(ref_id=ref, reading="梦见狗多与陪伴有关。")]
    timeline = [dict(period="明天", note="梦里的「蛇」预示你一定会发财。")]
    rejected = await submit(
        runtime, submission("dream", evidence, "这个梦反映陪伴需要。", timeline=timeline)
    )
    assert "timeline" in rejected.error
    plain = [dict(period="明天", note="可以和朋友聊聊。")]
    rejected = await submit(
        runtime, submission("dream", evidence, "这个梦反映陪伴需要。", timeline=plain)
    )
    assert "timeline" in rejected.error


async def test_name_claims_in_timeline_are_checked(runtime):
    await ask(runtime, "帮我看看“张三”这个名字")
    result = await invoke(runtime, "analyze_name", dict(surname="张", given="三"))
    ref = result.data["interpretations"][1]["ref_id"]
    timeline = [dict(period="本周", note="人格23，适合多沟通。")]
    value = submission(
        "name", [dict(ref_id=ref, reading="人格14。")], "张三人格14。", timeline=timeline
    )
    assert "不符" in (await submit(runtime, value)).error


# ---- 5. daily card orientation ----------------------------------------------------------


async def test_daily_card_orientation_and_followup(project):
    from app import create_runtime

    runtime = create_runtime(root=project, user_id="review-card", seed=1)
    try:
        with_birth(runtime)
        await ask(runtime, "今天运势怎么样？")
        result = await invoke(runtime, "daily_fortune", dict(date=runtime.session.calendar_anchor))
        card = result.data["card"]
        right, wrong = ("逆位", "正位") if card["reversed"] else ("正位", "逆位")
        evidence = [dict(ref_id=card["ref_id"], reading=f"每日一牌【{card['name']}】{wrong}。")]
        flipped = await submit(runtime, submission("daily", evidence, "今天稳步推进为宜。"))
        assert "方向错误" in flipped.error
        in_summary = submission(
            "daily",
            [dict(ref_id=card["ref_id"], reading="每日一牌提示稳步推进。")],
            f"今天稳步推进，每日一牌【{card['name']}】{wrong}。",
        )
        assert "方向错误" in (await submit(runtime, in_summary)).error
        good = f"今天稳步推进，每日一牌【{card['name']}】{right}。"
        evidence = [dict(ref_id=card["ref_id"], reading=good)]
        assert (await submit(runtime, submission("daily", evidence, good))).ok
        runtime.session.append_user("今天那张牌什么意思？")
        assert (await invoke(runtime, "read_reading", {})).ok
        follow = Reading.model_validate(
            submission("daily", evidence, f"这张【{card['name']}】{wrong}提醒你放慢。")
        )
        validator = runtime.registry.tools["submit_reading"].validator
        assert "方向错误" in validator(follow, runtime.session)
    finally:
        runtime.close()


async def test_daily_orientation_comparison_finishes_without_retry(runtime, scripted_model):
    from harness.loop import run_turn
    from harness.models import ModelResponse, ToolCall

    with_birth(runtime)
    await ask(runtime, "今天运势怎么样？")
    result = await invoke(runtime, "daily_fortune", dict(date=runtime.session.calendar_anchor))
    card = result.data["card"]
    right, other = ("逆位", "正位") if card["reversed"] else ("正位", "逆位")
    value = submission(
        "daily",
        [dict(ref_id=card["ref_id"])],
        "今天宜稳步推进。",
        sections=[
            dict(
                title="今天的牌面提示",
                body=(
                    f"每日一牌抽到{card['name']}{right}。"
                    f"{card['name']}{other}通常代表另一种侧重；{right}则表示不同的反思角度。"
                ),
                ref_ids=[card["ref_id"]],
            )
        ],
    )
    model = scripted_model(
        [ModelResponse(tool_calls=[ToolCall(id="submit", name="submit_reading", arguments=value)])]
    )
    outcome = await run_turn(
        runtime.session, "请继续完成解读。", model, runtime.registry, runtime.tracer, max_steps=1
    )
    assert outcome.status == "submit_reading"
    assert runtime.session.state["complete"]
    assert runtime.session.state["daily_result"]["card"] == card
    assert len(runtime.store.recent_readings(runtime.session.user_id)) == 1


# ---- 6-7. several names, unconfirmed forms ----------------------------------------------


async def two_names(runtime):
    await ask(runtime, "我叫赵杰，和“李逸”哪个五格更好？")
    first = await invoke(runtime, "analyze_name", dict(surname="赵", given="杰"))
    second = await invoke(runtime, "analyze_name", dict(surname="李", given="逸"))
    return first.data, second.data


EXPLAIN = "“杰”默认按繁体傑12画，写原字为8画，请按证件写法确认。"


async def test_grid_and_sancai_claims_are_bound_to_their_name(runtime):
    zhao, li = await two_names(runtime)
    assert (zhao["grids"]["人格"], li["grids"]["人格"]) == (26, 22)
    ref = zhao["interpretations"][1]["ref_id"]
    swapped = submission(
        "name", [dict(ref_id=ref, reading="人格26。")], "赵杰人格22，李逸人格26，写法请确认。"
    )
    swapped["advice"] = [EXPLAIN]
    assert "赵杰的人格22" in (await submit(runtime, swapped)).error
    sancai = submission(
        "name",
        [dict(ref_id=ref, reading=f"三才配置为{li['sancai']['key']}。")],
        "赵杰更稳。",
        advice=[EXPLAIN],
    )
    assert "三才" in (await submit(runtime, sancai)).error
    unbound = submission(
        "name", [dict(ref_id=ref, reading="人格26。")], "人格22更好。", advice=[EXPLAIN]
    )
    assert "哪个名字" in (await submit(runtime, unbound)).error
    form = submission(
        "name", [dict(ref_id=ref, reading="人格26。")], "傑按8画算。", advice=[EXPLAIN]
    )
    assert "笔画" in (await submit(runtime, form)).error
    good = submission(
        "name",
        [dict(ref_id=ref, reading="人格26。")],
        "赵杰人格26，李逸人格22。",
        advice=[EXPLAIN],
    )
    assert (await submit(runtime, good)).ok


async def test_unconfirmed_form_must_be_explained_even_if_omitted(runtime):
    zhao, _ = await two_names(runtime)
    ref = zhao["interpretations"][1]["ref_id"]
    silent = submission("name", [dict(ref_id=ref, reading="人格26。")], "赵杰人格26，体现成长。")
    error = (await submit(runtime, silent)).error
    assert "傑12画/杰8画" in error
    vague = submission("name", [dict(ref_id=ref, reading="人格26。")], "赵杰人格26，写法请确认。")
    assert "多种写法" in (await submit(runtime, vague)).error
    report = ReportInput(
        answer="赵杰人格26，体现成长。",
        points=[dict(ref_id=ref, text="人格26。")],
        confidence=LOW,
    )
    validator = runtime.session.output_validators["name"]
    assert "多种写法" in validator(as_reading(report, "name"), runtime.session.state)
    report.points[0].text = EXPLAIN
    assert validator(as_reading(report, "name"), runtime.session.state) is None


# ---- 8. 万俟 --------------------------------------------------------------------------


def test_wanqi_keeps_the_simple_form():
    result = analyze("万俟", "明")
    assert [(c["form"], c["strokes"]) for c in result["chars"]] == [
        ("万", 3),
        ("俟", 9),
        ("明", 8),
    ]
    assert result["grids"] == {"天格": 12, "人格": 17, "地格": 9, "外格": 4, "总格": 20}
    assert not result["ambiguities"]
    single = analyze("万", "明")
    assert single["chars"][0]["form"] == "萬" and single["ambiguities"][0]["char"] == "万"
