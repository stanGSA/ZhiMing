"""Failures found while preparing the first real knowledge review."""

import asyncio
import copy
import json

import pytest
import yaml

from harness.llm import RoleModelSpec, role_model
from harness.models import ModelResponse
from knowledge.checks import certainty_finding
from knowledge.review import load_ledgers
from scripts import draft_week6, draft_week23
from scripts import model_review_kb as review
from scripts.draft_sources import write_drafts
from scripts.kb_review_budget import BudgetExceeded, BudgetModel, ReviewBudget
from tests.knowledge.test_model_review import ROLES
from tests.knowledge.test_review_revocation import TARGET, tower_run
from tests.knowledge_fixture import copy_draft_knowledge


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    copy_draft_knowledge(review.ROOT / "knowledge", tmp_path / "knowledge")
    config = review.load_config(review.ROOT)
    config["kb_review"] = dict(roles=copy.deepcopy(ROLES))
    for spec in ROLES.values():
        monkeypatch.setenv(spec["api_key_env"], "offline-placeholder")
    return review.Workspace(tmp_path), config


@pytest.mark.parametrize("system", ["astro", "bazi", "name", "dream", "daily"])
def test_authoring_rerun_preserves_revised_source(tmp_path, system):
    path = next((review.ROOT / "knowledge/sources" / system).glob("*.yaml"))
    original = yaml.safe_load(path.read_text(encoding="utf-8"))["entries"]
    target = tmp_path / "entries.yaml"
    write_drafts(target, original)
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    data["entries"][0]["text"] += "审核后修订，仍须重新双审。"
    data["entries"][0]["version"] += 1
    target.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    edited = target.read_bytes()
    with pytest.raises(ValueError, match="拒绝覆盖"):
        write_drafts(target, original)
    assert target.read_bytes() == edited


@pytest.mark.parametrize("module", [draft_week23, draft_week6])
def test_authoring_main_is_noop_on_current_sources(tmp_path, monkeypatch, module):
    monkeypatch.setattr(module, "ROOT", tmp_path)
    module.main()
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.yaml")}
    module.main()
    assert all(p.read_bytes() == data for p, data in before.items())


async def test_uncalibrated_rereview_still_revokes_matching_approval(workspace, tmp_path):
    workspace, config = workspace
    _, old, _ = await tower_run(workspace, config, tmp_path / "old", "pass")
    review.record_ledger(workspace, [old.path], root=tmp_path)
    assert TARGET in load_ledgers(workspace.reviews)
    _, new, _ = await tower_run(workspace, config, tmp_path / "new", "reject", passes=1)
    with pytest.raises(ValueError, match="未达到"):
        review.record_ledger(workspace, [new.path], root=tmp_path)
    assert TARGET not in load_ledgers(workspace.reviews)
    revoked = review.read_json(new.path / "ledger_revocations.json")["records"]
    assert [row["id"] for row in revoked] == [TARGET]


async def test_concurrent_revisions_keep_all_proposals_and_resume(workspace, tmp_path):
    work, config = workspace
    plan = review.prepare(work, config, "daily")
    run = review.open_run(tmp_path / "parallel-revision", plan)
    review.write_json(
        run.path / "revision_queue.json",
        [dict(id=e["id"], verdicts={}, code_findings=[]) for e in plan["entries"][:6]],
    )
    active = maximum = calls = 0

    class Reviser:
        async def chat(self, messages, tools):
            nonlocal active, maximum, calls
            active += 1
            calls += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            proposal = json.loads(messages[-1]["content"])["entry"]
            active -= 1
            return ModelResponse(model="independent-reviser", text=json.dumps(proposal))

    options = dict(make_model=lambda *_: Reviser(), concurrency=3)
    result = await review.revise(run, plan, review.load_roles(config), **options)
    assert calls == 6 and maximum == 3
    assert len(result) == 6 and all(p["invalid"] is None for p in result)
    assert review.read_json(run.path / "revisions.json") == result
    assert await review.revise(run, plan, review.load_roles(config), **options) == result
    assert calls == 6


@pytest.mark.parametrize(
    "clause",
    [
        "不代表现实运势或事件必然发生",
        "不表示精力一定会受牵扯",
        "并不意味着现实发展必然顺利",
        "不代表实际情况必然如此",
        "并不意味着使用此数的人必然遭遇波折",
        "不代表个人必然具备相应能力",
        "不代表个人必然具有某种性格",
        "不意味着现实生活必然不利",
    ],
)
def test_review_disclaimers_do_not_hide_following_assertions(clause):
    assert certainty_finding(clause + "。") is None
    assert certainty_finding(clause + "，但你必然破财。") == "必然"


