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
    assert [e["rules"] for e in events if e.get("stage") == "safety"] == [["certainty"]] * 2
    assert outcome.data["reading"]["sections"] == []
