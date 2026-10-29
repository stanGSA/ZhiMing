"""Exercise the screenshot's preset through the browser and real web/runtime pipeline."""

import pytest

from harness.models import ModelResponse, ToolCall
from tests.runtime.test_dayun_recovery import QUESTION, draft
from tests.web.test_web_api import browser as browser
from tests.web.test_web_api import signed_browser as signed_browser
from tests.web.test_web_browser import chromium as chromium
from tests.web.test_web_browser import expect, open_saved_birth
from tests.web.test_web_browser import site as site


class DayunModel:
    def __init__(self, runtime):
        self.runtime = runtime
        self.calls = 0

    async def chat(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            name, args = "start_reading", {"question": QUESTION, "systems": ["bazi"]}
        elif self.calls == 2:
            name, args = "compute_bazi", {"gender": "male"}
        else:
            assert "lookup_meaning" not in [t["function"]["name"] for t in tools]
            name, args = "submit_reading", draft(self.runtime)
        return ModelResponse(
            tool_calls=[ToolCall(id=f"dayun-{self.calls}", name=name, arguments=args)],
            input_tokens=100,
            output_tokens=100,
        )


async def test_preset_api_saves_reading_and_history(signed_browser):
    client, _, runtimes = signed_browser
    await client.get("/api/session?system=bazi")
    runtime = runtimes[-1]
    model = DayunModel(runtime)
    runtime.model = model
    response = await client.post(
        "/api/chat",
        json={
            "message": QUESTION,
            "system": "bazi",
            "birth": {
                "date": "2001-10-25",
                "time": "03:00",
                "gender": "male",
                "location_id": "1803361",
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["messages"][-1]["status"] == "submit_reading"
    assert not data["messages"][-1]["failure"]
    assert model.calls == 3
    assert data["reading"]["calculations"]["bazi_result"]["dayun"]["start_solar"] == "2007-05-05"
    history = await client.get("/api/readings/" + data["reading"]["reading_id"])
    assert history.status_code == 200


@pytest.mark.parametrize("width", [390, 1280])
def test_current_dayun_button_displays_completed_report(site, chromium, width):
    base, runtimes = site
    page = open_saved_birth(chromium, base, "bazi", width)
    registered = page.request.post(
        f"{base}/api/account/register",
        data={
            "username": "大运测试",
            "password": "test-pass123",
            "accept_privacy": True,
            "keep_guest_records": True,
        },
        headers={"Origin": base, "X-Zhiming-Client": "web"},
    )
    assert registered.status == 201
    page.goto(f"{base}/bazi?provider=demo")
    expect(page.locator("#provider")).to_have_value("demo")
    with page.expect_response(lambda r: r.url.endswith("/api/new")) as changed:
        page.select_option("#provider", "configured")
    assert changed.value.status == 200
    expect(page.locator("#birth-date")).to_be_enabled()
    page.locator("[data-birth-fold] > summary").click()
    page.fill("#birth-date", "2001-10-25")
    page.fill("#birth-time", "03:00")
    page.select_option("#birth-gender", "male")
    with page.expect_response(lambda r: r.url.endswith("/api/chart")) as chart:
        page.locator("#birth-form button[type=submit]").click()
    assert chart.value.status == 200
    runtime = runtimes[-1]
    runtime.model = DayunModel(runtime)
    page.get_by_role("button", name="当前大运", exact=True).click()
    with page.expect_response(lambda r: r.url.endswith("/api/chat")) as response:
        page.click("#send")
    data = response.value.json()
    assert data["messages"][-1]["status"] == "submit_reading"
    expect(page.locator("#thinking")).to_have_count(0)
    expect(page.locator(".msg-assistant").last).to_contain_text("2007-05-05")
    expect(page.locator(".msg-assistant").last).not_to_contain_text("执行步数上限")
    assert runtime.model.calls == 3
    page.close()
