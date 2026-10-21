"""Offline tests of scripts/model_review_kb.py: two mock vendors over httpx.MockTransport."""

import asyncio
import json
from collections import Counter

import httpx
import pytest
import yaml

from app import ROOT
from harness.models import ModelResponse
from knowledge.build import build
from knowledge.kb import KnowledgeBase
from knowledge.review import content_hash
from scripts import model_review_kb as review
from tests.knowledge_fixture import copy_draft_knowledge

ROLES = dict(
    reviewer_a=dict(
        vendor="vendor-a",
        api="openai",
        model="model-a",
        api_key_env="TEST_REVIEW_A_KEY",
        base_url="https://a.test/v1",
        input_per_mtok=1.0,
        output_per_mtok=2.0,
        currency="USD",
    ),
    reviewer_b=dict(
        vendor="vendor-b",
        api="anthropic",
        model="model-b",
        api_key_env="TEST_REVIEW_B_KEY",
        base_url="https://b.test",
    ),
    reviser=dict(
        vendor="vendor-c",
        api="openai",
        model="model-c",
        api_key_env="TEST_REVIEW_C_KEY",
        base_url="https://c.test/v1",
    ),
)
# Ten cards, both orientations: small enough to run, large enough for every metric.
CARDS = ["the_fool", "the_magician", "the_tower", "the_star", "the_moon"]
CARDS += ["death", "strength", "the_sun", "the_world", "justice"]
IDS = [f"kb:tarot:card:{c}:{o}" for c in CARDS for o in ("upright", "reversed")]
# Both reviewers ask to revise these real entries, so kappa is defined and agreement is high.
DOUBTFUL = {"the_tower:upright", "death:reversed"}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    copy_draft_knowledge(ROOT / "knowledge", tmp_path / "knowledge")
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    config["kb_review"] = dict(timeout_s=10, roles=ROLES)
    for name in ("TEST_REVIEW_A_KEY", "TEST_REVIEW_B_KEY", "TEST_REVIEW_C_KEY"):
        monkeypatch.setenv(name, "test-placeholder")
    return review.Workspace(tmp_path), config


def real_entries(workspace):
    return {e["key"]: e for e in review.load_entries(workspace.sources, "tarot")}


class Reviewer:
    """A mock vendor: flags any item that differs from the source entry with that key."""

    def __init__(self, entries, name, rerun_flip=None, misses=(), broken=(), contradict=()):
        self.entries, self.name = entries, name
        self.rerun_flip = rerun_flip  # a key revised on the first look only
        self.misses = set(misses)  # mutations this reviewer never notices
        self.broken = list(broken)  # canned bad replies, served first
        self.contradict = set(contradict)  # keys answered "pass" while listing a problem
        self.seen = Counter()
        self.requests = []

    def verdicts(self, payload, planted_keys):
        out = []
        for item in payload["items"]:
            real = self.entries[item["key"]]
            changed = any(item[field] != real[field] for field in ("text", "theme_map", "synonyms"))
            batch = tuple(sorted(i["key"] for i in payload["items"]))
            self.seen[(batch, item["key"])] += 1
            first = self.seen[(batch, item["key"])] == 1
            mutation = planted_keys.get((item["key"], item["text"], json.dumps(item["theme_map"])))
            if changed and mutation not in self.misses:
                verdict = "reject" if "foreign" in str(mutation) else "revise"
            elif item["key"] in DOUBTFUL:
                verdict = "revise"
            elif item["key"] == self.rerun_flip and first:
                verdict = "revise"
            else:
                verdict = "pass"
            issues = [] if verdict == "pass" else [dict(dimension="consistency", detail="问题")]
            if item["key"] in self.contradict:
                verdict = "pass"
                issues = [dict(dimension="medical_legal_finance", detail="含医疗诊断式说法")]
            out.append(dict(item=item["item"], verdict=verdict, issues=issues, reason="理由"))
        return dict(items=out)


