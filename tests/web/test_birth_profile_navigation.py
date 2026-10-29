"""Saving the profile on the home page must populate each feature's form."""

import pytest

expect = pytest.importorskip("playwright.sync_api").expect

from tests.web.test_web_browser import chromium as chromium  # noqa: E402
from tests.web.test_web_browser import site as site  # noqa: E402


def test_saved_home_profile_follows_feature_navigation(site, chromium):
    base, _ = site
    context = chromium.new_context(reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{base}/ask?provider=demo")
    expect(page.locator("#birth-date")).to_be_enabled()
    page.fill("#birth-date", "1994-03-18")
    page.fill("#birth-time", "08:30")
    page.select_option("#birth-gender", "female")
    page.select_option("#birth-province", "1818058")
    expect(page.locator("#birth-city")).to_be_enabled()
    page.select_option("#birth-city", "1810843")
    expect(page.locator("#birth-district")).to_be_enabled()
    page.select_option("#birth-district", "1803361")
    expect(page.locator("#location-feedback")).to_contain_text("Asia/Shanghai")
    with page.expect_response(lambda r: "/api/birth?" in r.url) as saved:
        page.locator("#birth-form button[type=submit]").click()
    assert saved.value.status == 200
    expected_birth = saved.value.json()["birth"]
    expect(page.locator("#profile-status")).to_have_text("已保存")
    page.locator('.enroll-next[href="/bazi"]').click()
    for system in ("bazi", "astro", "daily"):
        if system != "bazi":
            page.locator(f'.zm-nav a[href="/{system}"]').click()
        expect(page.locator("#birth-date")).to_have_value(expected_birth["date"])
        expect(page.locator("#birth-time")).to_have_value(expected_birth["time"])
        expect(page.locator("#birth-district")).to_have_value(expected_birth["location_id"])
        assert (
            page.request.get(f"{base}/api/session?system={system}").json()["birth"]
            == expected_birth
        )
    assert not errors
    context.close()
