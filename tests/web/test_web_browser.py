"""真实浏览器回归：塔罗对话、会话轮询、排盘滚动与折叠表单校验。

需要 Playwright 与 Chromium；未安装浏览器时跳过（CI 只在 Ubuntu 上安装）。"""

import json
import socket
import threading
import time

import pytest

pytest.importorskip("fastapi")
sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect
uvicorn = pytest.importorskip("uvicorn")

from app import create_runtime  # noqa: E402
from harness.models import ModelResponse, ToolCall  # noqa: E402
from tests.conftest import ScriptedModel  # noqa: E402
from web import create_web_app  # noqa: E402


@pytest.fixture
def site(project):
    runtimes = []

    def factory(**kwargs):
        runtime = create_runtime(**kwargs, seed=42)
        runtimes.append(runtime)
        return runtime

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_web_app(root=project, runtime_factory=factory),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            pytest.fail("网页服务未能启动")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", runtimes
    server.should_exit = True
    thread.join(10)


@pytest.fixture
def chromium():
    with sync_api.sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch()
        except sync_api.Error as error:
            pytest.skip(f"Chromium 不可用：{error}")
        yield chromium
        chromium.close()


def open_tarot(chromium, base, reduced_motion=True):
    page = chromium.new_page(
        viewport={"width": 1280, "height": 900},
        reduced_motion="reduce" if reduced_motion else "no-preference",
    )
    chats = []
    page.on(
        "request",
        lambda r: chats.append(json.loads(r.post_data)) if r.url.endswith("/api/chat") else None,
    )
    page.goto(f"{base}/tarot")
    expect(page.locator("#tarot-begin")).to_be_enabled()
    return page, chats


def pick(page, *positions):
    # The fan overlaps; click the buttons directly, as a tap on each would.
    page.evaluate(
        "positions => positions.forEach((i) => document.querySelectorAll('.deck-card')[i].click())",
        list(positions),
    )


def draw(page, question, *positions):
    page.fill("#tarot-question", question)
    page.click("#tarot-begin")
    pick(page, *positions)


def answered(page, action):
    """Run an action that sends one /api/chat request; return once the page has applied the
    answer. The thinking bubble is also .msg-assistant, so counting bubbles is not enough."""
    with page.expect_response(lambda r: r.url.endswith("/api/chat")):
        action()
    expect(page.locator("#thinking")).to_have_count(0)
    expect(page.locator("#chat-form")).to_have_attribute("aria-busy", "false")


def reply(page, text):
    page.fill("#message", text)
    page.press("#message", "Enter")


def clarifying_model():
    return ScriptedModel(
        [
            response("start_reading", question="A 还是 B？"),
            response("ask_user", question="A 和 B 分别是什么？"),
            response("draw_tarot", spread="three_card", question="A 还是 B？"),
            response("ask_user", question="还想看哪一张？"),
        ]
    )


def response(name, **arguments):
    return ModelResponse(tool_calls=[ToolCall(id=name, name=name, arguments=arguments)])


def test_reply_to_a_clarifying_question_continues_the_round(site, chromium):
    base, runtimes = site
    page, chats = open_tarot(chromium, base)
    runtimes[-1].model = clarifying_model()
    answered(page, lambda: draw(page, "A 还是 B？", 4, 40, 70))
    assert page.is_hidden("#tarot-deck") and page.is_hidden("#tarot-begin")

    answered(page, lambda: reply(page, "A 是留在原公司，B 是去新公司"))
    # Sent straight away, with the same spread and positions; the deck never reopened.
    assert len(chats) == 2
    assert chats[1]["message"] == "A 是留在原公司，B 是去新公司"
    assert (chats[1]["spread"], chats[1]["picks"]) == ("three_card", [4, 40, 70])
    assert page.input_value("#tarot-question") == "A 还是 B？"
    assert page.is_hidden("#tarot-deck")
    assert runtimes[-1].session.state["tarot_result"]["picks"] == [4, 40, 70]