@pytest.mark.parametrize("conflict", ["shared_alias", "other_key"])
def test_revision_apply_rejects_cross_entry_alias_collision_before_writes(
    workspace, tmp_path, conflict
):
    work, config = workspace
    plan = review.prepare(work, config, "daily")
    run = review.open_run(tmp_path / "collision", plan)
    entries = plan["entries"][:2]
    alias = "冲突同义词" if conflict == "shared_alias" else entries[1]["key"]
    proposals = []
    for index, entry in enumerate(entries):
        proposal = {k: entry[k] for k in ("text", "theme_map", "synonyms", "keywords")}
        proposal["synonyms"] = [alias] if index == 0 or conflict == "shared_alias" else []
        proposals.append(
            dict(
                id=entry["id"],
                before_sha256=review.content_hash(entry),
                proposal=proposal,
                invalid=None,
            )
        )
    review.write_json(run.path / "revisions.json", proposals)
    before = {p: p.read_bytes() for p in review.source_paths(work.sources, "daily")}
    with pytest.raises(ValueError, match="同义词冲突"):
        review.apply_revisions(work, run)
    assert all(p.read_bytes() == content for p, content in before.items())


def test_runtime_vendor_exception_is_scoped_to_exact_model():
    config = review.load_config(review.ROOT)
    review.check_roles(review.load_roles(config), config, review.REVIEWERS)
    config["kb_review"]["roles"]["reviewer_a"]["model"] = "another-deepseek-model"
    with pytest.raises(ValueError, match="运行时模型"):
        review.check_roles(review.load_roles(config), config, review.REVIEWERS)


async def test_relay_address_is_read_from_the_environment(monkeypatch):
    roles = review.load_roles(review.load_config(review.ROOT))
    spec = roles["reviewer_b"]
    assert spec.base_url is None and spec.base_url_env == "OPENAI_REVIEW_BASE_URL"
    monkeypatch.delenv("OPENAI_REVIEW_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="未设置 OPENAI_REVIEW_BASE_URL"):
        review.require_endpoints(roles, ("reviewer_b", "reviser"))
    with pytest.raises(ValueError, match="未设置 OPENAI_REVIEW_BASE_URL"):
        role_model(spec)  # never the vendor's default endpoint with the relay's key
    assert review.public_spec(spec)["base_url_host"] is None
    # With the address used on 2026-10-21 a run binds to exactly the archived identity.
    monkeypatch.setenv("OPENAI_REVIEW_BASE_URL", "https://codegoai.com/v1")
    monkeypatch.setenv(spec.api_key_env, "offline-placeholder")
    historical = review.read_json(
        review.ROOT / "docs/verification/kb-model-review/20261021-live/astro-initial/manifest.json"
    )
    assert review.public_spec(spec) == historical["reviewers"]["reviewer_b"]
    model = role_model(spec)
    try:
        assert str(model.client.base_url).startswith("https://codegoai.com/v1")
    finally:
        await model.close()
    with pytest.raises(ValueError, match="只能配置一个"):
        RoleModelSpec(
            **dict(
                spec.model_dump(include=RoleModelSpec.model_fields.keys()),
                base_url="https://x.example",
            )
        )


def test_reviser_exception_is_bound_to_historical_reviewers():
    config = review.load_config(review.ROOT)
    roles = review.load_roles(config)
    review.check_roles(roles, config, (*review.REVIEWERS, "reviser"))
    reviewers = {name: review.public_spec(roles[name]) for name in review.REVIEWERS}
    exception = config["kb_review"]["reviser_vendor_exception"]
    assert review.reviser_exception_matches(roles["reviser"], reviewers, exception)
    reviewers["reviewer_b"]["model"] = "different-historical-model"
    assert not review.reviser_exception_matches(roles["reviser"], reviewers, exception)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("这不代表困扰必然消退，也不预示具体事件。", None),
        ("不代表困扰必然消退，但你必然破财。", "必然"),
        ("困扰必然消退。", "必然"),
        ("不代表状态必然好转或事件必然发生。", None),
        ("不代表负担必然减轻。", None),
        ("不代表过去不好但你必然好转。", "必然"),
    ],
)
def test_revision_negation_does_not_hide_a_positive_assertion(text, expected):
    assert certainty_finding(text) == expected