def mock_client(reviewer, api, planted_keys, returned):
    def respond(request):
        body = json.loads(request.content)
        reviewer.requests.append(body)
        if reviewer.broken:
            status, text = reviewer.broken.pop(0)
            if status != 200:
                return httpx.Response(status, json={"error": {"message": "bad request"}})
        else:
            user = body["messages"][-1]["content"]
            if api == "anthropic":
                user = user[0]["text"]
            text = json.dumps(reviewer.verdicts(json.loads(user), planted_keys), ensure_ascii=False)
        if api == "anthropic":
            return httpx.Response(
                200,
                json={
                    "id": "msg",
                    "type": "message",
                    "role": "assistant",
                    "model": returned,
                    "content": [{"type": "text", "text": text}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 100, "output_tokens": 20},
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "chat",
                "object": "chat.completion",
                "created": 0,
                "model": returned,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": f"```json\n{text}\n```"},
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            },
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(respond))


def factory(reviewers, plan):
    planted_keys = {
        (p["entry"]["key"], p["entry"]["text"], json.dumps(p["entry"]["theme_map"])): p["mutation"]
        for p in plan["planted"]
    }

    def make(role, spec):
        api = spec.api
        client = mock_client(reviewers[role], api, planted_keys, f"{spec.model}-2026")
        return review.role_model(spec, 10, http_client=client)

    return make


def plan_for(workspace, config, **options):
    defaults = dict(only_ids=IDS, plant_rate=0.25, batch_size=5, seed=7)
    return review.prepare(workspace, config, "tarot", **{**defaults, **options})


async def complete_run(workspace, config, path, reviewers=None, **options):
    plan = plan_for(workspace, config, **options)
    roles = review.load_roles(config)
    entries = real_entries(workspace)
    reviewers = reviewers or dict(
        reviewer_a=Reviewer(entries, "a"),
        reviewer_b=Reviewer(entries, "b", rerun_flip="the_star:upright"),
    )
    run = review.open_run(path, plan, dict(created_at="x"))
    result = await review.execute(run, plan, roles, make_model=factory(reviewers, plan))
    return plan, run, roles, reviewers, result


# ---- plan --------------------------------------------------------------------------------


def test_full_tarot_plan_is_blind_balanced_and_deterministic(workspace):
    workspace, config = workspace
    plan = review.prepare(workspace, config, "tarot")
    assert len(plan["entries"]) == 163 and len(plan["planted"]) == 16
    assert plan == review.prepare(workspace, config, "tarot")
    assert plan["planted"] != review.prepare(workspace, config, "tarot", seed=2)["planted"]
    counts = Counter(p["mutation"] for p in plan["planted"])
    # Every applicable tarot mutation is used and none dominates.
    assert set(counts) == {
        "flip_signs",
        "swap_orientation",
        "fatalistic",
        "medical",
        "foreign_text",
    }
    assert max(counts.values()) - min(counts.values()) <= 1
    originals = {p["ref"]: p["original"] for p in plan["planted"]}
    for batch in plan["batches"]:
        refs = {i["ref"] for i in batch["items"]}
        assert not any(originals[r] in refs for r in refs if r in originals)
        assert len(batch["items"]) <= 12
    by_id = {e["id"]: e for e in plan["entries"]}
    for item in plan["planted"]:
        assert content_hash(item["entry"]) != content_hash(by_id[item["original"]])
        assert item["entry"]["id"] == item["original"]  # the copy looks like the entry itself
    # Real and planted items show the same fields and nothing that identifies them.
    shown = [json.loads(p[1]["content"])["items"] for p in plan["prompts"].values()]
    keys = {frozenset(i) for items in shown for i in items if "counterpart" in i}
    assert len(keys) == 1
    text = json.dumps(plan["prompts"], ensure_ascii=False)
    assert "planted" not in text and "kb:tarot" not in text and "reviewed" not in text


def test_mutations_for_other_systems(workspace):
    workspace, config = workspace
    dream = review.prepare(workspace, config, "dream", plant_rate=0.1)
    assert "misleading_synonym" in {p["mutation"] for p in dream["planted"]}
    bazi = review.prepare(workspace, config, "bazi", plant_rate=0.3)
    wrong = [p for p in bazi["planted"] if p["mutation"] == "wrong_term"]
    assert wrong and all(p["entry"]["text"] != p["entry"]["key"] for p in wrong)