def test_a_round_left_open_survives_a_reload(site, chromium):
    base, runtimes = site
    page, chats = open_tarot(chromium, base)
    runtimes[-1].model = clarifying_model()
    answered(page, lambda: draw(page, "A 还是 B？", 4, 40, 70))

    page.reload()
    # The round comes back from the server: question, chosen positions, no deck.
    expect(page.locator("#tarot-question")).to_have_value("A 还是 B？")
    expect(page.locator("#tarot-spread .tarot-slot.is-picked")).to_have_count(3)
    assert page.is_hidden("#tarot-deck") and page.is_hidden("#tarot-begin")

    answered(page, lambda: reply(page, "A 是留在原公司，B 是去新公司"))
    assert len(chats) == 2
    assert chats[1]["message"] == "A 是留在原公司，B 是去新公司"
    assert (chats[1]["spread"], chats[1]["picks"]) == ("three_card", [4, 40, 70])
    assert page.is_hidden("#tarot-deck")
    assert runtimes[-1].session.state["tarot_result"]["picks"] == [4, 40, 70]


def test_starting_over_during_the_last_flight_sends_nothing(site, chromium):
    base, _ = site
    page, chats = open_tarot(chromium, base, reduced_motion=False)
    page.fill("#tarot-question", "最近的状态")
    page.click("#tarot-begin")
    page.wait_for_timeout(700)  # let the deck fan out
    # The third card is still flying (520 ms) when 重新起问 is pressed.
    page.evaluate(
        """() => {
          const cards = document.querySelectorAll('.deck-card');
          [3, 30, 60].forEach((i) => cards[i].click());
          document.querySelector('#new-question').click();
        }"""
    )
    page.wait_for_timeout(1500)
    assert chats == []
    assert page.locator("#messages .msg-error").count() == 0
    assert page.input_value("#tarot-question") == ""
    assert page.locator(".deck-flyer").count() == 0


def test_a_record_from_history_shows_its_own_question(site, chromium):
    base, _ = site
    page, _ = open_tarot(chromium, base)
    answered(page, lambda: draw(page, "未来的工作状态如何", 1, 2, 3))
    page.click("#new-question")
    expect(page.locator("#tarot-question")).to_have_value("")
    answered(page, lambda: draw(page, "感情关系有哪些反思线索", 10, 20, 30))
    expect(page.locator("#history-list .history-item")).to_have_count(2)

    page.click("#open-history")
    page.click("#history-list .history-item:has-text('未来的工作状态如何')")
    expect(page.locator("#tarot-question")).to_have_value("未来的工作状态如何")

    # A new conversation starts clean: no old question, no old cards.
    page.click("#new-chat")
    expect(page.locator("#tarot-question")).to_have_value("")
    expect(page.locator(".flip-card")).to_have_count(0)
    assert page.is_visible("#tarot-begin")


def test_an_unsent_question_survives_looking_at_a_record(site, chromium):
    base, _ = site
    page, _ = open_tarot(chromium, base)
    answered(page, lambda: draw(page, "下个月的重心", 5, 6, 7))
    page.click("#new-question")
    expect(page.locator("#tarot-question")).to_have_value("")
    page.fill("#tarot-question", "还没发出的问题")
    page.click("#open-history")
    page.click("#history-list .history-item")
    expect(page.locator("#tarot-question")).to_have_value("下个月的重心")
    page.click("#new-question")
    expect(page.locator("#tarot-question")).to_have_value("还没发出的问题")


def test_explicit_history_followup_sends_the_selected_record_and_survives_reload(site, chromium):
    base, _ = site
    page, chats = open_tarot(chromium, base)
    answered(page, lambda: draw(page, "旧记录的工作状态", 1, 2, 3))
    original = page.request.get(f"{base}/api/session?system=tarot").json()["reading"]
    page.click("#new-question")
    expect(page.locator("#tarot-question")).to_have_value("")
    answered(page, lambda: draw(page, "新记录的感情线索", 10, 20, 30))
    page.click("#open-history")
    page.click("#history-list .history-item:has-text('旧记录的工作状态')")
    page.get_by_role("button", name="继续这份解读", exact=True).click()
    answered(page, lambda: reply(page, "第一张牌具体什么意思？"))
    assert chats[-1]["reading_id"] == original["reading_id"]
    current = page.request.get(f"{base}/api/session?system=tarot").json()
    assert current["reading"]["tarot"] == original["tarot"]
    assert len(current["reading"]["responses"]) == 1
    expect(page.get_by_text("历次追问（1 次）", exact=True)).to_be_visible()
    page.reload()
    expect(page.locator("#send")).to_be_enabled()
    answered(page, lambda: reply(page, "第二张牌具体什么意思？"))
    assert chats[-1]["reading_id"] == original["reading_id"]
    expect(page.get_by_text("历次追问（2 次）", exact=True)).to_be_visible()
    page.close()


