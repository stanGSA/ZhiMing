"""Dream interpretation through the pipeline with scripted models (P2.1 of the plan)."""

import json
import re

import pytest

from app import create_runtime
from harness.models import ModelResponse
from pipeline.dream import NO_DREAM, UNMATCHED_TITLE, Dream
from tests.pipeline.drafts import Composer

QUESTION = (
    "帮我解个梦：昨晚梦见牙齿一颗一颗掉下来，后来又被一条大狗追，还路过一个地铁闸机，醒来很慌。"
)
SYMBOLS = [
    {"phrase": "牙齿一颗一颗掉下来", "symbol": "掉牙"},
    {"phrase": "被一条大狗追", "symbol": "被追"},
    {"phrase": "地铁闸机", "symbol": "地铁闸机"},
]
DREAM_LINE = re.compile(r"^(R\d+)｜意象「(.+?)」", re.M)


def extraction(symbols=SYMBOLS):
    return lambda messages: json.dumps({"symbols": symbols}, ensure_ascii=False)


def symbols_in(messages) -> dict:
    """alias -> symbol, read from the fact sheet the writer was given."""
    return dict(DREAM_LINE.findall(messages[1]["content"]))


def written(messages, body="往往和最近的紧张感有关，如果你正在面对压力，可以先放慢节奏。") -> str:
    layers = "".join(
        f"【分层】第{i}层：它想提醒你的事\n{{{{{alias}}}}}{body}\n【引用】{alias}\n"
        for i, alias in enumerate(symbols_in(messages), 1)
    )
    return (
        "【表态】描述\n【摘要】这个梦主要反映你最近的紧张和不安。值得留意的是你对失去掌控的担心。\n"
        f"{layers}【建议】\n- 先休息：这几天早点睡。\n- 记下来：把梦里的感受写下来。\n【收尾】慢慢来。"
    )


def names_the_unmatched(messages) -> str:
    return written(messages).replace("【收尾】", "【分层】闸机\n地铁闸机象征阻碍。\n【收尾】")


def prophecy(messages) -> str:
    return written(messages, body="预示你下个月会遇到麻烦。")


@pytest.fixture
def make(project):
    runtimes = []

    def build(*replies, user_id="dream-user"):
        composer = Composer(*replies)
        runtime = create_runtime(
            root=project, user_id=user_id, seed=7, model=composer, mode="pipeline"
        )
        events = []
        runtime.tracer.listeners.append(events.append)
        runtimes.append(runtime)
        return runtime, composer, events

    yield build
    for runtime in runtimes:
        runtime.close()


def planned(events) -> list[str]:
    return [name for e in events if e["event"] == "tool_plan" for name in e["tool_names"]]


def purposes(events) -> list[str]:
    return [e["purpose"] for e in events if e["event"] == "model_response"]


async def test_a_dream_takes_an_extraction_and_a_writing_call(make):
    runtime, composer, events = make(extraction(), written)
    outcome = await runtime.turn(QUESTION)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 0, None)
    assert purposes(events) == ["intent", "compose"]
    assert planned(events) == ["start_reading", "lookup_dream_symbols", "submit_reading"]
    # The extractor saw the dictionary words code found; neither call had tools.
    (extract, tools), (write, write_tools) = composer.seen
    assert tools == [] and write_tools == []
    assert "掉牙" in extract[1]["content"] and "被追" in extract[1]["content"]
    # The writer saw R-numbers, never a full reference, and was told what not to name.
    assert "dream:" not in str(write)
    assert set(symbols_in(write).values()) == {"掉牙", "被追"}
    assert "未收录（不要提及，程序会另外说明）：地铁闸机" in write[1]["content"]
    saved = runtime.store.get_reading(runtime.session.user_id, outcome.data["reading_id"])
    sections = saved["output_json"]["sections"]
    # Code reports the unmatched symbol in a section of its own, citing the convention.
    assert sections[-1]["title"] == UNMATCHED_TITLE
    assert "「地铁闸机」未收录" in sections[-1]["body"]
    assert "「掉牙」" in outcome.text and "「被追」" in outcome.text
    assert runtime.store.unfinished_pipeline_run(runtime.session.user_id) is None


async def test_extracted_phrases_must_be_the_users_own_words(make):
    runtime, *_ = make()
    dream = Dream(runtime)
    kept = dream.accepted(
        [
            {"phrase": "牙齿一颗一颗掉下来", "symbol": "掉牙"},
            # Not in the question: dropped.
            {"phrase": "牙齿掉光了", "symbol": "掉牙"},
            # Not a normalisation of the phrase: the user's own words are kept instead.
            {"phrase": "大狗", "symbol": "老虎"},
            # A long phrase with an unsupported symbol has no short form to fall back to.
            {"phrase": "后来又被一条大狗追，还路过一个地铁闸机", "symbol": "蛇"},
            {"phrase": "被一条大狗追", "symbol": "被追"},
            {"phrase": "被一条大狗追", "symbol": "被追"},
            "not an object",
        ],
        QUESTION,
    )
    assert kept == [
        {"phrase": "牙齿一颗一颗掉下来", "symbol": "掉牙"},
        {"phrase": "大狗", "symbol": "大狗"},
        {"phrase": "被一条大狗追", "symbol": "被追"},
    ]


async def test_code_finds_dictionary_symbols_without_a_model(make):
    runtime, *_ = make()
    found = Dream(runtime).candidates(QUESTION)
    symbols = [item["symbol"] for item in found]
    assert "掉牙" in symbols and "被追" in symbols
    assert all(item["phrase"] in QUESTION for item in found)