def test_vendor_rules(workspace):
    _, config = workspace
    roles = review.load_roles(config)
    review.check_roles(roles, config, (*review.REVIEWERS, "reviser"))
    same = dict(roles, reviewer_b=roles["reviewer_b"].model_copy(update=dict(vendor="Vendor-A")))
    with pytest.raises(ValueError, match="不同厂商"):
        review.check_roles(same, config, review.REVIEWERS)
    runtime = dict(roles, reviewer_a=roles["reviewer_a"].model_copy(update=dict(vendor="deepseek")))
    with pytest.raises(ValueError, match="运行时模型"):
        review.check_roles(runtime, config, review.REVIEWERS)
    reviser = dict(roles, reviser=roles["reviser"].model_copy(update=dict(vendor="vendor-b")))
    with pytest.raises(ValueError, match="自审自改"):
        review.check_roles(reviser, config, (*review.REVIEWERS, "reviser"))
    drafted = dict(config, kb_review={**config["kb_review"], "drafter_vendors": [" Vendor-B "]})
    with pytest.raises(ValueError, match="起草"):
        review.check_roles(roles, drafted, review.REVIEWERS)
    review.check_roles(roles, drafted, ("reviser",))  # the drafter may revise
    with pytest.raises(ValueError, match="未配置"):
        review.check_roles(dict(roles, reviewer_a=None), config, review.REVIEWERS)


def test_estimate_counts_calls_and_prices(workspace):
    workspace, config = workspace
    plan = plan_for(workspace, config)
    estimate = review.estimate(plan, review.load_roles(config))
    assert estimate["reviewer_a"]["calls"] == 2 * len(plan["batches"])
    assert estimate["reviewer_a"]["cost"] > 0 and estimate["reviewer_b"]["cost"] is None


# ---- run, resume, errors -----------------------------------------------------------------


async def test_run_resumes_logs_errors_and_records_identity(workspace, tmp_path):
    workspace, config = workspace
    entries = real_entries(workspace)
    reviewers = dict(
        # A bad JSON reply is retried; a 400 stops that call until the next invocation.
        reviewer_a=Reviewer(entries, "a", broken=[(200, "不是JSON")]),
        reviewer_b=Reviewer(entries, "b", broken=[(400, "")]),
    )
    path = tmp_path / "run1"
    plan, run, roles, reviewers, first = await complete_run(
        workspace, config, path, reviewers, passes=1
    )
    calls = len(plan["batches"]) * 2
    assert first["failed"] and first["cached"] == calls - 1
    kinds = Counter(e["kind"] for e in run.errors())
    assert kinds == {"parse_error": 1, "service_error": 1}
    requests = len(reviewers["reviewer_a"].requests) + len(reviewers["reviewer_b"].requests)
    # Resume: only the missing call is made again.
    again = await review.execute(run, plan, roles, make_model=factory(reviewers, plan))
    assert again == dict(completed=1, failed=[], cached=calls, expected=calls)
    assert len(reviewers["reviewer_a"].requests) + len(reviewers["reviewer_b"].requests) == (
        requests + 1
    )
    record = run.calls()[0]
    assert record["requested_model"] in ("model-a", "model-b")
    assert record["returned_model"] == record["requested_model"] + "-2026"
    retried = [c for c in run.calls() if c["attempt"] > 1]
    assert len(retried) == 1 and retried[0]["reviewer"] == "reviewer_a"
    # Blind: no request carries the other reviewer's verdicts or a planted marker.
    for body in reviewers["reviewer_b"].requests:
        text = json.dumps(body, ensure_ascii=False)
        assert "planted" not in text and 'verdict": "revise' not in text
    summary = review.merge(run, plan, roles)
    assert summary["usage"]["reviewer_a"]["errors"] == {"parse_error": 1}
    assert summary["usage"]["reviewer_b"]["errors"] == {"service_error": 1}
    assert summary["usage"]["reviewer_a"]["cost"] is not None
    assert (path / "report.md").read_text(encoding="utf-8").startswith("# 模型交叉审核：tarot")


