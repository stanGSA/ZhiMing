"""P3.1 requirements for astro: the range a question asks about and its consultation timezone."""

from types import SimpleNamespace

import pytest

from common.time_utils import NeedsInput
from pipeline.requirements import asked_range, birth_ready, period_choice

ANCHOR = "2026-10-30"  # a Friday


@pytest.mark.parametrize(
    "text, expected",
    [
        ("下个月事业运怎么样", ("2026-11-01", "2026-11-30")),
        ("2027年3月的人际关系", ("2027-03-01", "2027-03-31")),
        ("2026年12月1日到12月15日适合谈合作吗", ("2026-12-01", "2026-12-15")),
        ("2026年12月1日到15日", ("2026-12-01", "2026-12-15")),
        ("12月1日至12月20日", ("2026-12-01", "2026-12-20")),
        ("今年感情怎么样", ("2026-01-01", "2026-12-31")),
        ("明年上半年", ("2027-01-01", "2027-06-30")),
        ("明年下半年", ("2027-07-01", "2027-12-31")),
        ("这周", ("2026-10-26", "2026-11-01")),
        ("下周适合谈合作吗", ("2026-11-02", "2026-11-08")),
        ("下周三面试", ("2026-11-04", "2026-11-04")),
        ("下周三到周五适合谈合作吗", ("2026-11-04", "2026-11-06")),
        ("明年3月事业运怎么样", ("2027-03-01", "2027-03-31")),
        ("明年十二月事业运怎么样", ("2027-12-01", "2027-12-31")),
        ("2027年3月事业运怎么样", ("2027-03-01", "2027-03-31")),
        ("看看2027年3月5日", ("2027-03-05", "2027-03-05")),
        ("明天运势", ("2026-10-31", "2026-10-31")),
        ("接下来三个月", ("2026-10-30", "2027-01-29")),
        ("未来两周", ("2026-10-30", "2026-11-12")),
        ("11月适合跳槽吗", ("2026-11-01", "2026-11-30")),
        # An earlier month than the current one is next year's.
        ("3月运势", ("2027-03-01", "2027-03-31")),
        ("十二月运势", ("2026-12-01", "2026-12-31")),
    ],
)
def test_ranges_read_by_code(text, expected):
    assert asked_range(text, ANCHOR) == expected


@pytest.mark.parametrize(
    "text",
    [
        "最近运势怎么样",
        "这段时间适合换工作吗",
        "接下来要注意什么",
        "我的性格有什么特点",
        # A reversed range is not a range.
        "12月20日到12月1日",
        "今天和明天哪天更好",
    ],
)
def test_no_range_is_guessed(text):
    assert asked_range(text, ANCHOR) is None


def session(birth_tz, *messages, consultation_tz=None, locations=None):
    profile = {"tz": birth_tz}
    if consultation_tz:
        profile["consultation_tz"] = consultation_tz
    return SimpleNamespace(
        profile=profile,
        user_messages=list(messages),
        state={"question_message_index": 0, "locations": locations or {}},
    )


CHART = {"input": {"tz": "America/Los_Angeles"}}


def choose(birth_tz, *messages, **kwargs):
    chart = {"input": {"tz": birth_tz}}
    return period_choice(session(birth_tz, *messages, **kwargs), chart, "2026-11-01", "2026-11-30")


def test_overseas_birth_without_residence_defaults_to_the_birth_timezone():
    period = choose("America/Los_Angeles", "看星盘，下个月事业运怎么样？")
    assert (period.tz, period.defaulted) == ("America/Los_Angeles", True)
    assert "America/Los_Angeles" in period.note("洛杉矶") and "出生地洛杉矶" in period.note(
        "洛杉矶"
    )


def test_the_web_birth_note_is_not_a_residence():
    message = "下个月事业运怎么样？\n\n我在出生信息表中填写的资料：1996-05-10 08:30，出生地点：洛杉矶（America/Los_Angeles）。"
    assert choose("America/Los_Angeles", message).defaulted


def test_beijing_birth_uses_beijing_time_without_a_note():
    period = choose("Asia/Shanghai", "下个月事业运怎么样？")
    assert (period.tz, period.defaulted, period.note("上海")) == ("Asia/Shanghai", False, "")