@pytest.mark.parametrize(
    "reply",
    [
        "我没法按格式回答。",
        '{"symbols": "掉牙"}',
        ModelResponse(text='{"symbols": [', output_tokens=10, finish_reason="length"),
    ],
)
async def test_an_unusable_extraction_falls_back_to_code(make, reply):
    if isinstance(reply, ModelResponse):
        reply.input_tokens = 50
    runtime, _, events = make(reply, written)
    outcome = await runtime.turn(QUESTION)
    assert outcome.status == "submit_reading"
    stage = next(e for e in events if e.get("stage") == "extract")
    assert stage["source"] == "code" and stage["symbols"] >= 2
    # Code found only dictionary words, so nothing is reported unmatched.
    assert UNMATCHED_TITLE not in outcome.text


async def test_a_message_without_a_dream_is_asked_about(make):
    runtime, _, events = make(extraction([]))
    runtime.session.state["selected_systems"] = ["dream"]
    outcome = await runtime.turn("你好")
    assert outcome.status == "ask_user" and NO_DREAM in outcome.text
    assert purposes(events) == ["intent"]
    assert planned(events) == ["ask_user"]
    assert runtime.store.unfinished_pipeline_run(runtime.session.user_id) is None


async def test_nothing_matched_is_written_by_code(make):
    runtime, composer, events = make(extraction([{"phrase": "地铁闸机", "symbol": "地铁闸机"}]))
    outcome = await runtime.turn("我梦见自己站在地铁闸机前面，怎么也刷不过去。")
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, "no_symbol")
    assert purposes(events) == ["intent"]
    assert "都没有收录" in outcome.text and "「地铁闸机」未收录" in outcome.text


async def test_naming_an_unmatched_symbol_is_repaired(make):
    runtime, composer, events = make(extraction(), names_the_unmatched, written)
    outcome = await runtime.turn(QUESTION)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (3, 1, None)
    assert "地铁闸机" in info["problems"][0][0] and "未在词典中命中" in info["problems"][0][0]
    # The problem was found before submission: one submission only.
    assert planned(events).count("submit_reading") == 1
    assert "地铁闸机”未在词典中命中" in composer.seen[2][0][-1]["content"]


async def test_a_prophecy_twice_degrades_to_the_meanings(make):
    runtime, _, events = make(extraction(), prophecy, prophecy)
    outcome = await runtime.turn(QUESTION)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (3, 1, "keywords")
    assert all("预兆" in problems[0] for problems in info["problems"])
    saved = runtime.store.get_reading(runtime.session.user_id, outcome.data["reading_id"])
    titles = [s["title"] for s in saved["output_json"]["sections"]]
    assert titles == ["「掉牙」", "「被追」", UNMATCHED_TITLE]


async def test_a_high_risk_dream_with_a_safety_failure_twice_ends_in_a_safety_reply(make):
    sure = lambda m: written(m, body="说明你一定会生病，必须停药。")  # noqa: E731
    runtime, *_ = make(extraction(), sure, sure)
    outcome = await runtime.turn(QUESTION.replace("醒来很慌", "醒来担心身体健康"))
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["degraded"] == "safety"
    saved = runtime.store.get_reading(runtime.session.user_id, outcome.data["reading_id"])
    assert saved["output_json"]["sections"] == []
    assert saved["output_json"]["safety"]["flag"] is True


async def test_an_interrupted_dream_resumes_without_another_extraction(make):
    runtime, _, events = make(extraction(), RuntimeError("connection reset"), written)
    first = await runtime.turn(QUESTION)
    assert first.status != "submit_reading"
    assert runtime.store.unfinished_pipeline_run(runtime.session.user_id)["stage"] == "computed"
    second = await runtime.turn("继续")
    assert second.status == "submit_reading"
    assert purposes(events) == ["intent", "compose"]
    assert planned(events).count("lookup_dream_symbols") == 1


@pytest.mark.parametrize(
    "message",
    [
        # Another system named outside the dream page: the agent loop.
        "我梦见掉牙，用塔罗帮我看看",
        "梦见考试，顺便看看我的八字",
        # No dream at all outside the dream page.
        "今天心情不好",
        # A follow-up on a saved dream reading stays with the agent loop in P2.
        "上次的解梦里说的掉牙是什么意思",
    ],
)
async def test_messages_the_dream_pipeline_leaves_to_the_agent_loop(make, message):
    runtime, *_ = make()
    assert Dream(runtime).detect(runtime, message) is None


async def test_the_dream_page_and_plain_dream_questions_are_routed_here(make):
    runtime, *_ = make()
    dream = Dream(runtime)
    assert dream.detect(runtime, "昨晚做了个噩梦，梦见被追").kind == "new"
    runtime.session.state["selected_systems"] = ["dream"]
    assert dream.detect(runtime, "牙齿一颗一颗掉下来是怎么回事").kind == "new"
    runtime.session.state["selected_systems"] = ["tarot"]
    assert dream.detect(runtime, "梦见被追") is None


async def test_a_refused_code_reading_returns_the_refusal_and_keeps_the_run(make, monkeypatch):
    from harness.models import TurnOutcome
    from pipeline.runner import PipelineRunner, Stopped

    async def refuse(self, run, args):
        raise Stopped(TurnOutcome(status="retry_limit", text="提交被拒"))

    monkeypatch.setattr(PipelineRunner, "submit", refuse)
    runtime, *_ = make(extraction([{"phrase": "地铁闸机", "symbol": "地铁闸机"}]))
    outcome = await runtime.turn("我梦见自己站在地铁闸机前面，怎么也刷不过去。")
    assert (outcome.status, outcome.text) == ("retry_limit", "提交被拒")
    assert runtime.store.unfinished_pipeline_run(runtime.session.user_id)["stage"] == "computed"


# ---- PR #40 review --------------------------------------------------------------------------

MISSED = "昨晚梦见掉牙，还遇到地铁闸机。"
SEVEN = "昨晚梦见考试、迷路、游泳、爬山、开车、跳舞、哭，帮我解梦。"
SEVEN_SYMBOLS = [
    {"phrase": w, "symbol": w} for w in ("考试", "迷路", "游泳", "爬山", "开车", "跳舞", "哭")
]


