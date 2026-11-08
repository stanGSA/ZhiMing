"""PR 60 follow-ups: preserve user ranges, saved birth data and form provenance."""

# ruff: noqa: F811

import pytest

from pipeline import birth, requirements
from pipeline.bazi import ASK_FORM_GENDER, Bazi
from tests.pipeline.drafts import Composer
from tests.pipeline.test_runner_astro import written as astro_written
from tests.pipeline.test_runner_bazi import DAYUN, make, written  # noqa: F401
from tests.pipeline.test_runner_daily import written as daily_written
from tests.web.test_web_api import browser  # noqa: F401


@pytest.mark.parametrize(
    "question, draft, result_key",
    [
        ("看看我的八字性格", written, "bazi_result"),
        ("今天运势怎么样？", daily_written, "daily_result"),
        ("看看我的星盘性格", astro_written, "natal_result"),
    ],
)
async def test_saved_date_only_asks_for_place_and_resumes(make, question, draft, result_key):
    runtime, composer, _ = make(draft, birth={"birth_local_dt": "1996-05-10 08:30"})
    first = await runtime.turn(question)
    assert first.status == "ask_user", first.text
    assert first.text == birth.ASK_PLACE
    assert composer.seen == []
    second = await runtime.turn("杭州")
    assert second.status == "submit_reading", second.text
    assert result_key in runtime.session.state
    assert runtime.session.profile["birth_local_dt"] == "1996-05-10 08:30"


async def test_initial_luck_age_is_distinct_from_later_handover_ages(make):
    runtime, _, _ = make(written)
    await runtime.turn(DAYUN)
    stages = runtime.session.state["bazi_result"]["dayun"]["sequence"]
    system = Bazi(runtime)
    first, later = stages[0]["start_age"], stages[2]["start_age"]
    assert not system.problems([f"你在{first}岁起运。"], runtime.session)
    assert not system.problems([f"你在{later}岁交运。"], runtime.session)
    assert system.problems([f"你在{later}岁起运。"], runtime.session)
    assert system.problems([f"你在{later}岁上运。"], runtime.session)


async def test_wrong_initial_luck_age_is_repaired_before_submission(make):
    runtime, _, _ = make(lambda m: written(m, extra="你在22岁起运。"), written)
    result = await runtime.turn(DAYUN)
    assert result.status == "submit_reading", result.text
    assert result.data["pipeline"]["repairs"] == 1
    assert "22岁起运" not in result.text


@pytest.mark.parametrize("system", ["八字", "星盘"])
def test_birth_removal_keeps_the_preceding_explicit_range(system):
    text = f"用{system}看看2026年12月1日到2026年12月5日运势，我1990年3月5日出生在杭州"
    cleaned = birth.without_birth(text)
    assert "1990" not in cleaned
    assert requirements.asked_range(cleaned, "2026-11-08") == (
        "2026-12-01",
        "2026-12-05",
    )


async def test_explicit_range_then_typed_birth_reaches_submission(make):
    runtime, _, _ = make(written, birth=None)
    result = await runtime.turn(
        "用八字看看2026年12月1日到2026年12月5日运势，我1990年3月5日早上8点出生在杭州"
    )
    assert result.status == "submit_reading", result.text
    period = runtime.session.state["bazi_period_result"]
    assert (period["start"], period["end"]) == ("2026-12-01", "2026-12-05")


async def test_web_gender_is_completed_through_the_versioned_form(browser):
    client, _, runtimes = browser
    await client.get("/api/session?system=bazi")
    for runtime in runtimes:
        runtime.pipeline_systems = ("bazi",)
        runtime.model = Composer(written)
    form = {
        "date": "1996-05-10",
        "time": "08:30",
        "location_id": "1803361",
        "gender": "",
    }

    async def send(message, birth_form, version):
        response = await client.post(
            "/api/chat",
            json={
                "system": "bazi",
                "message": message,
                "birth": birth_form,
                "expected_birth_version": version,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    first = await send(DAYUN, form, 0)
    assert first["messages"][-1]["status"] == "ask_user"
    assert first["messages"][-1]["text"] == ASK_FORM_GENDER
    second = await send("我是男生", form, first["birth_version"])
    assert second["messages"][-1]["status"] == "ask_user"
    assert second["messages"][-1]["text"] == ASK_FORM_GENDER
    assert second["birth"]["gender"] == ""
    third = await send("继续", {**form, "gender": "male"}, second["birth_version"])
    assert third["birth_version"] > second["birth_version"]
    assert third["messages"][-1]["status"] == "submit_reading", third["messages"][-1]
    assert third["reading"]["birth_context"]["birth"]["gender"] == "male"
