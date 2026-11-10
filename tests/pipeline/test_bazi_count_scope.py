"""PR65 review: count lists keep their scope and the negation of that scope."""

import pytest

from pipeline.bazi import Bazi
from tests.pipeline.test_runner_bazi import NEXT_MONTH, make, written  # noqa: F401


@pytest.mark.parametrize(
    "text",
    [
        "这个月木2，火4，土2，金0，水0。",
        "这个月木2,火4,土2,金0,水0。",
        "这个月木2、火4，土2、金0，水0。",
        "这个月五行：木2，火4，土2，金0，水0。",
        "这个月木2个、火4个、土2个。",
        "结合原局看这个月五行是木2、火4、土2、金0、水0。",
        "原局如此这个月木2、火4、土2。",
        "原局木2、火4、土2但这个月木2，火4，土2。",
        "这个月并非不是木2，火4，土2。",
        "不能说这个月不是木2，火4，土2。",
        "不能说这不是这个月木2，火4，土2的分布。",
        "这个月不完全是木2，火4，土2。",
        "这个月不是木2，火4，土2，但其实木2，火4，土2。",
        "这不是这个月的分布但下个月木2，火4，土2。",
    ],
)
def test_period_counts_are_refused_across_list_separators_and_natal_mentions(text):
    assert Bazi.count_problems(text), text


@pytest.mark.parametrize(
    "text",
    [
        "这段时间的五行不是木2、火4、土2、金0、水0，那只是原局计数。",
        "这段时间的五行不是木2，火4，土2，金0，水0，那只是原局计数。",
        "这不是这个月木2、火4、土2的分布。",
        "这不是这个月木2，火4，土2的分布。",
        "原局五行计数木2，火4，土2，金0，水0。",
        "原局木2个、火4个、土2个。",
        "这段时间看原局木2，火4，土2。",
        "这段时间看原局，木2，火4，土2。",
        "这个月参考原局，木2，火4，土2是出生八字的计数。",
        "这个月，木2，火4，土2是出生八字的计数。",
        "原局木2，火4，土2，这个月流月火旺。",
        "这个月流月火旺；原局木2，火4，土2。",
        "流月丙午（6月6日至7月7日）火旺。",
    ],
)
def test_denied_period_counts_and_explicit_natal_counts_pass(text):
    assert Bazi.count_problems(text) == [], text


@pytest.mark.parametrize(
    "extra,repairs",
    [
        ("这个月木2，火4，土2，金0，水0。", 1),
        ("结合原局看这个月五行是木2、火4、土2、金0、水0。", 1),
        ("这段时间的五行不是木2、火4、土2、金0、水0，那只是原局计数。", 0),
        ("这不是这个月木2，火4，土2的分布。", 0),
        ("原局五行计数木2，火4，土2，金0，水0。", 0),
    ],
)
async def test_count_scope_repairs_only_period_assertions(make, extra, repairs):  # noqa: F811
    runtime, composer, _ = make(lambda m: written(m, extra=extra), written)
    outcome = await runtime.turn(NEXT_MONTH)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1 + repairs, repairs, None)
    if repairs:
        assert f"出问题的句子：“{extra}”" in composer.seen[1][0][-1]["content"]
    else:
        assert any(extra in section["body"] for section in outcome.data["reading"]["sections"])