def test_clearing_records_also_clears_an_unsent_question(site, chromium):
    base, _ = site
    page, _ = open_tarot(chromium, base)
    answered(page, lambda: draw(page, "下个月的重心", 5, 6, 7))
    page.click("#new-question")
    expect(page.locator("#tarot-question")).to_have_value("")
    page.fill("#tarot-question", "还没发出的私人问题")
    page.click("#open-history")
    page.click("#history-list .history-item")
    expect(page.locator("#tarot-question")).to_have_value("下个月的重心")

    page.click("#forget")
    page.click("#confirm-dialog button[value=confirm]")
    expect(page.locator("#history-list .history-item")).to_have_count(0)
    expect(page.locator("#tarot-question")).to_have_value("")


def test_thinking_bubble_shows_progress_labels(site, chromium):
    base, _ = site
    page, _ = open_tarot(chromium, base)
    page.route(
        "**/api/progress?*",
        lambda route: route.fulfill(
            status=200,
            content_type="text/event-stream",
            body='data: {"label":"事实核对未通过，正在改写"}\n\n',
        ),
    )
    page.evaluate("""() => {
      const realFetch=window.fetch;
      window.fetch=async (input, options) => {
        if (new URL(String(input), location.origin).pathname === '/api/chat') await new Promise(resolve=>setTimeout(resolve,1500));
        return realFetch(input,options);
      };
    }""")
    draw(page, "看近期状态", 0, 1, 2)
    expect(page.locator("#thinking .thinking span")).to_have_text("事实核对未通过，正在改写")
    expect(page.locator("#thinking")).to_have_count(0, timeout=20000)
    page.close()


def test_busy_session_on_ask_keeps_polling_without_a_transcript(site, chromium):
    base, _ = site
    page = chromium.new_page()
    calls, errors = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def session(route):
        response = route.fetch()
        data = response.json()
        data["busy"] = not calls
        calls.append(data["busy"])
        route.fulfill(response=response, json=data)

    page.route("**/api/session**", session)
    page.goto(f"{base}/ask?provider=demo")
    expect(page.locator("#messages")).to_have_count(0)
    expect(page.locator("#birth-date")).to_be_disabled()
    expect(page.locator("#birth-date")).to_be_enabled(timeout=10000)
    expect(page.locator("#connection")).to_have_text("离线演示")
    expect(page.locator("#toast")).to_be_hidden()
    assert calls == [True, False]
    assert not errors
    page.close()


def open_saved_birth(chromium, base, slug, width=1280):
    page = chromium.new_page(viewport={"width": width, "height": 844}, reduced_motion="reduce")
    page.goto(f"{base}/{slug}?provider=demo")
    expect(page.locator("#birth-country")).to_be_enabled()
    result = page.request.put(
        f"{base}/api/birth",
        data={
            "date": "2001-11-25",
            "time": "10:11",
            "unknown_time": False,
            "location_id": "1803361",
            "gender": "male",
        },
        headers={"X-Zhiming-Client": "web", "Origin": base},
    )
    assert result.ok, result.text()
    page.reload()
    expect(page.locator("#birth-district")).to_have_value("1803361")
    expect(page.locator("#birth-country")).to_be_enabled()
    expect(page.locator("[data-birth-fold]")).not_to_have_attribute("open", "")
    return page