def with_layer(text):
    return lambda m: written(m).replace("【建议】", f"【分层】另一层\n{text}\n【建议】")


async def test_a_symbol_the_extraction_missed_cannot_be_interpreted(make):
    """Review 1: the checks must not depend on the extraction naming every symbol."""
    only_teeth = extraction([{"phrase": "掉牙", "symbol": "掉牙"}])
    runtime, composer, events = make(only_teeth, with_layer("地铁闸机象征阻碍。"), written)
    outcome = await runtime.turn(MISSED)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["repairs"], info["degraded"]) == (1, None)
    assert info["problems"][0] == ["“地铁闸机”不在事实表里，只能解读事实表里的意象"]
    assert "地铁闸机象征" not in outcome.text
    assert planned(events).count("submit_reading") == 1


@pytest.mark.parametrize(
    "text",
    [
        "地铁闸机象征阻碍。",
        "梦见地铁闸机，说明你遇到了阻碍。",
        "你还梦见了地铁闸机。这个画面象征阻碍。",
        "地铁闸机这个画面往往和压力有关。",
        "闸机常和被卡住的感觉有关。",
        "地铁闸机，象征阻碍。",
        "梦里的地铁闸机，往往代表你对受阻的焦虑。",
        "地铁闸机这个场景，反映你对规则的抗拒。",
        "地铁闸机常常联系到阻碍。",
        "地铁闸机让人联想到阻碍。",
        "令人焦虑的地铁闸机，象征阻碍。",
        "地铁闸机让我焦虑，象征阻碍。",
        "地铁闸机这种感受往往反映最近的压力。",
    ],
)
async def test_interpreting_dream_content_outside_the_fact_sheet_is_refused(make, text):
    runtime, *_ = make(extraction([{"phrase": "掉牙", "symbol": "掉牙"}]), written)
    runtime.session.state["selected_systems"] = ["dream"]
    await runtime.turn(MISSED)
    assert Dream(runtime).unlisted([text], runtime.session), text


@pytest.mark.parametrize(
    "text",
    [
        "「掉牙」往往和焦虑有关，如果你正在面对压力，可以先放慢节奏。",
        "梦见掉牙常和担心失去掌控有关。",
        "这个梦主要反映你最近的紧张和不安。",
        "醒来很慌，这种感受往往反映最近的压力。",
        "你在梦里很慌，这往往反映压力。",
        "你梦见掉牙，还遇到了别的场景，这些都提示你先照顾好自己。",
        "地铁闸机还没有收录，醒来很慌这种感受往往反映最近的压力。",
        "你还梦见了地铁闸机，但「掉牙」往往和焦虑有关。",
    ],
)
async def test_interpreting_the_fact_sheet_and_the_feelings_is_accepted(make, text):
    runtime, *_ = make(extraction([{"phrase": "掉牙", "symbol": "掉牙"}]), written)
    await runtime.turn(MISSED.replace("。", "，醒来很慌。"))
    assert Dream(runtime).unlisted([text], runtime.session) == [], text


async def test_only_invalid_extracted_items_fall_back_to_code(make):
    """Review 1: a list of invalid items is not the model saying there is no dream."""
    invalid = extraction([{"phrase": "牙齿掉光了", "symbol": "掉牙"}])
    runtime, _, events = make(invalid, written)
    outcome = await runtime.turn("昨晚梦见掉牙。")
    assert outcome.status == "submit_reading"
    stage = next(e for e in events if e.get("stage") == "extract")
    assert (stage["source"], stage["symbols"]) == ("code", 1)
    assert "「掉牙」" in outcome.text


@pytest.mark.parametrize(
    "text",
    [
        "地铁闸机，象征阻碍。",
        "梦里的地铁闸机，往往代表你对受阻的焦虑。",
        "地铁闸机常常联系到阻碍。",
    ],
)
async def test_an_omitted_symbol_cannot_be_saved_by_splitting_its_subject(make, text):
    runtime, _, events = make(
        extraction([{"phrase": "掉牙", "symbol": "掉牙"}]), with_layer(text), written
    )
    outcome = await runtime.turn(MISSED)
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["repairs"] == 1
    assert planned(events).count("submit_reading") == 1
    saved = runtime.store.get_reading(runtime.session.user_id, outcome.data["reading_id"])
    assert not any(text in section["body"] for section in saved["output_json"]["sections"])


async def test_an_empty_extraction_still_asks(make):
    runtime, *_ = make(extraction([]))
    outcome = await runtime.turn("昨晚梦见掉牙。")
    assert outcome.status == "ask_user"


def broken(messages):
    return "这不是标记文本"


@pytest.mark.parametrize("misses", [False, True])
async def test_many_symbols_degrade_to_at_most_six_layers(make, misses):
    """Review 2: twelve symbols may be matched, a reading holds six layers."""
    symbols = SEVEN_SYMBOLS + ([{"phrase": "地铁闸机", "symbol": "地铁闸机"}] if misses else [])
    question = SEVEN.replace("，帮我", "、地铁闸机，帮我") if misses else SEVEN
    runtime, *_ = make(extraction(symbols), broken, broken)
    outcome = await runtime.turn(question)
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["degraded"] == "keywords"
    sections = outcome.data["reading"]["sections"]
    assert len(sections) <= 6
    # No matched symbol is dropped to fit.
    cited = {ref for section in sections for ref in section["ref_ids"]}
    symbols_cited = [r for r in cited if ":convention:" not in r and not r.endswith(":unmatched")]
    assert len(symbols_cited) == 7
    assert (sections[-1]["title"] == UNMATCHED_TITLE) is misses