async def test_revision_parse_failure_keeps_full_response_and_usage(workspace, tmp_path):
    workspace, config = workspace
    plan = review.prepare(workspace, config, "tarot", only_ids=[TARGET])
    run = review.open_run(tmp_path / "run", plan)
    review.write_json(
        run.path / "revision_queue.json", [dict(id=TARGET, verdicts={}, code_findings=[])]
    )
    raw = "invalid JSON " + "完整输出" * 2000

    class Reviser:
        async def chat(self, messages, tools):
            return ModelResponse(
                text=raw, model="actual-reviser", input_tokens=123, output_tokens=456
            )

    roles = review.load_roles(config)
    assert await review.revise(run, plan, roles, make_model=lambda *_: Reviser()) == []
    error = run.errors()[0]
    assert error["raw_text"] == raw and error["returned_model"] == "actual-reviser"
    assert error["usage_available"] and error["latency_s"] >= 0
    usage = review.usage_summary(run, roles)["reviser"]
    assert usage["input_tokens"] == 123 and usage["output_tokens"] == 456


def budget_config(**kwargs):
    return dict(kb_review=dict(budget=dict(state_path="budget.json", currency="USD", **kwargs)))


def priced_spec():
    return review.RoleConfig(**dict(ROLES["reviewer_a"], max_tokens=100))


def test_budget_reservations_survive_restart_and_unknown_usage(tmp_path):
    config = budget_config(limit="0.01")
    spec = priced_spec()
    budget = ReviewBudget(config, tmp_path)
    request = budget.reserve("reviewer_a", spec, [])
    initial = json.loads(budget.path.read_text())["requests"][0]["held"]
    budget.settle(request, ModelResponse(usage_available=False), 1)
    assert json.loads(budget.path.read_text())["requests"][0]["held"] == initial
    # A new object/process sees the first request's unreleased reservation.
    resumed = ReviewBudget(config, tmp_path)
    with pytest.raises(BudgetExceeded):
        resumed.reserve("reviewer_a", spec, [])


async def test_budget_blocks_network_and_counts_parse_retries(tmp_path):
    budget = ReviewBudget(budget_config(limit="0.000001"), tmp_path)
    asked = []

    class Model:
        async def chat(self, messages, tools):
            asked.append(messages)
            return ModelResponse(text="bad JSON", input_tokens=10, output_tokens=5)

    model = BudgetModel(Model(), "reviewer_a", priced_spec(), budget)
    with pytest.raises(BudgetExceeded):
        await model.chat([], [])
    assert asked == []


async def test_explicit_unlimited_budget_records_unpriced_calls(tmp_path):
    budget = ReviewBudget(budget_config(unlimited=True), tmp_path)
    spec = review.RoleConfig(**ROLES["reviewer_b"])

    class Model:
        request_attempts = 0

        async def chat(self, messages, tools):
            self.request_attempts += 2
            return ModelResponse(model="actual-model", input_tokens=99, output_tokens=11)

    model = BudgetModel(Model(), "reviewer_b", spec, budget)
    await model.chat([], [])
    assert model.request_attempts == 2
    rows = json.loads(budget.path.read_text())["requests"]
    assert rows[0]["returned_model"] == "actual-model" and rows[0]["input_tokens"] == 99
    assert rows[0]["held"] is None  # Unknown price is never reported as zero cost.


async def test_parallel_budget_models_attribute_each_http_retry(tmp_path):
    budget = ReviewBudget(budget_config(unlimited=True), tmp_path)
    active, peak, closed = 0, 0, []

    class Model:
        request_attempts = 0

        async def chat(self, messages, tools):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            self.request_attempts += 2
            await asyncio.sleep(0.01)
            active -= 1
            return ModelResponse(input_tokens=10, output_tokens=2)

        async def close(self):
            closed.append(self)

    model = BudgetModel(None, "reviewer_a", priced_spec(), budget, make_model=Model)

    async def one():
        await model.chat([], [])
        return model.request_attempts

    assert await asyncio.gather(one(), one(), one()) == [2, 2, 2]
    assert peak == 3 and len(closed) == 3
    assert {r["http_attempts"] for r in json.loads(budget.path.read_text())["requests"]} == {2}
