"""Server monitor: alert decisions, checks and channel payloads, offline."""

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


def test_alerts_fire_on_start_escalation_reminder_and_recovery(monkeypatch):
    monkeypatch.setenv("ZHIMING_MONITOR_REPEAT_HOURS", "6")
    state, now = {}, 1_800_000_000.0
    problems, recoveries = monitor.decide([item("disk", "warning")], state, now)
    assert [p["reason"] for p in problems] == ["new"] and not recoveries
    monitor.mark_sent(problems, state, now)
    # Same level shortly after: silent.
    problems, _ = monitor.decide([item("disk", "warning")], state, now + 300)
    assert problems == []
    # Worse: announced at once.
    problems, _ = monitor.decide([item("disk", "critical")], state, now + 600)
    assert [p["reason"] for p in problems] == ["worse"]
    monitor.mark_sent(problems, state, now + 600)
    assert state["checks"]["disk"]["since"] == now
    # Still bad after the repeat interval: a reminder.
    problems, _ = monitor.decide([item("disk", "critical")], state, now + 600 + 6 * 3600)
    assert [p["reason"] for p in problems] == ["repeat"]
    # Unknown is not a recovery; ok is.
    problems, recoveries = monitor.decide([item("disk", "unknown")], state, now + 7 * 3600)
    assert not problems and not recoveries and state["checks"]["disk"]["level"] == "critical"
    problems, recoveries = monitor.decide([item("disk", "ok")], state, now + 8 * 3600)
    assert [r["name"] for r in recoveries] == ["disk"]
    assert state["checks"]["disk"]["level"] == "ok"


def test_undelivered_alerts_are_retried_next_round(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIMING_ALERT_WEBHOOK_URL", "https://hooks.example/test")
    calls = []

    def failing(url, payload, timeout=15):
        calls.append(payload)
        raise OSError("down")

    monkeypatch.setattr(monitor, "post_json", failing)
    state_path, status_path = str(tmp_path / "state.json"), str(tmp_path / "status.json")
    state = {}
    assert monitor.run([item("backup", "critical")], state, state_path, status_path, 1000.0) == 2
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["delivery"]["last_error"].startswith("Webhook（generic）")
    assert status["checks"][0]["since"] == 1000.0
    assert oct(os.stat(state_path).st_mode & 0o777) == "0o600"
    state = monitor.load_state(state_path)
    monitor.run([item("backup", "critical")], state, state_path, status_path, 1300.0)
    assert len(calls) == 2  # not marked sent, so it is tried again
    monkeypatch.setattr(monitor, "post_json", lambda url, payload, timeout=15: b"{}")
    state = monitor.load_state(state_path)
    monitor.run([item("backup", "critical")], state, state_path, status_path, 1600.0)
    state = monitor.load_state(state_path)
    assert state["checks"]["backup"]["last_sent"] == 1600.0
    assert "last_error" not in state["delivery"]


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


def test_backup_and_disk_checks(tmp_path):
    now = time.time()
    assert monitor.check_backup(str(tmp_path), now)["level"] == "critical"
    archive = tmp_path / "zhiming-20261030T041000Z.tar.gz"
    archive.write_bytes(b"x" * 4096)
    result = monitor.check_backup(str(tmp_path), now)
    assert result["level"] == "warning" and "SHA256" in result["summary"]
    (tmp_path / (archive.name + ".sha256")).write_text("abc  name\n")
    assert monitor.check_backup(str(tmp_path), now)["level"] == "ok"
    old = now - 30 * 3600
    os.utime(archive, (old, old))
    result = monitor.check_backup(str(tmp_path), now)
    assert result["level"] == "critical" and "30 小时" in result["summary"]
    disk = monitor.check_disk([str(tmp_path), str(tmp_path / "missing")])
    assert disk["level"] in ("ok", "warning", "critical") and "可用" in disk["summary"]
    assert monitor.check_disk([str(tmp_path / "missing")])["level"] == "unknown"


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
    assert {c["level"] for c in monitor.check_app("http://local", "", 0)} == {"unknown"}


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
        assert {c["level"] for c in monitor.check_app(base, "w" * 40, 0)} == {"unknown"}
    finally:
        server.should_exit = True
        thread.join(10)
    assert monitor.check_health("site_local", "本机服务", base)["level"] == "critical"
