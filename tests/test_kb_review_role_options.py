"""Review-only reasoning options must be transmitted and bound to the reviewed evidence."""

import copy
import json

import httpx
import pytest

from harness.llm import RoleModelSpec, role_model
from scripts import kb_review_live as live
from scripts import model_review_kb as review
from tests.test_kb_review_r2 import SYSTEM, Models, setting  # noqa: F401


async def test_review_role_transmits_reasoning_options_and_keeps_total_usage(monkeypatch):
    monkeypatch.setenv("REVIEW_TEST_KEY", "offline-placeholder")
    received = []

    def respond(request):
        received.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-v4-pro",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "{}",
                            "reasoning_content": "test reasoning",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 50,
                    "total_tokens": 70,
                    "completion_tokens_details": {"reasoning_tokens": 40},
                },
            },
        )

    spec = RoleModelSpec(
        vendor="deepseek",
        api="openai",
        model="deepseek-v4-pro",
        api_key_env="REVIEW_TEST_KEY",
        base_url="https://review.example",
        thinking="enabled",
        reasoning_effort="high",
        max_tokens=16384,
    )
    model = role_model(spec, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    try:
        response = await model.chat([{"role": "user", "content": "review"}], [])
    finally:
        await model.close()
    assert received[0]["thinking"] == {"type": "enabled"}
    assert received[0]["reasoning_effort"] == "high"
    assert received[0]["max_tokens"] == 16384
    assert response.output_tokens == 50 and response.reasoning_tokens == 40


@pytest.mark.parametrize(
    "options",
    [
        {"thinking": "enabled", "vendor": "openai"},
        {"reasoning_effort": "high"},
        {"thinking": "disabled", "reasoning_effort": "high"},
    ],
)
def test_review_reasoning_cannot_be_silently_ignored(options):
    data = dict(vendor="deepseek", api="openai", model="test", api_key_env="TEST_KEY")
    with pytest.raises(ValueError):
        RoleModelSpec(**(data | options))


async def test_pilot_and_registration_are_bound_to_actual_role_settings(setting, tmp_path):  # noqa: F811
    work, config, roles, _, prereg = setting
    calibration = review.ROOT / prereg["calibration"]["path"]
    root = tmp_path / "bound-pilot"
    models = Models(work)
    result = await live.run_pilot(
        root,
        1,
        calibration,
        workspace=work,
        config=config,
        roles=roles,
        make_model=models.make,
        systems=(SYSTEM,),
    )
    assert result["met"]
    changed = copy.deepcopy(roles)
    changed["reviewer_a"] = roles["reviewer_a"].model_copy(update={"temperature": 0.0})
    before = len(models.calls)
    with pytest.raises(ValueError, match="角色|审核方"):
        await live.run_pilot(
            root,
            1,
            calibration,
            workspace=work,
            config=config,
            roles=changed,
            make_model=models.make,
            systems=(SYSTEM,),
        )
    assert len(models.calls) == before
    with pytest.raises(ValueError, match="最近一次试跑"):
        live.preregister(root, calibration, config, changed, systems=(SYSTEM,), workspace=work)
    plan = review.load_plan(root / "pilot-1" / SYSTEM)
    with pytest.raises(ValueError, match="角色|审核方"):
        await review.execute(
            review.RunDir(root / "pilot-1" / SYSTEM), plan, changed, make_model=models.make
        )
    assert len(models.calls) == before
