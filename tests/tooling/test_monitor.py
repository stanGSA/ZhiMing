"""Server monitor: alert decisions, checks and channel payloads, offline."""

import hashlib
import json
import os
import time

import pytest

from ops import monitor


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith(("ZHIMING_ALERT_", "ZHIMING_MONITOR_")):
            monkeypatch.delenv(name)
    monkeypatch.setattr(monitor, "systemctl", lambda *args: None)


def item(name, level, summary="说明"):
    return monitor.check(name, name, level, summary)


class Channels:
    """Stand-in alert channels: records every attempt and fails the names in ``failing``."""

    def __init__(self, *names):
        self.names = names
        self.failing = set()
        self.attempts = {name: [] for name in names}
        self.delivered = {name: [] for name in names}

    def __call__(self):
        return {name: self.sender(name) for name in self.names}

    def sender(self, name):
        def send(title, text, level, checks):
            self.attempts[name].append(title)
            if name in self.failing:
                raise OSError("down")
            self.delivered[name].append(title)

        return send


@pytest.fixture
def channels(monkeypatch):
    fake = Channels("机器人", "邮件")
    monkeypatch.setattr(monitor, "channels", fake)
    return fake


def test_alerts_fire_on_start_escalation_reminder_and_recovery(channels, monkeypatch):
    monkeypatch.setenv("ZHIMING_MONITOR_REPEAT_HOURS", "6")
    state, now = {}, 1_800_000_000.0
    sent = channels.delivered["机器人"]

    def round_(level, at):
        monitor.run([item("disk", level)], state, None, None, at)

    round_("warning", now)
    assert sent == ["【知命告警】1 项警告"]
    round_("warning", now + 300)  # same level shortly after: silent
    assert len(sent) == 1
    round_("critical", now + 600)  # worse: at once
    assert sent[-1] == "【知命告警】1 项严重" and state["checks"]["disk"]["since"] == now
    round_("critical", now + 600 + 6 * 3600)  # still bad after the interval: a reminder
    assert len(sent) == 3
    round_("unknown", now + 7 * 3600)  # unknown is not a recovery
    assert len(sent) == 3 and state["checks"]["disk"]["level"] == "critical"
    round_("ok", now + 8 * 3600)
    assert sent[-1] == "【知命恢复】disk" and len(sent) == 4
    round_("ok", now + 9 * 3600)
    assert len(sent) == 4
    assert channels.delivered["邮件"] == sent


def test_a_failed_escalation_is_retried_next_round(channels):
    state = {}
    monitor.run([item("disk", "warning")], state, None, None, 1000.0)
    channels.failing.add("机器人")
    monitor.run([item("disk", "critical")], state, None, None, 1300.0)
    monitor.run([item("disk", "critical")], state, None, None, 1600.0)
    assert channels.attempts["机器人"][1:] == ["【知命告警】1 项严重"] * 2
    channels.failing.clear()
    monitor.run([item("disk", "critical")], state, None, None, 1900.0)
    monitor.run([item("disk", "critical")], state, None, None, 2200.0)
    assert channels.delivered["机器人"] == ["【知命告警】1 项警告", "【知命告警】1 项严重"]


def test_a_failed_recovery_is_retried_next_round(channels):
    state = {}
    monitor.run([item("disk", "warning")], state, None, None, 1000.0)
    channels.failing.add("机器人")
    monitor.run([item("disk", "ok")], state, None, None, 1300.0)
    monitor.run([item("disk", "ok")], state, None, None, 1600.0)
    assert channels.attempts["机器人"][1:] == ["【知命恢复】disk"] * 2
    channels.failing.clear()
    monitor.run([item("disk", "ok")], state, None, None, 1900.0)
    monitor.run([item("disk", "ok")], state, None, None, 2200.0)
    assert channels.delivered["机器人"] == ["【知命告警】1 项警告", "【知命恢复】disk"]