def test_a_stated_timezone_wins():
    period = choose("America/Los_Angeles", "按北京时间看下个月")
    assert (period.tz, period.defaulted) == ("Asia/Shanghai", False)
    period = choose("America/Los_Angeles", "按出生地当地时间看下个月")
    assert (period.tz, period.defaulted) == ("America/Los_Angeles", False)


def test_a_saved_consultation_timezone_wins():
    period = choose("America/Los_Angeles", "下个月", consultation_tz="Europe/Paris")
    assert (period.tz, period.defaulted) == ("Europe/Paris", False)


@pytest.mark.parametrize(
    "message",
    [
        "我现在住在多伦多，下个月事业运怎么样？",
        # Other ways of saying where one lives.
        "我人一直在国外，下个月怎么样？",
        "我常年在海外工作，下个月呢",
        "我定居温哥华，下个月呢",
        "去年搬到了悉尼，下个月呢",
        # A negated residence still says the birth place is not where one is.
        "我不在国外，下个月怎么样？",
        "我已经不住洛杉矶了，下个月呢",
        "我现在不是住在洛杉矶，下个月呢",
        # A double negation and a turn still state a residence.
        "我不是不在国外，只是想看下个月",
        "我出生在洛杉矶，但现在人在上海工作，下个月呢",
        "我在国内，下个月呢",
        "我已经回国了，下个月呢",
        # An unresolved clock or timezone named in words.
        "按多伦多时间看下个月",
        "用UTC看下个月",
    ],
)
def test_a_stated_residence_is_asked_not_defaulted(message):
    with pytest.raises(NeedsInput) as raised:
        choose("America/Los_Angeles", message)
    assert raised.value.code == "confirm_period_timezone"


@pytest.mark.parametrize("birth_tz", ["Asia/Urumqi", "Etc/GMT-8"])
def test_domestic_clocks_other_than_beijing_are_still_asked(birth_tz):
    with pytest.raises(NeedsInput):
        choose(birth_tz, "下个月事业运怎么样？")


def test_a_later_answer_counts_as_stated():
    """The answer to the question is read from the messages after the question."""
    period = choose("America/Los_Angeles", "我现在住在多伦多，下个月呢", "按北京时间")
    assert (period.tz, period.defaulted) == ("Asia/Shanghai", False)


def test_birth_ready_needs_date_clock_and_place():
    ready = SimpleNamespace(
        profile={"birth_local_dt": "1996-05-10 08:30", "tz": "Asia/Shanghai", "lat": 31.2},
        birth_binding=None,
    )
    assert birth_ready(ready)
    for missing in ("birth_local_dt", "tz", "lat"):
        profile = {k: v for k, v in ready.profile.items() if k != missing}
        assert not birth_ready(SimpleNamespace(profile=profile, birth_binding=None))


@pytest.mark.parametrize(
    "text, timing",
    [
        ("看星盘，我的事业运怎么样", True),
        ("最近适合换工作吗", True),
        ("现在适合跳槽吗", True),
        ("下个月感情如何", True),
        ("我适合做设计吗", False),
        ("我会不会是个敏感的人", False),
        ("我的性格有什么特点", False),
        ("从本命星盘看我适合什么工作方式", False),
    ],
)
def test_timing_questions(text, timing):
    from pipeline.requirements import is_timing

    assert is_timing(text) is timing


@pytest.mark.parametrize(
    "message",
    [
        "不用真太阳时，按固定UTC+8。",
        "用真太阳时。",
        "关闭真太阳时",
    ],
)
def test_a_solar_time_choice_is_not_a_residence(message):
    """Bazi PR: the bazi clock convention says nothing about where the user lives."""
    period = choose("America/Los_Angeles", "下个月工作上要注意什么？", message)
    assert (period.tz, period.defaulted) == ("America/Los_Angeles", True)


@pytest.mark.parametrize(
    "message",
    [
        # Still asked: a residence or a timezone beside the solar-time choice.
        "不用真太阳时，我现在住在多伦多",
        "按固定UTC+8，用UTC看下个月",
        "用真太阳时，按多伦多时间看下个月",
        "按UTC+8时间看下个月",
    ],
)
def test_a_residence_beside_a_solar_time_choice_is_still_asked(message):
    with pytest.raises(NeedsInput):
        choose("America/Los_Angeles", "下个月工作上要注意什么？", message)
