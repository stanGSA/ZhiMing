"""The tarot page in pipeline mode: same API, same saved reading, code-driven underneath."""

import httpx
import pytest

pytest.importorskip("fastapi")

from app import create_runtime
from tests.pipeline.drafts import followup_answer, good
from web import create_web_app

HEADERS = {"X-Zhiming-Client": "web", "Origin": "http://testserver"}


class Writer:
    """Writes a reading, or a follow-up answer when the request is a follow-up."""

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, tools):
        from harness.models import ModelResponse

        self.calls += 1
        draft = followup_answer if "原解读摘要" in messages[1]["content"] else good
        return ModelResponse(text=draft(messages), input_tokens=100, output_tokens=50)


@pytest.fixture
async def page(project):
    runtimes = []

    def factory(**kwargs):
        kwargs.pop("provider", None)
        runtime = create_runtime(**kwargs, seed=42, model=Writer(), mode="pipeline")
        runtimes.append(runtime)
        return runtime

    app = create_web_app(root=project, runtime_factory=factory)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=HEADERS
        ) as client:
            yield client, runtimes


async def test_tarot_page_reading_and_follow_up(page):
    client, runtimes = page
    await client.get("/api/session?system=tarot")
    ask = {"system": "tarot", "spread": "three_card", "picks": [3, 30, 60]}
    data = (await client.post("/api/chat", json={"message": "看看近期事业", **ask})).json()
    assert data["messages"][-1]["status"] == "submit_reading"
    reading = data["reading"]
    assert len(reading["tarot"]["cards"]) == 3 and reading["output"]["sections"]
    assert reading["question"] == "看看近期事业"  # the page's spread note is not the question
    tarot = next(r for r in runtimes if r.session.state.get("tarot_result"))
    assert tarot.session.state["picks"] == [3, 30, 60]
    assert tarot.model.calls == 1
    follow = {"system": "tarot", "spread": "three_card"}
    again = await client.post("/api/chat", json={"message": "第二张牌具体什么意思？", **follow})
    data = again.json()
    assert data["messages"][-1]["status"] == "submit_reading"
    assert data["reading"]["reading_id"] == reading["reading_id"]
    assert data["reading"]["tarot"]["cards"] == reading["tarot"]["cards"]
    assert tarot.model.calls == 2