def test_a_new_episode_after_an_undelivered_recovery_is_announced(channels):
    state = {}
    monitor.run([item("disk", "critical")], state, None, None, 1000.0)
    channels.failing.add("机器人")
    monitor.run([item("disk", "ok")], state, None, None, 1300.0)  # recovery not delivered
    channels.failing.clear()
    monitor.run([item("disk", "critical")], state, None, None, 1600.0)  # a new failure
    monitor.run([item("disk", "critical")], state, None, None, 1900.0)
    assert channels.attempts["机器人"] == [
        "【知命告警】1 项严重",
        "【知命恢复】disk",
        "【知命告警】1 项严重",
    ]
    assert state["notified"]["机器人"]["disk"]["episode"] == 1600.0
    # The mail channel heard every change in order.
    assert channels.delivered["邮件"] == channels.attempts["机器人"][:1] + [
        "【知命恢复】disk",
        "【知命告警】1 项严重",
    ]


def test_falling_back_and_rising_again_is_announced_as_worse(channels):
    state = {}
    monitor.run([item("disk", "critical")], state, None, None, 1000.0)
    monitor.run([item("disk", "warning")], state, None, None, 1300.0)  # milder: no message
    monitor.run([item("disk", "critical")], state, None, None, 1600.0)
    monitor.run([item("disk", "critical")], state, None, None, 1900.0)
    assert channels.delivered["机器人"] == ["【知命告警】1 项严重", "【知命告警】1 项严重"]
    assert state["checks"]["disk"] == {
        "level": "critical",
        "since": 1000.0,
        "raised": 1600.0,
        "summary": "说明",
    }


def test_one_channel_failing_does_not_silence_or_repeat_the_others(channels, tmp_path):
    state, status_path = {}, str(tmp_path / "status.json")
    channels.failing.add("邮件")
    monitor.run([item("backup", "critical")], state, None, status_path, 1000.0)
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["delivery"]["last_error"] == "邮件：OSError"
    monitor.run([item("backup", "critical")], state, None, status_path, 1300.0)
    # The robot already has it: not sent again. The mail is retried every round.
    assert len(channels.attempts["机器人"]) == 1 and len(channels.attempts["邮件"]) == 2
    channels.failing.clear()
    monitor.run([item("backup", "critical")], state, None, status_path, 1600.0)
    monitor.run([item("backup", "critical")], state, None, status_path, 1900.0)
    assert len(channels.delivered["邮件"]) == 1 and len(channels.attempts["机器人"]) == 1
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["delivery"]["last_error"] is None