async def test_many_symbols_degrade_within_the_limit_without_any_model_call(make):
    """Review 2: with no budget code extracts the symbols and writes the reading alone."""
    runtime, _, events = make()
    runtime.token_budget = 1
    outcome = await runtime.turn(SEVEN)
    assert outcome.status == "submit_reading"
    assert purposes(events) == []
    assert outcome.data["pipeline"]["degraded"] == "keywords"
    assert len(outcome.data["reading"]["sections"]) <= 6


@pytest.mark.parametrize("page", [["dream"], None])
@pytest.mark.parametrize(
    "message",
    [
        "刚才那个梦里的掉牙为什么和压力有关？",
        "这个梦里的掉牙具体是什么意思？",
        "那段解读里说的失去掌控是指什么？",
    ],
)
async def test_a_follow_up_on_a_saved_dream_stays_with_the_agent_loop(make, page, message):
    """Review 3: a follow-up must not start a new reading."""
    runtime, *_ = make(extraction(), written)
    runtime.session.state["selected_systems"] = ["dream"]
    first = await runtime.turn(QUESTION)
    assert first.status == "submit_reading"
    runtime.session.state["selected_systems"] = page
    assert Dream(runtime).detect(runtime, message) is None


async def test_a_new_dream_after_a_saved_one_is_a_new_reading(make):
    runtime, *_ = make(extraction(), written)
    await runtime.turn(QUESTION)
    assert (
        Dream(runtime).detect(runtime, "今天又梦见被一条大狗追了，这次是什么意思？").kind == "new"
    )


class AcceptingJudge:
    async def check(self, texts, session):
        return None


async def test_with_the_policy_judge_a_safety_failure_still_ends_in_the_safety_reply(make):
    """Review 4: the prophecy rule catching the draft first must not hide its safety class."""
    sure = lambda m: written(m, body="说明你一定会生病，必须停药。")  # noqa: E731
    runtime, _, events = make(extraction([{"phrase": "掉牙", "symbol": "掉牙"}]), sure, sure)
    runtime.session.policy_judge = AcceptingJudge()
    outcome = await runtime.turn("昨晚梦见掉牙，醒来担心健康。")
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert info["degraded"] == "safety"
    # The reported problem is the dream rule; the safety class was recorded on its own.
    assert "预兆" in info["problems"][0][0]
    assert [e["rules"] for e in events if e.get("stage") == "safety"] == [
        ["certainty", "hard_claim"]
    ] * 2
    assert outcome.data["reading"]["sections"] == []


@pytest.mark.parametrize("judge", [False, True])
async def test_a_medication_directive_alone_ends_in_safety_degradation(make, judge):
    bad = lambda messages: written(messages, body="提醒你必须停药。")  # noqa: E731
    runtime, _, events = make(extraction([{"phrase": "掉牙", "symbol": "掉牙"}]), bad, bad)
    if judge:
        runtime.session.policy_judge = AcceptingJudge()
    outcome = await runtime.turn("昨晚梦见掉牙。")
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["degraded"] == "safety"
    assert outcome.data["reading"]["sections"] == []
    assert [e["rules"] for e in events if e.get("stage") == "safety"] == [["hard_claim"]] * 2


@pytest.mark.parametrize(
    "message",
    ["我最近老做同一个梦：被人追着一直跑。这个梦说明什么？", "昨晚做了个怪梦，梦里在下雨"],
)
async def test_a_dream_told_without_梦见_is_still_a_dream(make, message):
    """Found by the P2 dataset routing test: 做同一个梦 left the dream to the agent loop."""
    runtime, *_ = make()
    assert Dream(runtime).detect(runtime, message).kind == "new"


# ---- P2 pilot tuning: what the pilot's drafts were refused for, and what must stay refused --

GRANDMOTHER = "梦到去世的奶奶在老房子里给我做饭，醒来就哭了。这个梦是什么意思？"
GRANDMOTHER_SYMBOLS = [
    {"phrase": "去世的奶奶", "symbol": "已故亲人"},
    {"phrase": "老房子", "symbol": "房子"},
    {"phrase": "做饭", "symbol": "做饭"},
    {"phrase": "哭", "symbol": "哭"},
]
CHASED = "我最近老做同一个梦：被人追着一直跑，跑进考场才发现自己什么都没复习。这个梦说明什么？"
HOSPITAL = "梦见自己生病住院了，是不是预示我的健康要出问题？要不要去做检查？"
MALL = "梦见自己在一个巨大的商场里迷路，手机也没电了，到处找不到出口。这个梦怎么理解？"
PILOT_SYMBOLS = {
    GRANDMOTHER: GRANDMOTHER_SYMBOLS,
    CHASED: [{"phrase": "被人追", "symbol": "被追"}, {"phrase": "考场", "symbol": "考场"}],
    HOSPITAL: [{"phrase": "生病", "symbol": "生病"}, {"phrase": "住院", "symbol": "住院"}],
    MALL: [
        {"phrase": "商场", "symbol": "商场"},
        {"phrase": "迷路", "symbol": "迷路"},
        {"phrase": "手机", "symbol": "手机"},
        {"phrase": "找不到出口", "symbol": "找不到出口"},
    ],
}


async def problems_of(make, question, text):
    runtime, *_ = make(extraction(PILOT_SYMBOLS[question]), written)
    runtime.session.state["selected_systems"] = ["dream"]
    await runtime.turn(question)
    return Dream(runtime).problems([text], runtime.session)