@pytest.mark.parametrize("slug", ["astro", "bazi"])
@pytest.mark.parametrize("width", [390, 1280])
def test_drawing_scrolls_to_the_chart_result(site, chromium, slug, width):
    base, _ = site
    page = open_saved_birth(chromium, base, slug, width)
    if slug == "bazi":
        page.locator("[data-birth-fold] > summary").click()
    with page.expect_response(lambda r: r.url.endswith("/api/chart")) as response:
        page.locator("#draw-chart" if slug == "astro" else "#birth-form button").click()
    assert response.value.ok, response.value.text()
    assert not response.value.json().get("question")
    expect(page.locator("[data-birth-fold]")).not_to_have_attribute("open", "")
    expect(page.locator("#astro-empty" if slug == "astro" else "#bazi-empty")).to_be_hidden()
    # The result starts at the viewport top even when the birth bar wraps on mobile.
    page.wait_for_function(
        "() => Math.abs(document.querySelector('.band-work').getBoundingClientRect().top) < 2",
        timeout=5000,
    )
    page.close()


@pytest.mark.parametrize("date", ["1800-01-01", "9999-12-31"])
def test_external_draw_opens_invalid_folded_birth_form(site, chromium, date):
    base, _ = site
    page = open_saved_birth(chromium, base, "astro")
    errors, charts = [], []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("request", lambda r: charts.append(r.url) if r.url.endswith("/api/chart") else None)
    page.locator("[data-birth-fold] > summary").click()
    page.fill("#birth-date", date)
    page.locator("[data-birth-fold] > summary").click()
    page.click("#draw-chart")
    expect(page.locator("[data-birth-fold]")).to_have_attribute("open", "")
    expect(page.locator("#birth-date")).to_be_visible()
    expect(page.locator("#birth-date")).to_be_focused()
    assert page.locator("#birth-date").evaluate("el => !el.validity.valid")
    assert charts == []
    assert not errors
    # Correcting the revealed field allows the same external button to draw normally.
    page.fill("#birth-date", "2001-11-25")
    page.locator("[data-birth-fold] > summary").click()
    with page.expect_response(lambda r: r.url.endswith("/api/chart")) as response:
        page.click("#draw-chart")
    assert response.value.ok, response.value.text()
    expect(page.locator("#astro-empty")).to_be_hidden()
    assert len(charts) == 1
    page.close()


def test_name_calculation_and_chosen_form_survive_navigation_and_reload(site, chromium):
    base, _ = site
    page = chromium.new_page()
    page.goto(f"{base}/name?provider=demo")
    expect(page.locator("#name-surname")).to_be_enabled()
    page.fill("#name-surname", "赵")
    page.fill("#name-given", "杰")
    with page.expect_response(lambda r: r.url.endswith("/api/name")):
        page.get_by_role("button", name="推演五格").click()
    expect(page.locator("#name-board")).to_be_visible()
    with page.expect_response(lambda r: r.url.endswith("/api/name")):
        page.locator('#name-forms input[value="杰"]').check()
    expect(page.locator("#name-chars")).to_contain_text("八画")
    original = page.locator("#name-board").inner_text()

    page.locator('.zm-nav a[href="/ask"]').click()
    expect(page.locator("#connection")).to_have_text("离线演示")
    page.locator('.zm-nav a[href="/name"]').click()
    for reload in (False, True):
        if reload:
            page.reload()
        expect(page.locator("#name-surname")).to_have_value("赵")
        expect(page.locator("#name-given")).to_have_value("杰")
        expect(page.locator("#name-board")).to_be_visible()
        expect(page.locator('#name-forms input[value="杰"]')).to_be_checked()
        expect(page.locator('#name-forms input[value="傑"]')).not_to_be_checked()
        assert page.locator("#name-board").inner_text() == original

    page.click("#forget")
    page.click("#confirm-dialog button[value=confirm]")
    expect(page.locator("#name-board")).to_be_hidden()
    expect(page.locator("#name-surname")).to_have_value("")
    page.reload()
    expect(page.locator("#name-surname")).to_be_enabled()
    expect(page.locator("#name-board")).to_be_hidden()
    expect(page.locator("#name-given")).to_have_value("")
    page.close()
