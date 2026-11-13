"""scripts.service_probe: the r14/r15 service anomalies fail the probe, a normal service passes."""

import json

import pytest

from harness.models import ModelResponse, ToolCall
from scripts import service_probe


def reply(text="OK", output_tokens=1, **extra):
    return ModelResponse(text=text, output_tokens=output_tokens, model="m", **extra)


def call(arguments=None, text="", output_tokens=12, **extra):
    return ModelResponse(
        text=text,
        output_tokens=output_tokens,
        model="m",
        tool_calls=[ToolCall(id="c1", name="get_profile", arguments=arguments or {})],
        **extra,
    )


def test_a_service_without_thinking_passes():
    assert service_probe.problems_of("reply", reply()) == []
    assert service_probe.problems_of("reply", reply("OK。", 2)) == []
    assert service_probe.problems_of("tool", call()) == []


@pytest.mark.parametrize(
    "response",
    [
        reply(output_tokens=16),  # r15 preflight attempt 4: “OK” in 16 tokens
        reply(output_tokens=31),  # attempt 5
        reply(reasoning_tokens=200),
        reply(reasoning_content="The user asks…"),
        reply("The user asks about bazi 大运…", 300),  # r14 single: reasoning as the answer
        reply(usage_available=False),
    ],
)
def test_reply_anomalies_fail(response):
    assert service_probe.problems_of("reply", response)


@pytest.mark.parametrize(
    "response",
    [
        call({"_placeholder": ""}),  # r14 single: an argument on a tool without parameters
        call(text="用户要我调用 get_profile……"),
        call(output_tokens=900),
        reply("The user wants me to call get_profile.", 40),  # text instead of a call
    ],
)
def test_tool_call_anomalies_fail(response):
    assert service_probe.problems_of("tool", response)


class Fake:
    model = "deepseek-v4.1-flash"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.closed = False

    async def chat(self, messages, tools):
        return self.responses.pop(0)

    async def close(self):
        self.closed = True


async def test_the_report_and_exit_code(monkeypatch, tmp_path):
    runtime, judge = Fake(reply(), call()), Fake(reply(output_tokens=5304))
    monkeypatch.setattr(service_probe, "build_model", lambda *a, **k: runtime)
    monkeypatch.setattr(service_probe, "role_model", lambda *a, **k: judge)
    output = tmp_path / "probe.json"
    assert await service_probe.main("pro", output) == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert [p["ok"] for p in report["probes"]] == [True, True, False]
    assert report["probes"][2]["probe"] == "judge_pro_reply"
    assert "output_tokens=5304 > 3" in report["probes"][2]["problems"]
    assert runtime.closed and judge.closed
    assert "base_url" not in output.read_text(encoding="utf-8")


async def test_an_error_is_recorded_without_the_endpoint(monkeypatch, tmp_path):
    class Limited(Exception):
        status_code = 429

    class Failing(Fake):
        async def chat(self, messages, tools):
            raise Limited("https://relay.example/v1 rate limited")

    monkeypatch.setattr(service_probe, "build_model", lambda *a, **k: Failing())
    output = tmp_path / "probe.json"
    assert await service_probe.main(None, output) == 1
    text = output.read_text(encoding="utf-8")
    assert "relay.example" not in text and '"status_code": 429' in text