@pytest.mark.parametrize(
    "question, text",
    [
        # The user's own word for a matched symbol is that symbol (去世的奶奶 → 去世的亲人).
        (GRANDMOTHER, "梦里奶奶为你做饭，象征着被照顾、被滋养的感觉。"),
        # Words between two matched symbols of one phrase are not other dream content.
        (GRANDMOTHER, "奶奶在老房子里给你做饭，这个画面往往反映你对被照顾的怀念。"),
        # The dream as a whole may be interpreted, even right after a detail is retold.
        (CHASED, "同一个梦反复出现，往往提示这份压力还在。"),
        (CHASED, "你梦里被人追着一直跑，这个梦说明你最近压力不小。"),
        # The question the user asks is not something dreamed.
        (HOSPITAL, "这个梦不是健康的预兆，更多反映你最近很累。"),
        # What the fact sheet itself says about a hit (手机: 没电或损坏) is in the fact sheet.
        (MALL, "「手机」没电，往往和沟通受阻的感受有关。"),
    ],
)
async def test_what_the_pilot_refused_on_the_dream_and_the_fact_sheet_is_accepted(
    make, question, text
):
    assert await problems_of(make, question, text) == [], text


@pytest.mark.parametrize(
    "question, text",
    [
        # Only the head noun of the user's phrase counts: 去世 stays another symbol (死亡).
        (GRANDMOTHER, "梦见死亡，往往象征一段关系的结束。"),
        # A retold detail is still not interpreted through a generic subject.
        (CHASED, "你梦里一直跑，这个画面说明你想逃开什么。"),
        # “这个梦” does not cover content named inside its own subject.
        (CHASED, "这个梦里的考场象征被评价的压力。"),
        # Unmatched symbols stay unmatched, and so does what the fact sheet does not say.
        (HOSPITAL, "梦见住院往往反映你希望被照顾。"),
        # 找不到出口 with 迷路 matched is that symbol (owner, r5); without 迷路 it stays
        # refused, see test_what_the_lost_construction_does_not_cover_is_still_refused.
        (MALL, "巨大的商场往往代表选择太多。"),
    ],
)
async def test_what_the_fact_sheet_does_not_hold_is_still_refused(make, question, text):
    assert await problems_of(make, question, text), text


async def test_a_dream_told_within_a_question_is_still_dream_content(make):
    """Only clauses that ask and tell no dream are left out of the dream's content."""
    question = "梦见掉牙，还梦见地铁闸机是什么意思？"
    runtime, *_ = make(extraction([{"phrase": "掉牙", "symbol": "掉牙"}]), written)
    runtime.session.state["selected_systems"] = ["dream"]
    await runtime.turn(question)
    assert Dream(runtime).unlisted(["地铁闸机象征阻碍。"], runtime.session)


async def test_a_degraded_reading_gives_the_dictionarys_sentence_for_each_symbol(make):
    runtime, *_ = make(extraction(), prophecy, prophecy)
    outcome = await runtime.turn(QUESTION)
    assert outcome.data["pipeline"]["degraded"] == "keywords"
    bodies = [s["body"] for s in outcome.data["reading"]["sections"]]
    # 掉牙's first sentence in the dictionary, not only its keywords (“掉牙、身体”).
    assert "「掉牙」：梦见掉牙，常与担心失去掌控" in bodies[0]
    assert "这个意象常和" not in bodies[0]


async def test_each_drafts_problems_are_traced_as_text(make):
    runtime, _, events = make(extraction(), names_the_unmatched, written)
    outcome = await runtime.turn(QUESTION)
    traced = [e for e in events if e.get("stage") == "problems"]
    assert [e["draft"] for e in traced] == [1]
    assert traced[0]["problems"] == outcome.data["pipeline"]["problems"][0]
    saved = runtime.store.get_reading(runtime.session.user_id, outcome.data["reading_id"])
    assert saved["pipeline_json"]["problems"] == outcome.data["pipeline"]["problems"]


async def test_a_dream_repair_lists_the_symbols_without_the_tarot_seat_wording(make):
    runtime, composer, _ = make(extraction(), names_the_unmatched, written)
    await runtime.turn(QUESTION)
    request = composer.seen[2][0][-1]["content"]
    assert "可引用的编号只有：R1=「掉牙」；R2=「被追」。" in request
    assert "牌位" not in request


def test_tarot_repairs_keep_the_seat_wording():
    from pipeline import compose
    from pipeline.factsheet import Fact

    facts = [Fact("R1", "ref", "现在位", "【星星】正位", "R1｜…")]
    tarot = compose.repair_messages([], "稿", ["问题"], facts)[-1]["content"]
    assert "R1=现在位位【星星】正位。写某个牌位时，只能用该牌位对应的编号。" in tarot
    other = compose.repair_messages([], "稿", ["问题"], facts, positions=False)[-1]["content"]
    assert other.endswith("可引用的编号只有：R1=【星星】正位。")


async def test_the_users_phrase_alias_passes_the_final_submission_validator(make):
    text = "梦里奶奶为你做饭，象征着被照顾、被滋养的感觉。"
    runtime, _, events = make(extraction(GRANDMOTHER_SYMBOLS), with_layer(text), written)
    outcome = await runtime.turn(GRANDMOTHER)
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["repairs"] == 0
    assert outcome.data["pipeline"]["degraded"] is None
    assert text in outcome.text
    assert planned(events).count("submit_reading") == 1


@pytest.mark.parametrize("alias", ["爷爷", "祖父母"])
async def test_a_phrase_alias_does_not_authorise_its_other_dictionary_synonyms(make, alias):
    runtime, *_ = make(
        extraction(GRANDMOTHER_SYMBOLS), with_layer(f"「{alias}」象征被照顾。"), written
    )
    outcome = await runtime.turn(GRANDMOTHER)
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["repairs"] == 1
    assert "不是本次命中的意象" in outcome.data["pipeline"]["problems"][0][0]


async def test_phrase_aliases_are_not_inherited_by_the_single_agent_validator(make):
    from common.schemas import Reading
    from plugins.dream.validation import validate_output

    runtime, *_ = make(extraction(GRANDMOTHER_SYMBOLS), written)
    outcome = await runtime.turn(GRANDMOTHER)
    reading = Reading.model_validate(outcome.data["reading"])
    reading.summary = "梦里奶奶象征被照顾。"
    assert "pipeline_run" not in runtime.session.state
    assert "不是本次命中的意象" in validate_output(
        reading, runtime.session.state, Dream(runtime).matcher
    )