def test_state_and_status_files_survive_between_rounds(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIMING_ALERT_WEBHOOK_URL", "https://hooks.example/test")
    calls = []

    def failing(url, payload, timeout=15):
        calls.append(payload)
        raise OSError("down")

    monkeypatch.setattr(monitor, "post_json", failing)
    state_path, status_path = str(tmp_path / "state.json"), str(tmp_path / "status.json")
    assert monitor.run([item("backup", "critical")], {}, state_path, status_path, 1000.0) == 2
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["delivery"]["last_error"] == "Webhook（generic）：OSError"
    assert status["checks"][0]["since"] == 1000.0
    if os.name == "posix":  # Windows has no POSIX permission bits to check
        assert os.stat(state_path).st_mode & 0o777 == 0o600
        assert os.stat(status_path).st_mode & 0o777 == 0o644
    monitor.run(
        [item("backup", "critical")], monitor.load_state(state_path), state_path, None, 1300.0
    )
    assert len(calls) == 2
    monkeypatch.setattr(monitor, "post_json", lambda url, payload, timeout=15: b"{}")
    monitor.run(
        [item("backup", "critical")], monitor.load_state(state_path), state_path, None, 1600.0
    )
    state = monitor.load_state(state_path)
    assert state["notified"]["Webhook（generic）"]["backup"] == {
        "level": "critical",
        "at": 1600.0,
        "episode": 1000.0,
        "raised": 1000.0,
    }
    assert state["delivery"]["Webhook（generic）"] == {"last_ok": 1600.0}


def test_env_file_is_read_without_overriding_the_environment(tmp_path, monkeypatch):
    path = tmp_path / "monitor.env"
    path.write_text(
        '# comment\nZHIMING_ALERT_WEBHOOK_URL="https://hooks.example/x"\n'
        "ZHIMING_MONITOR_REPEAT_HOURS=2\nnot a line\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZHIMING_MONITOR_REPEAT_HOURS", "9")
    monitor.load_env(str(path))
    assert os.environ["ZHIMING_ALERT_WEBHOOK_URL"] == "https://hooks.example/x"
    assert os.environ["ZHIMING_MONITOR_REPEAT_HOURS"] == "9"
    monitor.load_env(str(tmp_path / "missing.env"))
    with pytest.raises(SystemExit):
        monitor.load_env(str(tmp_path / "missing.env"), required=True)


def test_without_channels_the_journal_records_each_problem_once(tmp_path, capsys):
    state = {}
    monitor.run([item("tls", "warning", "证书 10 天后到期")], state, None, None, 1000.0)
    assert "【知命告警】1 项警告" in capsys.readouterr().out
    monitor.run([item("tls", "warning", "证书 10 天后到期")], state, None, None, 1300.0)
    assert capsys.readouterr().out == ""


def test_channel_payloads_and_signatures(monkeypatch):
    sent = []
    monkeypatch.setattr(
        monitor, "post_json", lambda url, payload, timeout=15: sent.append((url, payload)) or b""
    )
    monkeypatch.setenv("ZHIMING_ALERT_WEBHOOK_URL", "https://oapi.dingtalk.com/robot/send?t=1")
    monkeypatch.setenv("ZHIMING_ALERT_WEBHOOK_KIND", "dingtalk")
    monkeypatch.setenv("ZHIMING_ALERT_WEBHOOK_SECRET", "SECsecret")
    monitor.send_webhook("标题", "正文", "warning", [])
    url, payload = sent[-1]
    assert "&timestamp=" in url and "&sign=" in url
    assert payload == {"msgtype": "text", "text": {"content": "标题\n正文"}}
    monkeypatch.setenv("ZHIMING_ALERT_WEBHOOK_KIND", "feishu")
    monitor.send_webhook("标题", "正文", "warning", [])
    assert {"timestamp", "sign"} <= set(sent[-1][1]) and sent[-1][1]["msg_type"] == "text"
    monkeypatch.setenv("ZHIMING_ALERT_WEBHOOK_KIND", "wecom")
    monitor.send_webhook("标题", "正文", "warning", [])
    assert sent[-1][1]["msgtype"] == "text"
    monkeypatch.setenv("ZHIMING_ALERT_WEBHOOK_KIND", "generic")
    monitor.send_webhook("标题", "正文", "critical", [item("disk", "critical")])
    assert sent[-1][1]["level"] == "critical" and sent[-1][1]["checks"][0]["name"] == "disk"
    # Robots answer 200 with an error code when, for example, the keyword is wrong.
    monkeypatch.setenv("ZHIMING_ALERT_WEBHOOK_KIND", "wecom")
    monkeypatch.setattr(monitor, "post_json", lambda *a, **k: b'{"errcode": 93000}')
    with pytest.raises(RuntimeError, match="93000"):
        monitor.send_webhook("标题", "正文", "warning", [])
    assert set(monitor.channels()) == {"企业微信机器人"}


def write_backup(directory, name, content=b"x" * 4096, checksum=None, age_h=1.0):
    import hashlib

    archive = directory / name
    archive.write_bytes(content)
    stamp = time.time() - age_h * 3600
    os.utime(archive, (stamp, stamp))
    if checksum is not False:
        digest = checksum or hashlib.sha256(content).hexdigest()
        (directory / (name + ".sha256")).write_text(f"{digest}  {name}\n", encoding="ascii")
    return archive


def test_backup_checksums_are_recomputed_once_per_archive(tmp_path, monkeypatch):
    now = time.time()
    assert monitor.check_backup(str(tmp_path), now)["level"] == "critical"
    archive = write_backup(tmp_path, "zhiming-a.tar.gz", checksum=False, age_h=2)
    result = monitor.check_backup(str(tmp_path), now)
    assert result["level"] == "warning" and "缺少 SHA256" in result["summary"]
    write_backup(tmp_path, "zhiming-a.tar.gz", age_h=2)
    state = {}
    hashed = []
    real = monitor.verify_checksum
    monkeypatch.setattr(monitor, "verify_checksum", lambda path: hashed.append(path) or real(path))
    result = monitor.check_backup(str(tmp_path), now, state)
    assert result["level"] == "ok" and "SHA256 一致" in result["summary"]
    monitor.check_backup(str(tmp_path), now, state)
    assert len(hashed) == 1  # unchanged archive: cached verdict
    # Corrupted after the fact: same size, different bytes, new mtime -> re-hashed, mismatch.
    archive.write_bytes(b"y" * 4096)
    result = monitor.check_backup(str(tmp_path), now, state)
    assert result["level"] == "critical" and "不一致" in result["summary"] and len(hashed) == 2
    write_backup(tmp_path, "zhiming-a.tar.gz", checksum="incorrect-checksum", age_h=2)
    result = monitor.check_backup(str(tmp_path), now, state)
    assert result["level"] == "critical" and "格式错误" in result["summary"]
    # A fresh archive still waiting for its checksum: the previous completed one is judged.
    write_backup(tmp_path, "zhiming-a.tar.gz", age_h=2)
    write_backup(tmp_path, "zhiming-b.tar.gz", checksum=False, age_h=0.01)
    assert monitor.check_backup(str(tmp_path), now, state)["level"] == "ok"
    old = write_backup(tmp_path, "zhiming-a.tar.gz", age_h=30)
    (tmp_path / "zhiming-b.tar.gz").unlink()
    result = monitor.check_backup(str(tmp_path), now, state)
    assert result["level"] == "critical" and "30 小时" in result["summary"]
    assert old.exists()
    # Only the checksum file changes: added, damaged, removed and repaired are all noticed.
    for name in ("zhiming-a.tar.gz", "zhiming-b.tar.gz"):
        for path in (tmp_path / name, tmp_path / (name + ".sha256")):
            path.unlink(missing_ok=True)
    state = {}
    write_backup(tmp_path, "zhiming-c.tar.gz", checksum=False, age_h=2)
    assert monitor.check_backup(str(tmp_path), now, state)["level"] == "warning"
    good = write_backup(tmp_path, "zhiming-c.tar.gz", age_h=2)
    checksum = tmp_path / "zhiming-c.tar.gz.sha256"
    stamp = os.stat(good).st_mtime
    assert monitor.check_backup(str(tmp_path), now, state)["level"] == "ok"
    checksum.write_text("f" * 64 + "  zhiming-c.tar.gz\n", encoding="ascii")
    os.utime(good, (stamp, stamp))
    result = monitor.check_backup(str(tmp_path), now, state)
    assert result["level"] == "critical" and "不一致" in result["summary"]
    checksum.unlink()
    assert monitor.check_backup(str(tmp_path), now, state)["level"] == "warning"
    # Written back without touching the archive (as when it lands right after a check).
    digest = hashlib.sha256(good.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  zhiming-c.tar.gz\n", encoding="ascii")
    assert os.stat(good).st_mtime == stamp
    assert monitor.check_backup(str(tmp_path), now, state)["level"] == "ok"
    # Unreadable backup directory: the watch itself is broken, which is critical.
    monkeypatch.setattr(monitor.os, "access", lambda path, mode: False)
    assert monitor.check_backup(str(tmp_path), now)["level"] == "critical"


def test_disk_check(tmp_path):
    disk = monitor.check_disk([str(tmp_path), str(tmp_path / "missing")])
    assert disk["level"] in ("ok", "warning", "critical") and "可用" in disk["summary"]
    assert monitor.check_disk([str(tmp_path / "missing")])["level"] == "critical"


def metrics(**overrides):
    data = {
        "errors": {"window_s": 1800, "calls": 20, "errors": 1, "rate": 0.05, "kinds": {}},
        "today": {
            "tokens": 1000,
            "cost": 0.5,
            "currency": "CNY",
            "priced": True,
            "budget_percent": 10.0,
        },
        "paused": None,
        "last_hour": {"tokens": 1000},
        "hourly_average_7d": 900,
        "events": [],
        "suspended_accounts": 0,
    }
    data.update(overrides)
    return data


def test_app_metrics_become_model_and_cost_checks(monkeypatch):
    responses = []
    monkeypatch.setattr(
        monitor,
        "fetch",
        lambda url, token=None, timeout=15: (200, json.dumps(responses[-1]).encode(), 0.01),
    )
    responses.append(metrics())
    checks = {c["name"]: c for c in monitor.check_app("http://local", "t" * 40, 0)}
    assert all(c["level"] == "ok" for c in checks.values())
    responses.append(
        metrics(
            errors={
                "window_s": 1800,
                "calls": 10,
                "errors": 4,
                "rate": 0.4,
                "kinds": {"http_500": 4},
            },
            today={
                "tokens": 9,
                "cost": 0,
                "currency": "CNY",
                "priced": False,
                "budget_percent": 100,
            },
            paused={"auto": True, "at": 0, "reason": "突增", "by": "system"},
            last_hour={"tokens": 900_000},
            events=[{"kind": "account_suspended_auto"}],
        )
    )
    checks = {c["name"]: c for c in monitor.check_app("http://local", "t" * 40, 0)}
    assert (
        checks["model_errors"]["level"] == "critical"
        and "http_500" in checks["model_errors"]["summary"]
    )
    assert checks["budget"]["level"] == "critical"
    assert checks["model_pause"]["level"] == "critical"
    assert checks["spend_spike"]["level"] == "warning"
    assert checks["suspensions"]["level"] == "warning"
    # Too few calls for a rate to mean anything.
    responses.append(
        metrics(errors={"window_s": 1800, "calls": 2, "errors": 2, "rate": 1.0, "kinds": {}})
    )
    checks = {c["name"]: c for c in monitor.check_app("http://local", "t" * 40, 0)}
    assert checks["model_errors"]["level"] == "ok"
    # Budget refusals start below 100%: reported as critical from the refusal on.
    responses.append(
        metrics(
            today={
                "tokens": 8900,
                "cost": 0,
                "currency": "CNY",
                "priced": False,
                "budget_percent": 89.0,
                "budget_refused_at": 1_800_000_000,
            }
        )
    )
    checks = {c["name"]: c for c in monitor.check_app("http://local", "t" * 40, 0)}
    assert (
        checks["budget"]["level"] == "critical"
        and "已因全站每日预算拒绝" in (checks["budget"]["summary"])
    )


def test_broken_metrics_collection_is_itself_alerted(monkeypatch, channels):
    replies = [(404, b"", 0.01)]
    monkeypatch.setattr(monitor, "fetch", lambda url, token=None, timeout=15: replies[-1])
    state = {}

    def round_(at):
        checks = monitor.check_app("http://local", "t" * 40, at, state)
        monitor.run(checks, state, None, None, at)
        return {c["name"]: c for c in checks}

    first = round_(1000.0)
    assert first["app_metrics"]["level"] == "unknown"  # one miss may be a restart
    assert not channels.attempts["机器人"]
    second = round_(1300.0)
    assert (
        second["app_metrics"]["level"] == "critical"
        and "已失效" in (second["app_metrics"]["summary"])
    )
    assert channels.delivered["机器人"] == ["【知命告警】1 项严重"]
    replies.append((200, b"not json", 0.01))
    round_(1600.0)
    replies.append((200, json.dumps({"errors": {}}).encode(), 0.01))  # incompatible data
    assert round_(1900.0)["app_metrics"]["level"] == "critical"
    replies.append((200, json.dumps(metrics()).encode(), 0.01))
    assert round_(2200.0)["app_metrics"]["level"] == "ok"
    assert channels.delivered["机器人"][-1] == "【知命恢复】应用指标采集"
    assert "metrics_failures" not in state
    # A missing token is a configuration error: critical at once.
    checks = {c["name"]: c for c in monitor.check_app("http://local", "", 0, {})}
    assert checks["app_metrics"]["level"] == "critical"
    assert {checks[n]["level"] for n, _ in monitor.APP_CHECKS} == {"unknown"}


def test_health_check_against_the_real_app(project):
    import threading

    import uvicorn

    from web import create_web_app

    app = create_web_app(root=project, monitor_token="z" * 40)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        port = server.servers[0].sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        assert monitor.check_health("site_local", "本机服务", base)["level"] == "ok"
        checks = monitor.check_app(base, "z" * 40, time.time())
        assert {c["level"] for c in checks} == {"ok"}
        state = {}
        monitor.check_app(base, "w" * 40, 0, state)
        wrong = {c["name"]: c for c in monitor.check_app(base, "w" * 40, 0, state)}
        assert wrong["app_metrics"]["level"] == "critical"
        assert "404" in wrong["app_metrics"]["summary"]
    finally:
        server.should_exit = True
        thread.join(10)
    assert monitor.check_health("site_local", "本机服务", base)["level"] == "critical"