async def test_interrupted_run_resumes_without_repeating_calls(workspace, tmp_path):
    workspace, config = workspace
    plan = plan_for(workspace, config, passes=1)
    roles = review.load_roles(config)
    path = tmp_path / "run-interrupted"
    run = review.open_run(path, plan)
    calls = []

    class Stops:
        def __init__(self, stop_at):
            self.stop_at = stop_at

        async def chat(self, messages, tools):
            calls.append(messages)
            if len(calls) == self.stop_at:
                raise asyncio.CancelledError
            await asyncio.sleep(0.01)  # a real request yields; cancellation lands here
            payload = json.loads(messages[-1]["content"])
            items = [dict(item=i["item"], verdict="pass", issues=[]) for i in payload["items"]]
            return ModelResponse(text=json.dumps(dict(items=items)), model="m")

    with pytest.raises(asyncio.CancelledError):
        await review.execute(run, plan, roles, make_model=lambda r, s: Stops(3), concurrency=1)
    assert {e["kind"] for e in run.errors()} == {"interrupted"}
    finished = len(run.calls())
    assert finished == 2
    before = len(calls)
    result = await review.execute(run, plan, roles, make_model=lambda r, s: Stops(0))
    assert result["cached"] == result["expected"]
    assert len(calls) - before == result["expected"] - finished  # finished calls not repeated


def test_run_directory_is_bound_to_its_plan(workspace, tmp_path):
    workspace, config = workspace
    plan = plan_for(workspace, config)
    path = tmp_path / "bound"
    review.open_run(path, plan, dict(created_at="x"))
    (path / "inputs.json").unlink()  # a crash after the manifest: the plan files are restored
    review.open_run(path, plan)
    assert (path / "inputs.json").is_file()
    with pytest.raises(ValueError, match="新目录"):
        review.open_run(path, plan_for(workspace, config, seed=8))
    other = tmp_path / "other"
    other.mkdir()
    (other / "note.txt").write_text("x")
    with pytest.raises(ValueError, match="拒绝覆盖"):
        review.open_run(other, plan)


# ---- metrics -----------------------------------------------------------------------------


def test_cohen_kappa():
    pairs = [("pass", "pass")] * 20 + [("revise", "revise")] * 5 + [("pass", "revise")] * 2
    pairs += [("reject", "reject")] * 2 + [("revise", "pass")]
    observed = 27 / 30
    a = Counter(x for x, _ in pairs)
    b = Counter(y for _, y in pairs)
    expected = sum(a[c] * b[c] for c in review.VERDICTS) / 900
    assert review.cohen_kappa(pairs) == round((observed - expected) / (1 - expected), 4)
    assert review.cohen_kappa([("pass", "pass")] * 5) is None  # chance agreement is total
    assert review.cohen_kappa([]) is None


async def test_merge_metrics_and_queue(workspace, tmp_path):
    workspace, config = workspace
    plan, run, roles, reviewers, _ = await complete_run(workspace, config, tmp_path / "run")
    summary = review.merge(run, plan, roles)
    values, gates = summary["metrics"], summary["gates"]
    assert summary["planted"] == len(plan["planted"]) == 5
    assert values["detection"] == {"reviewer_a": 1.0, "reviewer_b": 1.0}
    assert values["detection_merged"] == 1.0
    assert values["rerun"]["reviewer_a"] == 1.0
    assert values["rerun"]["reviewer_b"] < 1.0  # the_star:upright changed its verdict
    assert values["kappa"] is not None and values["kappa"] < 1.0
    merged = json.loads((run.path / "merged.json").read_text(encoding="utf-8"))
    approved = {i.split(":", 3)[3] for i in merged["approved_ids"]}
    queue = json.loads((run.path / "revision_queue.json").read_text(encoding="utf-8"))
    queued = {q["id"].split(":", 3)[3] for q in queue}
    assert DOUBTFUL | {"the_star:upright"} == queued  # any non-pass verdict queues an entry
    assert approved == {i.split(":", 3)[3] for i in IDS} - queued
    assert not gates["pass_rate"]  # 17/20 < 95%
    assert summary["human_reviewed_rate"] == 0.0