@pytest.mark.parametrize(
    "dialogue",
    [
        "有人问我能不能打开地铁闸机。",
        "有人对我说：“帮我打开地铁闸机，好吗？”",
        "“能不能打开地铁闸机？”",
        "有人问我：能不能打开地铁闸机？",
        "能不能打开地铁闸机我已经记不清了。",
    ],
)
async def test_questions_inside_the_dream_do_not_hide_omitted_symbols(make, dialogue):
    text = "地铁闸机象征阻碍。"
    runtime, _, events = make(
        extraction([{"phrase": "掉牙", "symbol": "掉牙"}]), with_layer(text), written
    )
    outcome = await runtime.turn(f"梦见掉牙，{dialogue}")
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["repairs"] == 1
    assert "地铁闸机" in outcome.data["pipeline"]["problems"][0][0]
    assert text not in outcome.text
    assert planned(events).count("submit_reading") == 1


@pytest.mark.parametrize("noun", ["门把手", "着装"])
async def test_function_characters_inside_nouns_do_not_hide_omitted_symbols(make, noun):
    text = f"{noun}，往往反映你想逃避。"
    runtime, _, events = make(
        extraction([{"phrase": "掉牙", "symbol": "掉牙"}]), with_layer(text), written
    )
    outcome = await runtime.turn(f"梦见掉牙，接着我看到{noun}。")
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["repairs"] == 1
    assert noun in outcome.data["pipeline"]["problems"][0][0]
    assert text not in outcome.text
    assert planned(events).count("submit_reading") == 1


# ---- P2 r2: the refusals read in the drafts' problem texts --------------------------------


async def test_echoing_whether_to_get_checked_does_not_end_in_the_safety_reply(make):
    """r2 dream_hospital_health#2: both drafts were refused for “不要去做检查” inside
    “要不要去做检查”, and the reading degraded to the safety template."""
    echo = lambda m: written(  # noqa: E731
        m, body="关于要不要去做检查：梦本身不能说明身体状况，如有不适请及时就医。"
    )
    runtime, *_ = make(extraction(PILOT_SYMBOLS[HOSPITAL]), echo)
    runtime.session.state["selected_systems"] = ["dream"]
    outcome = await runtime.turn(HOSPITAL)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None)


async def test_a_reaction_or_state_is_not_reported_as_an_unmatched_symbol(make):
    """r2 dream_flood_and_snake#2: 不敢下去 was extracted, then refused as unmatched."""
    question = "梦见家里进水了，水里还有一条蛇游来游去，我站在床上不敢下去。帮我解一下这个梦。"
    symbols = [
        {"phrase": "水", "symbol": "水"},
        {"phrase": "蛇", "symbol": "蛇"},
        {"phrase": "站在床上", "symbol": "床"},
        {"phrase": "不敢下去", "symbol": "不敢下去"},
        {"phrase": "游来游去", "symbol": "一直游"},
        {"phrase": "家里进水了", "symbol": "家里进水了"},
    ]
    runtime, *_ = make(extraction(symbols), written)
    runtime.session.state["selected_systems"] = ["dream"]
    await runtime.turn(question)
    result = Dream(runtime).result(runtime.session.state)
    # 家里进水了 has no negation or degree: it stays an unmatched symbol.
    assert "不敢下去" not in result["misses"]
    assert {h["key"] for h in result["hits"]} >= {"水", "蛇", "床"}
    # Retelling it is allowed; interpreting it is still content outside the fact sheet.
    dream = Dream(runtime)
    assert dream.problems(["你站在床上不敢下去，醒来还心有余悸。"], runtime.session) == []
    assert dream.problems(["不敢下去，说明你在用退守的方式保护自己。"], runtime.session)


async def test_a_refused_draft_is_traced_with_its_text(make):
    runtime, _, events = make(extraction(), names_the_unmatched, written)
    await runtime.turn(QUESTION)
    traced = next(e for e in events if e.get("stage") == "problems")
    assert "地铁闸机象征阻碍" in traced["text"]


@pytest.mark.parametrize("noun", ["未婚夫", "未婚妻", "不倒翁"])
async def test_unmatched_nouns_with_negative_characters_still_finish_a_reading(make, noun):
    runtime, *_ = make(extraction([{"phrase": noun, "symbol": noun}]))
    outcome = await runtime.turn(f"我梦见了{noun}，这是什么意思？")
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["degraded"] == "no_symbol"
    assert f"「{noun}」未收录" in outcome.text


async def test_a_mixed_dream_reports_the_unmatched_noun_without_interpreting_it(make):
    runtime, *_ = make(
        extraction([{"phrase": "蛇", "symbol": "蛇"}, {"phrase": "未婚夫", "symbol": "未婚夫"}]),
        written,
    )
    outcome = await runtime.turn("我梦见蛇和未婚夫，这是什么意思？")
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["repairs"] == 0
    assert "「未婚夫」未收录" in outcome.text
    assert Dream(runtime).problems(["未婚夫象征你最近的压力。"], runtime.session)


def test_only_complete_reaction_phrases_are_filtered(make):
    runtime, *_ = make()
    states = ["不敢下去", "找不到出口", "没复习", "一直跑"]
    nouns = ["不明飞行物", "不敢下去的孩子", "没有眼睛的娃娃", "一直跑的机器人"]
    items = [{"phrase": word, "symbol": word} for word in [*states, *nouns]]
    kept = Dream(runtime).accepted(items, "、".join([*states, *nouns]))
    assert {item["symbol"] for item in kept} == set(nouns)


