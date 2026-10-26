"""The MCP server, called through the SDK's in-memory client (and once over stdio)."""

import sys

import pytest
import yaml

pytest.importorskip("mcp", reason="需要 uv sync --extra mcp")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import get_default_environment, stdio_client  # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

from app import ROOT  # noqa: E402
from knowledge.review import LEVELS  # noqa: E402
from mcp_server.server import build_server  # noqa: E402
from plugins.astro.calculator import angular_delta  # noqa: E402
from plugins.tarot.draw import draw_tarot  # noqa: E402

TOOLS = {
    "resolve_location",
    "compute_natal_chart",
    "compute_transits",
    "compute_bazi",
    "compute_bazi_period",
    "draw_tarot",
    "analyze_name",
    "lookup_dream_symbols",
    "daily_fortune",
    "lookup_meaning",
}
CHENGDU = {"birth_local": "1996-05-10 08:30", "tz": "Asia/Shanghai", "lat": 30.66, "lon": 104.07}


def case(dataset, identity):
    cases = yaml.safe_load((ROOT / f"evals/cases/{dataset}.yaml").read_text(encoding="utf-8"))
    return next(c for c in cases["cases"] if c["id"] == identity)


@pytest.fixture(scope="module")
def server():
    return build_server()


async def call(server, name, arguments):
    async with create_connected_server_and_client_session(server) as client:
        result = await client.call_tool(name, arguments)
    return result.isError, result.structuredContent


def assert_interpreted(data):
    assert data["status"] == "ok" and data["kb_version"]
    assert data["interpretations"]
    for item in data["interpretations"]:
        assert item["ref_id"] and item["meaning"]["text"]
        assert item["meaning"]["review_status"] in LEVELS
    levels = [i["meaning"]["review_status"] for i in data["interpretations"]]
    assert data["review"]["lowest"] == min(levels, key=LEVELS.index)


async def test_lists_every_tool_read_only(server):
    async with create_connected_server_and_client_session(server) as client:
        tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == TOOLS
    assert all(tool.annotations.readOnlyHint for tool in tools)
    schema = next(t for t in tools if t.name == "compute_natal_chart").inputSchema
    assert schema["required"] == ["birth"]


async def test_bazi_matches_boundary_dataset(server):
    reference = case("bazi_boundary", "bazi-01")
    given = reference["input"]
    birth = dict(birth_local=given["birth_local_clock"], tz=given["tz"], lon=given["lon"])
    arguments = dict(birth=birth, gender=given["gender"], true_solar_time=False)
    error, data = await call(server, "compute_bazi", arguments)
    assert not error
    for key, value in reference["expected"].items():
        assert data[key] == value, key
    assert_interpreted(data)
    assert data["bazi_id"].startswith("bz")
    # Same inputs, same result, identifiers included.
    assert (await call(server, "compute_bazi", arguments))[1] == data


async def test_natal_chart_matches_reference_chart(server):
    reference = case("reference_charts", "chart-02")
    given = reference["input"]
    birth = {k: given[k] for k in ("birth_local", "tz", "lat", "lon", "time_known")}
    error, chart = await call(server, "compute_natal_chart", {"birth": birth})
    assert not error
    expected = reference["expected"]
    for actual, ref in zip(chart["planets"], expected["planets"], strict=True):
        assert actual["body"] == ref["body"]
        assert abs(angular_delta(actual["lon"], ref["lon"])) < 0.01
        assert (actual["sign"], actual["house"]) == (ref["sign"], ref.get("house"))
        assert actual["retrograde"] == ref["retrograde"]
    assert chart["house_system"] == expected["house_system"]
    for house, value in expected["cusps"].items():
        # JSON object keys are strings.
        assert abs(angular_delta(chart["cusps"][str(house)], value)) < 0.01
    assert {(a["a"], a["b"], a["type"]) for a in chart["aspects"]} == {
        (a["a"], a["b"], a["type"]) for a in expected["aspects"]
    }
    assert_interpreted(chart)
    sun = next(i for i in chart["interpretations"] if i["kind"] == "planet_sign")
    assert sun["ref_id"] == f"astro:{chart['chart_id']}:{sun['fact']}"
    assert (await call(server, "compute_natal_chart", {"birth": birth}))[1] == chart


async def test_tarot_fixed_seed_is_reproducible(server):
    vector = yaml.safe_load((ROOT / "plugins/tarot/evals/cases.yaml").read_text(encoding="utf-8"))
    reference = vector["cases"][0]
    arguments = dict(
        spread=reference["spread"], question=reference["question"], seed=reference["seed"]
    )
    error, draw = await call(server, "draw_tarot", arguments)
    assert not error
    assert [{k: c[k] for k in ("card_id", "reversed")} for c in draw["cards"]] == reference[
        "expected"
    ]
    assert draw["cards"] == [
        {**pure, **{k: c[k] for k in ("meaning_key", "ref_id", "meaning")}}
        for pure, c in zip(
            draw_tarot(reference["spread"], reference["question"], reference["seed"])["cards"],
            draw["cards"],
            strict=True,
        )
    ]
    assert all(c["meaning"]["review_status"] in LEVELS for c in draw["cards"])
    assert (await call(server, "draw_tarot", arguments))[1] == draw

    # Without a seed the draw is random, and the seed it returns replays it exactly.
    error, fresh = await call(server, "draw_tarot", {"question": "合成问题"})
    assert not error and 0 <= fresh["seed"] < 2**53
    replay = await call(server, "draw_tarot", {"question": "合成问题", "seed": fresh["seed"]})
    assert replay[1]["cards"] == fresh["cards"]


