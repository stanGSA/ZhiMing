"""Stage 1 B1/B3: relationship and finance directions, still drafts until cross-reviewed."""

import pytest
import yaml

from app import ROOT, create_runtime
from knowledge.catalogues import expected_keys
from knowledge.review import content_hash
from scripts import model_review_kb as review
from scripts.draft_week23 import DIGNITY, GOD_TEXT, HOUSE_THEME, PLANET_NATURE, draft
from signals.merge import merge_signals
from tests.test_week6 import ask, with_birth
from tests.test_week23_integration import invoke

THEMES = ("relationship", "finance")
OUTER = ("Uranus", "Neptune", "Pluto")


def source(system):
    path = ROOT / f"knowledge/sources/{system}/entries.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["entries"]


def directed(entry):
    return any(entry["theme_map"][theme] for theme in THEMES)


@pytest.mark.parametrize("system", ["astro", "bazi"])
def test_drafts_regenerate_the_b1_sources(system):
    """Rerunning scripts/draft_week23.py keeps B1 content, so ledger hashes still match."""
    generated = [draft(*key) for key in sorted(expected_keys(system))]
    assert [content_hash(e) for e in generated] == [content_hash(e) for e in source(system)]


def test_every_ten_god_has_a_relationship_or_finance_direction():
    gods = {e["key"]: e for e in source("bazi") if e["kind"] == "ten_god"}
    assert set(gods) == set(GOD_TEXT) and all(directed(e) for e in gods.values())
    # A ten god at a pillar says the same as the ten god itself.
    for entry in source("bazi"):
        if entry["kind"] == "god_pillar":
            god = gods[entry["key"].split(":")[0]]
            assert {t: entry["theme_map"][t] for t in THEMES} == {
                t: god["theme_map"][t] for t in THEMES
            }


def test_classical_planets_have_directions_and_outer_planets_stay_neutral():
    astro = [e for e in source("astro") if e["kind"] in ("planet_sign", "planet_house")]
    for planet in ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"):
        assert any(directed(e) for e in astro if e["key"].startswith(f"{planet}:"))
    assert not any(directed(e) for e in astro if e["key"].split(":")[0] in OUTER)
    for entry in astro:
        planet, place = entry["key"].split(":")
        if entry["kind"] == "planet_sign":
            strong, weak = DIGNITY.get(planet, ({}, {}))
            # Only a dignity or debility gives a sign direction, and with the matching sign.
            for theme in THEMES:
                value = entry["theme_map"][theme]
                if value:
                    assert place in strong or place in weak, entry["id"]
                    assert (value > 0) == (place in strong), entry["id"]
        else:
            expected = PLANET_NATURE.get(planet) if place in HOUSE_THEME else None
            theme = HOUSE_THEME.get(place)
            assert entry["theme_map"].get(theme, 0.0) == (expected or 0.0)


@pytest.mark.parametrize("system", ["astro", "bazi"])
def test_directions_are_stated_in_the_text_and_attributed(system):
    for entry in source(system):
        for theme, word in (("relationship", "感情方面"), ("finance", "财务方面")):
            assert bool(entry["theme_map"][theme]) <= (word in entry["text"]), entry["id"]
        changed = directed(entry)
        assert ("Anthropic Claude" in entry["source"]) == changed, entry["id"]
        assert entry["version"] == (4 if changed else 3) and entry["reviewed"] is False


def test_b1_drafter_cannot_review():
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert "anthropic" in review.drafter_vendors(config)
    spec = dict(api="openai", model="m", api_key_env="KEY", base_url="https://example.test/v1")
    roles = {
        "reviewer_a": review.RoleConfig(vendor="Anthropic", **{**spec, "api": "anthropic"}),
        "reviewer_b": review.RoleConfig(vendor="vendor-b", **spec),
        "reviser": None,
    }
    with pytest.raises(ValueError, match="起草"):
        review.check_roles(roles, config, review.REVIEWERS)


def test_daily_entries_stay_neutral_conventions():
    """B3: the nine daily entries are conventions; daily directions come from other systems."""
    assert len(source("daily")) == 9 and not any(directed(e) for e in source("daily"))


# Synthetic births found by searching 1988-1991 charts; each gives the verdict through real
# natal astro (planet in sign/house) and natal bazi (ten god at a pillar) signals.
@pytest.mark.parametrize(
    "birth,expected",
    [
        ("1988-01-20 15:00", {("tension", "relationship")}),
        ("1988-06-05 07:00", {("tension", "finance")}),
        ("1988-02-06 20:00", {("resonance", "relationship"), ("resonance", "finance")}),
    ],
)
async def test_relationship_and_finance_form_tension_and_resonance(project, birth, expected):
    runtime = create_runtime(project, user_id="synthetic-b1", seed=1)
    try:
        runtime.session.append_user(f"我是男，出生于{birth}，北京；用于合成测试。")
        assert (await invoke(runtime, "start_reading", dict(question="感情与财运"))).ok
        place = await invoke(runtime, "resolve_location", dict(query="北京"))
        args = dict(
            birth_local=birth, location_id=place.data["location"]["location_id"], time_known=True
        )
        assert (await invoke(runtime, "compute_natal_chart", args)).ok
        assert (await invoke(runtime, "compute_bazi", {**args, "gender": "male"})).ok
        signals = runtime.session.state["signals"]
        merged = merge_signals(signals, runtime.kb.rules("merge"))
        items = [i for i in merged["tensions"] + merged["resonances"] if i["theme"] in THEMES]
        assert {(i["kind"], i["theme"]) for i in items} == expected
        kinds = {s["ref_id"]: s["kb_ref"].split(":")[2] for s in signals}
        for item in items:
            assert item["horizon"] == "trait" and set(item["systems"]) == {"astro", "bazi"}
            assert {kinds[r] for r in item["refs"]["astro"]} <= {"planet_sign", "planet_house"}
            assert {kinds[r] for r in item["refs"]["bazi"]} == {"god_pillar"}
            # Drafts until two vendors approve them: the reading stays low confidence.
            assert all(s["review_status"] == "draft" for s in signals)
    finally:
        runtime.close()


async def test_daily_signals_carry_ten_god_relationship_and_finance(runtime):
    with_birth(runtime)
    await ask(runtime, "今天运势怎么样？")
    result = await invoke(runtime, "daily_fortune", dict(date=runtime.session.calendar_anchor))
    assert result.ok, result.error
    day = [
        s
        for s in runtime.session.state["signals"]
        if s["kb_ref"].startswith("kb:bazi:ten_god:") and s["theme"] in THEMES
    ]
    assert day and all(s["horizon"] == "moment" for s in day)


def test_b1_counts_quoted_in_the_report():
    astro = [e for e in source("astro") if directed(e)]
    bazi = [e for e in source("bazi") if directed(e)]
    assert (len(astro), len(bazi)) == (60, 50)