@pytest.mark.parametrize("text", ["只要不要去医院就行。", "出现这些副作用不用去医院。"])
async def test_non_question_discouragement_in_a_dream_draft_is_not_submitted(make, text):
    def bad(messages):
        return written(messages).replace("【收尾】慢慢来。", f"【收尾】{text}")

    runtime, _, events = make(extraction(PILOT_SYMBOLS[HOSPITAL]), bad, bad)
    runtime.session.state["selected_systems"] = ["dream"]
    outcome = await runtime.turn(HOSPITAL)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 1, "safety")
    assert text not in outcome.text
    assert planned(events).count("submit_reading") == 1


# ---- P2 r3: the two false rejections located in plugins/dream/validation.py::ungrounded ----

TEETH = "帮我解个梦：昨晚梦见牙齿一颗一颗掉下来，醒来心里很慌。"
TEETH_SYMBOLS = [{"phrase": "牙齿一颗一颗掉下来", "symbol": "掉牙"}]
R3_GRANDMOTHER_SYMBOLS = [
    {"phrase": "去世的奶奶", "symbol": "去世的亲人"},
    {"phrase": "老房子", "symbol": "房子"},
    {"phrase": "给我做饭", "symbol": "做饭"},
]
HOME_MEAL = (
    "如果你最近确实有些累，不妨给自己留一点像“回家吃饭”那样的松弛时刻，"
    "比如好好做一顿饭、早点休息，或回一趟让你安心的地方。"
)


@pytest.mark.parametrize(
    "question, symbols, text",
    [
        # r3 dream_teeth_falling#3: retelling the phrase that matched 掉牙 named 牙齿.
        (TEETH, TEETH_SYMBOLS, "你梦见牙齿一颗一颗掉下来。"),
        # r3 dream_late_grandmother#1: a quoted everyday phrase was fuzzily read as 吃饭.
        (GRANDMOTHER, R3_GRANDMOTHER_SYMBOLS, HOME_MEAL),
    ],
)
async def test_the_r3_false_rejections_pass_the_final_submission(make, question, symbols, text):
    runtime, _, events = make(extraction(symbols), with_layer(text), written)
    outcome = await runtime.turn(question)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["repairs"], info["degraded"]) == (0, None), info["problems"]
    assert text in outcome.text
    assert planned(events).count("submit_reading") == 1


@pytest.mark.parametrize(
    "question, symbols, text",
    [
        # 牙齿 outside the matched phrase is still another, unmatched symbol.
        (TEETH, TEETH_SYMBOLS, "梦见牙齿往往象征自我形象。"),
        # The exact alias in quotes, and any near match in 「」, still name a symbol.
        (GRANDMOTHER, R3_GRANDMOTHER_SYMBOLS, "梦里的“吃饭”象征被照顾。"),
        (GRANDMOTHER, R3_GRANDMOTHER_SYMBOLS, "「回家吃饭」象征被照顾。"),
        (GRANDMOTHER, R3_GRANDMOTHER_SYMBOLS, "梦见吃饭，说明你需要被照顾。"),
    ],
)
async def test_what_the_r3_fixes_must_still_refuse(make, question, symbols, text):
    runtime, *_ = make(extraction(symbols), with_layer(text), written)
    outcome = await runtime.turn(question)
    info = outcome.data["pipeline"]
    assert info["repairs"] == 1
    assert "不是本次命中的意象" in info["problems"][0][0]


async def test_the_matched_phrase_is_not_inherited_by_the_single_agent_validator(make):
    from common.schemas import Reading
    from plugins.dream.validation import validate_output

    runtime, *_ = make(extraction(TEETH_SYMBOLS), written)
    outcome = await runtime.turn(TEETH)
    reading = Reading.model_validate(outcome.data["reading"])
    reading.summary = "你梦见牙齿一颗一颗掉下来。"
    assert "pipeline_run" not in runtime.session.state
    assert "不是本次命中的意象" in validate_output(
        reading, runtime.session.state, Dream(runtime).matcher
    )


# ---- PR #46 review: keep the r3 fixes without authorising other symbols -------------------


@pytest.mark.parametrize(
    "text",
    [
        "梦里的“回家吃饭”象征被照顾。",
        "【回家吃饭】往往反映你需要被照顾。",
        "《回家吃饭》的场景象征被照顾。",
        "梦见“回家吃饭”。",
        # No fuzzy match for the whole quote: the inner alias must still be checked.
        "“吃饭休息”象征被照顾。",
    ],
)
async def test_pr46_quoted_interpretations_of_unhit_symbols_are_repaired(make, text):
    runtime, _, events = make(extraction(R3_GRANDMOTHER_SYMBOLS), with_layer(text), written)
    outcome = await runtime.turn(GRANDMOTHER)
    info = outcome.data["pipeline"]
    assert outcome.status == "submit_reading"
    assert (info["repairs"], info["degraded"]) == (1, None)
    assert "吃饭" in info["problems"][0][0]
    assert text not in outcome.text
    assert planned(events).count("submit_reading") == 1


@pytest.mark.parametrize(
    "phrase,symbol,text",
    [
        ("猫和蛇", "蛇", "梦见猫和蛇象征你最近需要独立和警惕。"),
        # A suffix alias of a broad source phrase is not an alias of the hit either.
        ("蛇和猫", "蛇", "梦见猫象征你最近需要独立。"),
        ("猫和蛇", "蛇", "梦里的“猫和蛇”象征你最近需要独立和警惕。"),
        ("猫和牙齿一颗一颗掉下来", "掉牙", "梦见猫和牙齿一颗一颗掉下来象征压力。"),
        ("牙齿一颗一颗掉下来和猫", "掉牙", "梦见猫象征你最近需要独立。"),
    ],
)
async def test_pr46_a_broad_source_phrase_does_not_authorise_other_symbols(
    make, phrase, symbol, text
):
    runtime, _, events = make(
        extraction([{"phrase": phrase, "symbol": symbol}]), with_layer(text), written
    )
    outcome = await runtime.turn(f"我梦见{phrase}，醒来很紧张。")
    info = outcome.data["pipeline"]
    assert outcome.status == "submit_reading"
    assert (info["repairs"], info["degraded"]) == (1, None)
    assert "猫" in info["problems"][0][0]
    assert text not in outcome.text
    assert planned(events).count("submit_reading") == 1