def test_metrics_rules_on_hand_written_verdicts(workspace):
    workspace, config = workspace
    plan = plan_for(workspace, config, passes=2)
    real = [e["id"] for e in plan["entries"]]
    planted = [p["ref"] for p in plan["planted"]]

    def table(default="pass", **special):
        return {r: dict(verdict=special.get(r, default)) for r in real + planted}

    flagged = {p: "revise" for p in planted}
    verdicts = {
        ("reviewer_a", 1): table(**flagged),
        ("reviewer_b", 1): table(**flagged, **{real[0]: "revise"}),
        ("reviewer_a", 2): table(**flagged),
        ("reviewer_b", 2): {k: v for k, v in table(**flagged).items() if k != real[1]},
    }
    plan["checks"] = [dict(id=real[2], check="certainty", detail="x")]
    result = review.metrics(plan, verdicts)
    assert real[0] in result["queued"]  # one reviewer's revise is enough
    assert real[2] in result["queued"]  # a blocking code finding overrides two passes
    assert real[1] in result["incomplete"]  # a missing rerun verdict is not an approval
    assert not result["gates"]["complete"] and not result["calibrated"]


# ---- revise, apply, ledger ---------------------------------------------------------------


async def test_ledger_needs_calibration_and_current_content(workspace, tmp_path):
    workspace, config = workspace
    entries = real_entries(workspace)
    # A reviewer that misses most planted errors makes the run uncalibrated.
    blind = dict(
        reviewer_a=Reviewer(entries, "a"),
        reviewer_b=Reviewer(
            entries, "b", misses={"flip_signs", "fatalistic", "medical", "swap_orientation"}
        ),
    )
    plan, run, roles, _, _ = await complete_run(workspace, config, tmp_path / "blind", blind)
    review.merge(run, plan, roles)
    with pytest.raises(ValueError, match="不能记为模型交叉审核"):
        review.record_ledger(workspace, [run.path], root=tmp_path)
    good = dict(reviewer_a=Reviewer(entries, "a"), reviewer_b=Reviewer(entries, "b"))
    plan, run, roles, _, _ = await complete_run(workspace, config, tmp_path / "good", good)
    summary = review.merge(run, plan, roles)
    assert summary["calibrated"] and summary["metrics"]["kappa"] == 1.0
    # Edit one approved entry after the run: its approval must not be recorded.
    path = workspace.sources / "tarot/cards.yaml"
    source = yaml.safe_load(path.read_text(encoding="utf-8"))
    edited = next(e for e in source["entries"] if e["key"] == "the_sun:upright")
    edited["text"] += "补充一句。"
    path.write_text(yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8")
    result = review.record_ledger(workspace, [run.path], root=tmp_path)
    assert result == dict(written={"tarot": 17}, stale=["kb:tarot:card:the_sun:upright"])
    ledger = yaml.safe_load((workspace.reviews / "tarot.yaml").read_text(encoding="utf-8"))
    record = ledger["records"][0]
    assert {r["vendor"] for r in record["reviewers"]} == {"vendor-a", "vendor-b"}
    assert {r["returned_model"] for r in record["reviewers"]} == {"model-a-2026", "model-b-2026"}
    assert record["report"] == "good/report.md"
    report = build(
        workspace.sources, tmp_path / "data/kb.sqlite", workspace.rules, workspace.reviews
    )
    counts = report["partitions"]["tarot"]["review_status"]["counts"]
    assert counts == {"draft": 146, "model_reviewed": 17, "human_reviewed": 0}
    assert report["reviewed_rate"] == 0
    kb = KnowledgeBase(tmp_path / "data/kb.sqlite")
    try:
        assert kb.lookup("tarot", "card", "the_sun:upright")["review_status"] == "draft"
        assert kb.lookup("tarot", "card", "the_fool:upright")["review_status"] == "model_reviewed"
        assert kb.lookup("tarot", "card", "the_tower:upright")["review_status"] == "draft"
    finally:
        kb.close()


async def test_revisions_are_proposals_that_need_a_new_review(workspace, tmp_path):
    workspace, config = workspace
    plan, run, roles, _, _ = await complete_run(workspace, config, tmp_path / "run")
    review.merge(run, plan, roles)
    replies = {
        "the_tower:upright": dict(text="高塔正位提示结构需要调整，先检查最脆弱的环节。",
            theme_map=dict(self=-0.4), synonyms=["高塔:正位"], keywords=["变动"], note="缓和措辞"),
        "death:reversed": dict(text="死神逆位提示改变被拖延，你注定无法摆脱。",
            theme_map=dict(self=-0.2), synonyms=["死神:逆位"], keywords=["拖延"], note="x"),
        "the_star:upright": dict(text="星星正位提示恢复信心，可以设定小目标。",
            theme_map=dict(self=0.3), synonyms=["星星:正位"], keywords=["希望"], note="y"),
    }  # fmt: skip
    seen = []

    class Reviser:
        async def chat(self, messages, tools):
            key = json.loads(messages[-1]["content"])["entry"]["key"]
            seen.append(json.loads(messages[-1]["content"]))
            return ModelResponse(text=json.dumps(replies[key], ensure_ascii=False), model="c-1")

    proposals = await review.revise(run, plan, roles, make_model=lambda r, s: Reviser())
    invalid = {p["id"].split(":", 3)[3]: p["invalid"] for p in proposals}
    assert invalid["death:reversed"] and "注定" in invalid["death:reversed"]
    assert invalid["the_tower:upright"] is None
    # The reviser sees the reviewers' issues, never which of them is which vendor.
    assert all("vendor" not in json.dumps(m) for m in seen) and seen[0]["issues"]
    applied = review.apply_revisions(workspace, run)
    assert applied == ["kb:tarot:card:the_star:upright", "kb:tarot:card:the_tower:upright"]
    source = {e["key"]: e for e in review.load_entries(workspace.sources, "tarot")}
    assert source["the_tower:upright"]["version"] == 2
    assert source["the_tower:upright"]["reviewed"] is False
    # A revision is never an approval: the ledger is untouched and the entries stay drafts.
    assert not (workspace.reviews / "tarot.yaml").exists()
    with pytest.raises(ValueError, match="已在修改建议之后变化"):
        review.apply_revisions(workspace, run)


# ---- adapters and command line -------------------------------------------------------------


async def test_role_adapters_use_their_own_key_and_endpoint(monkeypatch):
    received = []

    def respond(request):
        received.append((request.url.host, request.headers, json.loads(request.content)))
        return httpx.Response(
            200,
            json={
                "id": "msg",
                "type": "message",
                "role": "assistant",
                "model": "model-b-2026",
                "content": [{"type": "text", "text": "{}"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    monkeypatch.setenv("TEST_REVIEW_B_KEY", "role-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    spec = review.RoleConfig.model_validate(dict(ROLES["reviewer_b"], temperature=0))
    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    model = review.role_model(spec, 10, http_client=client)
    try:
        response = await model.chat([dict(role="user", content="x")], [])
    finally:
        await model.close()
    host, headers, body = received[0]
    assert host == "b.test" and headers["x-api-key"] == "role-key"
    assert "tools" not in body and body["temperature"] == 0 and body["max_tokens"] == 4096
    assert response.model == "model-b-2026"
    monkeypatch.delenv("TEST_REVIEW_A_KEY", raising=False)
    with pytest.raises(ValueError, match="TEST_REVIEW_A_KEY"):
        review.role_model(review.RoleConfig.model_validate(ROLES["reviewer_a"]))


def test_plan_command_calls_no_model(capsys):
    output = review.main(["plan", "--system", "daily"])
    assert output["entries"] == 9 and output["planted"] == 5  # minimum for a detection rate
    assert json.loads(capsys.readouterr().out)["system"] == "daily"


# ---- review findings on the first draft PR --------------------------------------------------


@pytest.mark.parametrize("count", [1, 2, 6])
async def test_small_re_review_gives_planted_copies_their_own_batch(workspace, tmp_path, count):
    """Re-reviewing a few revised entries: every batch holds the originals, so the copies
    get a batch of their own instead of crashing the plan."""
    workspace, config = workspace
    ids = IDS[:count]
    plan = review.prepare(workspace, config, "tarot", only_ids=ids)  # default size and rate
    assert len(plan["planted"]) == min(count, 5)  # five, but at most one copy per entry
    originals = {p["ref"]: p["original"] for p in plan["planted"]}
    for batch in plan["batches"]:
        refs = {i["ref"] for i in batch["items"]}
        assert not any(originals[r] in refs for r in refs if r in originals)
    *_, result = await complete_run(
        workspace, config, tmp_path / f"small-{count}", only_ids=ids, plant_rate=0.1, batch_size=10
    )
    assert result["cached"] == result["expected"] and not result["failed"]


def test_pass_with_listed_issues_is_a_parse_error():
    batch = dict(batch="b001", items=[dict(item="i01", ref="x")])

    def reply(verdict, issues):
        return json.dumps(dict(items=[dict(item="i01", verdict=verdict, issues=issues)]))

    with pytest.raises(ValueError, match="自相矛盾"):
        review.parse_verdicts(reply("pass", [dict(dimension="medical", detail="医疗断言")]), batch)
    assert review.parse_verdicts(reply("pass", []), batch)["i01"]["verdict"] == "pass"
    assert review.parse_verdicts(reply("revise", ["x"]), batch)["i01"]["issues"] == [
        dict(detail="x")
    ]


async def test_a_reported_problem_never_becomes_an_approval(workspace, tmp_path):
    workspace, config = workspace
    entries = real_entries(workspace)
    # Both vendors answer "pass" for this entry while listing a medical claim, on every try.
    reviewers = {
        role: Reviewer(entries, role, contradict={"the_sun:upright"}) for role in review.REVIEWERS
    }
    plan, run, roles, _, result = await complete_run(
        workspace, config, tmp_path / "contradict", reviewers
    )
    errors = [e for e in run.errors() if e["kind"] == "parse_error"]
    assert errors and all("自相矛盾" in e["message"] for e in errors)
    assert result["failed"]  # those calls stay open for a resume, not counted as verdicts
    summary = review.merge(run, plan, roles)
    merged = json.loads((run.path / "merged.json").read_text(encoding="utf-8"))
    assert "kb:tarot:card:the_sun:upright" not in merged["approved_ids"]
    assert "kb:tarot:card:the_sun:upright" in summary["incomplete"]
    with pytest.raises(ValueError, match="不能记为模型交叉审核"):
        review.record_ledger(workspace, [run.path], root=tmp_path)
    assert not (workspace.reviews / "tarot.yaml").exists()


async def test_rerun_of_revise_asks_again_for_invalid_proposals_only(workspace, tmp_path):
    workspace, config = workspace
    plan, run, roles, _, _ = await complete_run(workspace, config, tmp_path / "revise-again")
    review.merge(run, plan, roles)
    replies = {
        "the_tower:upright": [dict(text="高塔正位提示结构需要调整，先检查最脆弱的环节。",
            theme_map=dict(self=-0.4), synonyms=["高塔:正位"], keywords=["变动"])],
        "death:reversed": [
            dict(text="死神逆位提示改变被拖延，你注定无法摆脱。", theme_map=dict(self=-0.2),
                 synonyms=["死神:逆位"], keywords=["拖延"]),
            dict(text="死神逆位提示改变被拖延，可以先放下一件旧事。", theme_map=dict(self=-0.2),
                 synonyms=["死神:逆位"], keywords=["拖延"]),
        ],
        "the_star:upright": [dict(text="星星正位提示恢复信心，可以设定小目标。",
            theme_map=dict(self=0.3), synonyms=["星星:正位"], keywords=["希望"])],
    }  # fmt: skip
    asked = []

    class Reviser:
        async def chat(self, messages, tools):
            key = json.loads(messages[-1]["content"])["entry"]["key"]
            asked.append(key)
            reply = replies[key].pop(0)
            return ModelResponse(text=json.dumps(reply, ensure_ascii=False), model="c-1")

    first = await review.revise(run, plan, roles, make_model=lambda r, s: Reviser())
    assert [p["id"] for p in first if p["invalid"]] == ["kb:tarot:card:death:reversed"]
    asked.clear()
    second = await review.revise(run, plan, roles, make_model=lambda r, s: Reviser())
    assert asked == ["death:reversed"]  # valid proposals are not asked for again
    assert all(p["invalid"] is None for p in second)
    death = next(p for p in second if p["id"].endswith("death:reversed"))
    assert [old["invalid"] for old in death["previous_invalid"]] == ["修改稿含确定性说法“注定”"]
    assert len(review.apply_revisions(workspace, run)) == 3


# ---- borrowed calibration (follow-up to the review) ---------------------------------------

MISS_ALL = {"flip_signs", "swap_orientation", "fatalistic", "medical", "foreign_text"}
SMALL = dict(only_ids=IDS[:2], calibrated_by="main", plant_rate=0.1, batch_size=10)


async def calibrated_main(workspace, config, tmp_path):
    entries = real_entries(workspace)
    good = dict(reviewer_a=Reviewer(entries, "a"), reviewer_b=Reviewer(entries, "b"))
    plan, run, roles, _, _ = await complete_run(workspace, config, tmp_path / "main", good)
    assert review.merge(run, plan, roles)["calibrated"]
    return entries


@pytest.mark.parametrize(
    "missed_by_a, missed_by_b, allowed",
    [
        (set(), set(), True),
        (MISS_ALL, set(), True),  # one vendor flagging every copy is enough
        ("first", "first", False),  # one copy passed by both vendors
        (MISS_ALL, MISS_ALL, False),
    ],
)
async def test_borrowed_calibration_needs_every_planted_copy_flagged(
    workspace, tmp_path, missed_by_a, missed_by_b, allowed
):
    workspace, config = workspace
    entries = await calibrated_main(workspace, config, tmp_path)
    first = plan_for(workspace, config, **SMALL)["planted"][0]["mutation"]

    def misses(value):
        return {first} if value == "first" else value

    reviewers = dict(
        reviewer_a=Reviewer(entries, "a", misses=misses(missed_by_a)),
        reviewer_b=Reviewer(entries, "b", misses=misses(missed_by_b)),
    )
    plan, run, roles, _, _ = await complete_run(
        workspace, config, tmp_path / "small", reviewers, **SMALL
    )
    assert not review.merge(run, plan, roles)["calibrated"]  # too few items to calibrate
    if allowed:
        result = review.record_ledger(workspace, [run.path], root=tmp_path)
        assert result == dict(written={"tarot": 2}, stale=[])
    else:
        with pytest.raises(ValueError, match="全部埋错"):
            review.record_ledger(workspace, [run.path], root=tmp_path)
        assert not (workspace.reviews / "tarot.yaml").exists()


async def test_ledger_refuses_an_empty_run_and_skips_one_with_nothing_approved(workspace, tmp_path):
    workspace, config = workspace
    entries = await calibrated_main(workspace, config, tmp_path)
    plan = plan_for(workspace, config, **SMALL)
    empty = review.open_run(tmp_path / "empty", plan, dict(created_at="x"))
    review.merge(empty, plan, review.load_roles(config))
    # No call finished: a refusal that names the reason, not a crash in min().
    with pytest.raises(ValueError, match="全部埋错"):
        review.record_ledger(workspace, [empty.path], root=tmp_path)
    doubtful = [f"kb:tarot:card:{key}" for key in sorted(DOUBTFUL)]
    good = dict(reviewer_a=Reviewer(entries, "a"), reviewer_b=Reviewer(entries, "b"))
    plan, run, roles, _, _ = await complete_run(
        workspace, config, tmp_path / "queued", good, **dict(SMALL, only_ids=doubtful)
    )
    review.merge(run, plan, roles)
    assert review.record_ledger(workspace, [run.path], root=tmp_path) == dict(written={}, stale=[])
    # Nothing approved: no ledger file, so the knowledge version does not change.
    assert not (workspace.reviews / "tarot.yaml").exists()