@pytest.mark.parametrize(
    "name,arguments,code,field",
    [
        (
            "compute_natal_chart",
            {"birth": {**CHENGDU, "lat": 200}},
            "invalid_arguments",
            "birth.lat",
        ),
        ("draw_tarot", {"question": "q", "seed": -1}, "invalid_arguments", "seed"),
        ("draw_tarot", {"question": "q", "spread": "celtic"}, "invalid_arguments", "spread"),
        ("compute_bazi", {"birth": {"birth_local": "1990-02-04 09:59"}}, "invalid_arguments", None),
        (
            "compute_natal_chart",
            {"birth": {"birth_local": "1990-02-04 09:59", "location_id": "missing"}},
            "unknown_location",
            None,
        ),
        ("analyze_name", {"surname": "王", "given": "ab"}, "invalid_arguments", None),
        (
            "lookup_meaning",
            {"system": "tarot", "kind": "card", "key": "nope"},
            "missing_entry",
            None,
        ),
    ],
)
async def test_bad_arguments_return_structured_errors(server, name, arguments, code, field):
    error, data = await call(server, name, arguments)
    assert error
    assert data["ok"] is False and data["code"] == code and data["error"]
    if field:
        assert field in [detail["field"] for detail in data["details"]]


async def test_decisions_for_the_person_come_back_as_needs_input(server):
    _, place = await call(server, "resolve_location", {"query": "乌鲁木齐"})
    assert place["status"] == "resolved"
    birth = {"birth_local": "1990-02-04 09:59", "location_id": place["location"]["location_id"]}
    # A Xinjiang clock may be Beijing or Xinjiang time: the web page's chart panel asks too.
    error, data = await call(server, "compute_natal_chart", {"birth": birth})
    assert not error and data["status"] == "needs_input"
    assert data["code"] == "confirm_clock_timezone"
    error, data = await call(
        server, "compute_natal_chart", {"birth": {**birth, "clock_tz": "Asia/Shanghai"}}
    )
    assert not error and data["status"] == "ok"
    overseas = {"birth_local": "1990-02-04 09:59", "tz": "America/New_York", "lon": -74.0}
    error, data = await call(server, "compute_bazi", {"birth": overseas})
    assert not error and data["code"] == "confirm_bazi_clock"


async def test_remaining_tools(server):
    _, place = await call(server, "resolve_location", {"query": "北京"})
    beijing = {"birth_local": "1993-08-17 23:20", "location_id": place["location"]["location_id"]}

    error, moves = await call(
        server,
        "compute_transits",
        {"birth": beijing, "start": "2026-11-01", "end": "2026-11-30", "tz": "Asia/Shanghai"},
    )
    assert not error and moves["events"]
    assert_interpreted(moves)

    error, period = await call(
        server,
        "compute_bazi_period",
        {"birth": beijing, "start": "2026-11-01", "end": "2026-11-30", "tz": "Asia/Shanghai"},
    )
    assert not error and period["periods"]
    assert_interpreted(period)

    error, name = await call(server, "analyze_name", {"surname": "王", "given": "思远"})
    assert not error
    assert name["grids"] == {"天格": 5, "人格": 13, "地格": 26, "外格": 18, "总格": 30}
    assert_interpreted(name)

    error, dream = await call(server, "lookup_dream_symbols", {"symbols": ["掉牙", "无人机"]})
    assert not error
    assert [h["key"] for h in dream["hits"]] == ["掉牙"] and dream["misses"] == ["无人机"]
    assert_interpreted(dream)

    arguments = {"birth": CHENGDU, "date": "2026-10-26", "tz": "Asia/Shanghai"}
    error, daily = await call(server, "daily_fortune", arguments)
    assert not error and daily["date"] == "2026-10-26" and daily["card"]["name"]
    assert_interpreted(daily)
    assert (await call(server, "daily_fortune", arguments))[1] == daily

    error, meaning = await call(
        server,
        "lookup_meaning",
        {"system": "tarot", "kind": "card", "key": daily["card"]["meaning_key"]},
    )
    assert not error and meaning["entry"]["review_status"] in LEVELS
    assert meaning["review"]["lowest"] == meaning["entry"]["review_status"]


async def test_stdio_entry_point():
    # The client passes only a minimal environment; add what docs/usage.md configures.
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server"],
        cwd=str(ROOT),
        env={**get_default_environment(), "PYTHONUTF8": "1"},
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            tools = (await client.list_tools()).tools
            result = await client.call_tool("draw_tarot", {"question": "合成问题", "seed": 42})
    assert {tool.name for tool in tools} == TOOLS
    assert [c["card_id"] for c in result.structuredContent["cards"]] == [
        "the_moon",
        "justice",
        "the_tower",
    ]