async def test_pr46_a_normalised_hit_with_other_content_can_still_be_retold(make):
    phrase = "猫和牙齿一颗一颗掉下来"
    text = "你梦见牙齿一颗一颗掉下来。"
    runtime, *_ = make(extraction([{"phrase": phrase, "symbol": "掉牙"}]), with_layer(text))
    outcome = await runtime.turn(f"我梦见{phrase}，醒来很紧张。")
    info = outcome.data["pipeline"]
    assert outcome.status == "submit_reading"
    assert (info["repairs"], info["degraded"]) == (0, None), info["problems"]
    assert text in outcome.text


@pytest.mark.parametrize("phrase", ["去世的奶奶", "梦到去世的奶奶"])
async def test_pr46_a_suffix_inside_the_hits_literal_alias_still_names_the_hit(make, phrase):
    text = "梦里奶奶象征被照顾。"
    runtime, *_ = make(extraction([{"phrase": phrase, "symbol": "去世的亲人"}]), with_layer(text))
    outcome = await runtime.turn(GRANDMOTHER)
    info = outcome.data["pipeline"]
    assert outcome.status == "submit_reading"
    assert (info["repairs"], info["degraded"]) == (0, None), info["problems"]
    assert text in outcome.text


@pytest.mark.parametrize("pipeline", [False, True])
async def test_pr46_the_submission_validator_checks_quoted_interpretations(make, pipeline):
    from common.schemas import Reading
    from plugins.dream.validation import validate_output

    runtime, *_ = make(extraction(R3_GRANDMOTHER_SYMBOLS), written)
    outcome = await runtime.turn(GRANDMOTHER)
    reading = Reading.model_validate(outcome.data["reading"])
    reading.summary = "梦里的“回家吃饭”象征被照顾。"
    state = dict(runtime.session.state)
    if pipeline:
        state["pipeline_run"] = {"system": "dream"}
    assert "吃饭" in (validate_output(reading, state, Dream(runtime).matcher) or "")


async def test_the_r4_teeth_variant_is_the_matched_symbol(make):
    """r4 dream_teeth_falling#1: 一颗颗 is the same controlled phrase as 一颗一颗."""
    text = "梦里牙齿一颗颗掉下来，醒来心慌，可能和最近担心失去掌控、形象受损或表达受阻有关。"
    runtime, _, events = make(extraction(TEETH_SYMBOLS), with_layer(text), written)
    outcome = await runtime.turn(TEETH)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None)
    assert text in outcome.text


@pytest.mark.parametrize("text", ["被老虎追象征最近的压力。", "梦里的“被老虎追”象征压力。"])
async def test_a_normalised_chase_does_not_authorise_another_pursuer(make, text):
    symbols = [{"phrase": "被一条大狗追", "symbol": "被追"}]
    runtime, *_ = make(extraction(symbols), with_layer(text), written)
    outcome = await runtime.turn("帮我解梦：梦见被一条大狗追，醒来很慌。")
    info = outcome.data["pipeline"]
    assert outcome.status == "submit_reading"
    assert (info["repairs"], info["degraded"]) == (1, None)
    assert "不是本次命中的意象" in info["problems"][0][0]
    assert text not in outcome.text


# ---- P2 r5: 找不到出口 is 迷路 in other words (找不到路 is already its alias) ----------------

MALL_HITS = [
    {"phrase": "商场", "symbol": "商场"},
    {"phrase": "迷路", "symbol": "迷路"},
    {"phrase": "手机", "symbol": "手机"},
]


@pytest.mark.parametrize(
    "text",
    [
        # r5 dream_lost_in_mall#1, both refused sentences.
        "你在商场里找不到出口，可能提示最近面对的选择不少，或者身处一个新环境。",
        "梦里你在商场里四处走却找不到出口，可能说明你正处在需要辨认路线的阶段。",
        # r5 dream_lost_in_mall#3.
        "梦里找不到出口的着急是真实的，但它更多反映的是当下情绪，而不是现实走向。",
        "梦里的商场出口难找，可能对应你最近面对不少选项。",
    ],
)
async def test_the_r5_lost_constructions_are_the_matched_symbol(make, text):
    runtime, *_ = make(extraction(MALL_HITS), written)
    runtime.session.state["selected_systems"] = ["dream"]
    await runtime.turn(MALL)
    assert Dream(runtime).problems([text], runtime.session) == [], text


@pytest.mark.parametrize(
    "symbols, text",
    [
        # Without 迷路 matched, the same construction is still content outside the fact sheet.
        (MALL_HITS[:1] + MALL_HITS[2:], "到处找不到出口，往往反映你对方向的困惑。"),
        # The construction does not cover the rest of the scene.
        (MALL_HITS, "巨大的商场往往代表选择太多。"),
    ],
)
async def test_what_the_lost_construction_does_not_cover_is_still_refused(make, symbols, text):
    runtime, *_ = make(extraction(symbols), written)
    runtime.session.state["selected_systems"] = ["dream"]
    await runtime.turn(MALL)
    assert Dream(runtime).problems([text], runtime.session), text


async def test_a_lost_construction_passes_the_final_submission(make):
    text = "你在商场里找不到出口，可能提示最近面对的选择不少。"
    runtime, _, events = make(extraction(MALL_HITS), with_layer(text), written)
    outcome = await runtime.turn(MALL)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None)
    assert text in outcome.text
