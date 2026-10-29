"""ZhiMing server monitor and alert dispatcher. Standard library only; runs as a systemd timer.

Checks the site (local and public health), the TLS certificate's expiry, disk space, the
latest backup, systemd services and timers, clock sync, and, through the app's token-protected
metrics endpoint, the model error rate, today's spend against the budget, auto-pauses and
spend spikes, and whether those metrics can be collected at all. Problems are sent once when
they start, again when they get worse, as a reminder every few hours while they last, and once
when they recover; each channel is tracked separately and retried until it accepts the news.

Usage (root; settings come from /etc/zhiming/monitor.env, read by the systemd unit and by the
script itself, so a manual run matches the timer's; ``--env`` names another file):
    python3 -I monitor.py               # one round: check, alert, write status.json
    python3 -I monitor.py --dry-run     # print the checks; no alerts, no state
    python3 -I monitor.py --test-alert  # send a test message through every channel
    python3 -I monitor.py --external https://zhiming.mom   # off-server probe (CI)

Channels (environment): ZHIMING_ALERT_WEBHOOK_URL with ZHIMING_ALERT_WEBHOOK_KIND
(generic | wecom | dingtalk | feishu | slack) and optional ZHIMING_ALERT_WEBHOOK_SECRET;
ZHIMING_ALERT_SERVERCHAN_KEY; ZHIMING_ALERT_SMTP_HOST/_PORT/_USER/_PASSWORD/_FROM/_TO.
ZHIMING_MONITOR_HEARTBEAT_URL is fetched after every completed round (dead man's switch).
Never prints secrets or response bodies from the channels.
"""

from __future__ import annotations

import argparse
import base64
import glob
import hashlib
import hmac
import json
import os
import shutil
import smtplib
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

RANK = {"ok": 0, "unknown": 0, "warning": 1, "critical": 2}
LABEL = {"ok": "正常", "unknown": "未知", "warning": "警告", "critical": "严重"}
ICON = {"ok": "✓", "unknown": "?", "warning": "!", "critical": "✕"}
BEIJING = timezone(timedelta(hours=8))
USER_AGENT = "zhiming-monitor/1"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def number(name: str, default: float) -> float:
    try:
        return float(env(name, str(default)))
    except ValueError:
        return default


def check(name: str, label: str, level: str, summary: str) -> dict:
    return {"name": name, "label": label, "level": level, "summary": summary}


def beijing(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, BEIJING).strftime("%Y-%m-%d %H:%M")


# ---------- probes ----------


def fetch(url: str, *, token: str | None = None, timeout: float = 15) -> tuple[int, bytes, float]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    started = time.monotonic()
    # Loopback probes never go through a proxy configured for outbound traffic.
    local = urllib.parse.urlsplit(url).hostname in ("127.0.0.1", "localhost", "::1")
    opener = (
        urllib.request.build_opener(urllib.request.ProxyHandler({}))
        if local
        else urllib.request.build_opener()
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(1024 * 1024)
            return response.status, body, time.monotonic() - started
    except urllib.error.HTTPError as exc:
        return exc.code, b"", time.monotonic() - started


def check_health(name: str, label: str, base: str, slow_s: float = 5) -> dict:
    url = base.rstrip("/") + "/healthz"
    try:
        status, body, elapsed = fetch(url)
    except (OSError, ValueError) as exc:
        return check(name, label, "critical", f"{url} 无法访问：{type(exc).__name__}")
    try:
        healthy = status == 200 and json.loads(body).get("status") == "ok"
    except ValueError:
        healthy = False
    if not healthy:
        return check(name, label, "critical", f"{url} 返回 {status}")
    level = "warning" if elapsed > slow_s else "ok"
    return check(name, label, level, f"{status} · {elapsed * 1000:.0f} ms")


def check_page(name: str, label: str, url: str) -> dict:
    """The entrance page itself, so a broken static file or proxy rule is noticed too."""
    try:
        status, body, elapsed = fetch(url)
    except (OSError, ValueError) as exc:
        return check(name, label, "critical", f"{url} 无法访问：{type(exc).__name__}")
    if status != 200 or "知命".encode() not in body:
        return check(name, label, "critical", f"{url} 返回 {status} 或内容异常")
    return check(name, label, "ok", f"{status} · {elapsed * 1000:.0f} ms")


def certificate_expiry(host: str, port: int = 443, timeout: float = 15) -> float:
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            return ssl.cert_time_to_seconds(tls.getpeercert()["notAfter"])


def check_certificate(base: str, now: float) -> dict:
    parsed = urllib.parse.urlsplit(base)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not host:
        return check("tls", "证书到期", "unknown", "未配置 HTTPS 地址")
    try:
        expires = certificate_expiry(host, parsed.port or 443)
    except ssl.SSLCertVerificationError as exc:
        return check("tls", "证书到期", "critical", f"{host} 证书校验失败：{exc.verify_message}")
    except (OSError, ValueError) as exc:
        return check(
            "tls", "证书到期", "critical", f"{host}:443 TLS 握手失败：{type(exc).__name__}"
        )
    days = (expires - now) / 86400
    warn = number("ZHIMING_MONITOR_CERT_WARN_DAYS", 21)
    crit = number("ZHIMING_MONITOR_CERT_CRIT_DAYS", 7)
    level = "critical" if days < crit else "warning" if days < warn else "ok"
    summary = f"{host} 证书 {days:.0f} 天后到期（{beijing(expires)}）"
    if level != "ok":
        summary += "；请确认 certbot 续期可连接正式 ACME 接口"
    return check("tls", "证书到期", level, summary)


def check_disk(paths: list[str]) -> dict:
    warn_pct = number("ZHIMING_MONITOR_DISK_WARN_PCT", 15)
    crit_pct = number("ZHIMING_MONITOR_DISK_CRIT_PCT", 8)
    warn_gb = number("ZHIMING_MONITOR_DISK_WARN_GB", 2)
    crit_gb = number("ZHIMING_MONITOR_DISK_CRIT_GB", 1)
    seen, parts, worst = set(), [], "ok"
    for path in paths:
        try:
            device = os.stat(path).st_dev
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        if device in seen:
            continue
        seen.add(device)
        free_gb = usage.free / 1024**3
        percent = 100 * usage.free / usage.total if usage.total else 0
        level = (
            "critical"
            if percent < crit_pct or free_gb < crit_gb
            else "warning"
            if percent < warn_pct or free_gb < warn_gb
            else "ok"
        )
        worst = max(worst, level, key=RANK.get)
        parts.append(f"{path} 可用 {free_gb:.1f} GiB（{percent:.0f}%）")
    if not parts:
        return check("disk", "磁盘空间", "critical", "无法读取任何磁盘信息，磁盘监控失效")
    return check("disk", "磁盘空间", worst, "；".join(parts))


def systemctl(*args: str) -> str | None:
    if shutil.which("systemctl") is None:
        return None
    try:
        result = subprocess.run(
            ["systemctl", *args], capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def verify_checksum(archive: str) -> str | None:
    """Compare the archive with its ``.sha256`` file; returns a problem, or None if it matches."""
    try:
        with open(archive + ".sha256", encoding="ascii") as stream:
            recorded = stream.read(4096).split()
    except FileNotFoundError:
        return "missing"
    except (OSError, UnicodeDecodeError):
        return "malformed"
    if len(recorded) != 2 or recorded[1] != os.path.basename(archive):
        return "malformed"
    if len(recorded[0]) != 64 or any(c not in "0123456789abcdef" for c in recorded[0]):
        return "malformed"
    digest = hashlib.sha256()
    with open(archive, "rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return None if hmac.compare_digest(digest.hexdigest(), recorded[0]) else "mismatch"


def check_backup(directory: str, now: float, state: dict | None = None) -> dict:
    """The newest completed archive is recent, intact (its SHA256 recomputed) and non-trivial.

    A hash is only recomputed when the archive changes; the result is cached in ``state``.
    """
    state = {} if state is None else state
    max_age = number("ZHIMING_MONITOR_BACKUP_MAX_AGE_H", 26)
    problems, level = [], "ok"
    result = systemctl("show", "zhiming-backup.service", "-p", "Result", "--value")
    if result and result != "success":
        problems.append(f"zhiming-backup.service 最近一次结果为 {result}")
        level = "critical"
    if not os.access(directory, os.R_OK | os.X_OK):
        # Unreadable means the monitor itself is misconfigured: backups are no longer watched.
        problems.append(f"无法读取 {directory}，备份监控失效（监控需以 root 运行）")
        return check("backup", "备份", "critical", "；".join(problems))
    archives = sorted(
        (p for p in glob.glob(os.path.join(directory, "zhiming-*.tar.gz")) if os.path.isfile(p)),
        key=os.path.getmtime,
        reverse=True,
    )
    # The checksum is written right after the archive: a fresh archive without one is still
    # being finished, so judge the previous completed archive instead.
    if (
        len(archives) > 1
        and not os.path.exists(archives[0] + ".sha256")
        and now - os.path.getmtime(archives[0]) < 900
    ):
        archives = archives[1:]
    if not archives:
        problems.append(f"{directory} 中没有备份")
        return check("backup", "备份", "critical", "；".join(problems))
    latest = archives[0]
    stat = os.stat(latest)
    age_h = (now - stat.st_mtime) / 3600
    if age_h > max_age:
        problems.append(f"最近备份已 {age_h:.0f} 小时（超过 {max_age:.0f} 小时）")
        level = "critical"
    if stat.st_size < 1024:
        problems.append("最近备份小于 1 KiB")
        level = "critical"
    # The verdict depends on both files: a checksum written, repaired, damaged or removed later
    # must be noticed even when the archive itself is unchanged.
    try:
        digest = os.stat(latest + ".sha256")
        recorded = [digest.st_size, digest.st_mtime_ns]
    except OSError:
        recorded = None
    identity = [latest, stat.st_size, stat.st_mtime_ns, recorded]
    cached = state.get("backup_verified")
    if cached and cached.get("identity") == identity:
        verdict = cached.get("verdict")
    else:
        try:
            verdict = verify_checksum(latest)
        except OSError:
            verdict = "unreadable"
        if verdict in ("missing", "unreadable"):
            # Possibly transient (a checksum still being written): decide again next round.
            state.pop("backup_verified", None)
        else:
            state["backup_verified"] = {"identity": identity, "verdict": verdict}
    if verdict == "missing":
        problems.append("最近备份缺少 SHA256 校验文件")
        level = max(level, "warning", key=RANK.get)
    elif verdict is not None:
        problems.append(
            {
                "malformed": "最近备份的 SHA256 校验文件格式错误",
                "mismatch": "最近备份的 SHA256 与校验文件不一致，归档可能已损坏",
                "unreadable": "最近备份无法读取",
            }[verdict]
        )
        level = "critical"
    summary = "；".join(problems) or (
        f"{os.path.basename(latest)}，{age_h:.1f} 小时前，"
        f"{stat.st_size / 1024**2:.1f} MiB，SHA256 一致，共 {len(archives)} 份"
    )
    return check("backup", "备份", level, summary)


def check_services(state: dict) -> list[dict]:
    services = [s for s in env("ZHIMING_MONITOR_SERVICES", "zhiming,nginx").split(",") if s]
    timers = [
        t
        for t in env(
            "ZHIMING_MONITOR_TIMERS",
            "zhiming-backup.timer,zhiming-trace-retention.timer,certbot.timer",
        ).split(",")
        if t
    ]
    if systemctl("--version") is None:
        return [
            check("services", "系统服务", "critical", "无法调用 systemctl，服务与定时任务监控失效")
        ]
    down = [s for s in services if systemctl("is-active", s) != "active"]
    checks = [
        check(
            "services",
            "系统服务",
            "critical" if down else "ok",
            f"未运行：{'、'.join(down)}" if down else f"{'、'.join(services)} 运行中",
        )
    ]
    stopped = [t for t in timers if systemctl("is-active", t) != "active"]
    checks.append(
        check(
            "timers",
            "定时任务",
            "warning" if stopped else "ok",
            f"未启用：{'、'.join(stopped)}" if stopped else f"{len(timers)} 个定时任务已启用",
        )
    )
    raw = systemctl("show", "zhiming.service", "-p", "NRestarts", "--value")
    if raw and raw.isdigit():
        count = int(raw)
        previous = state.get("restarts")
        # The counter starts over when the service is restarted by hand.
        delta = count - previous if previous is not None and count >= previous else 0
        state["restarts"] = count
        limit = number("ZHIMING_MONITOR_RESTART_WARN", 3)
        checks.append(
            check(
                "restarts",
                "自动重启",
                "warning" if delta >= limit else "ok",
                f"上次检查以来自动重启 {delta} 次（累计 {count} 次）",
            )
        )
    return checks


def check_clock() -> dict:
    synced = None
    if shutil.which("timedatectl"):
        try:
            synced = subprocess.run(
                ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            synced = None
    if synced is None or synced == "":
        return check("clock", "时间同步", "unknown", "无法读取 NTP 状态")
    if synced != "yes":
        return check(
            "clock", "时间同步", "warning", "系统时钟未与 NTP 同步，证书与日志时间可能出错"
        )
    return check("clock", "时间同步", "ok", "NTP 已同步")


APP_CHECKS = (
    ("model_errors", "模型错误率"),
    ("budget", "今日预算"),
    ("model_pause", "模型暂停"),
    ("spend_spike", "消耗突增"),
    ("suspensions", "账号自动暂停"),
)


def check_app(base: str, token: str, now: float, state: dict | None = None) -> list[dict]:
    """Model and spend checks from the app's metrics, plus one check that the collection itself
    works: without it a wrong token or a broken endpoint would silence every check below."""
    state = {} if state is None else state
    if not token:
        problem = "未配置 ZHIMING_MONITOR_TOKEN"
    else:
        try:
            status, body, _ = fetch(base.rstrip("/") + "/api/ops/metrics", token=token)
            data = json.loads(body) if status == 200 else None
            problem = None if isinstance(data, dict) else f"指标接口返回 {status}"
            checks = app_checks(data, now) if problem is None else []
        except (OSError, ValueError) as exc:
            problem = f"无法访问指标接口：{type(exc).__name__}"
        except (KeyError, TypeError, AttributeError):
            problem = "指标数据格式无法识别（应用与监控版本可能不一致）"
    if problem is None:
        state.pop("metrics_failures", None)
        return [check("app_metrics", "应用指标采集", "ok", "正常"), *checks]
    failures = state.get("metrics_failures", 0) + 1
    state["metrics_failures"] = failures
    needed = int(number("ZHIMING_MONITOR_METRICS_FAILURES", 2))
    # A missing token is a configuration error: no point waiting for a second round.
    confirmed = not token or failures >= needed
    collection = check(
        "app_metrics",
        "应用指标采集",
        "critical" if confirmed else "unknown",
        f"{problem}（连续 {failures} 次）；模型错误率、预算与异常消耗告警已失效"
        if confirmed
        else f"{problem}（第 {failures} 次，下一轮确认）",
    )
    return [
        collection,
        *(check(n, label, "unknown", "应用指标不可用") for n, label in APP_CHECKS),
    ]


def app_checks(data: dict, now: float) -> list[dict]:
    checks = []
    errors = data["errors"]
    rate, calls = errors["rate"], errors["calls"]
    minimum = number("ZHIMING_MONITOR_ERROR_MIN_CALLS", 5)
    level = "ok"
    if calls >= minimum:
        if rate >= number("ZHIMING_MONITOR_ERROR_CRIT", 0.25):
            level = "critical"
        elif rate >= number("ZHIMING_MONITOR_ERROR_WARN", 0.10):
            level = "warning"
    kinds = "，".join(f"{k} ×{v}" for k, v in errors["kinds"].items())
    checks.append(
        check(
            "model_errors",
            "模型错误率",
            level,
            f"近 {errors['window_s'] // 60} 分钟 {errors['errors']}/{calls} 次失败（{rate:.0%}）"
            + (f"：{kinds}" if kinds else ""),
        )
    )
    today = data["today"]
    percent = today["budget_percent"]
    warn = number("ZHIMING_MONITOR_BUDGET_WARN_PCT", 80)
    cost = f"，估算 {today['cost']:.2f} {today['currency']}" if today["priced"] else ""
    refused = today.get("budget_refused_at")
    if refused:
        # Refusals start before 100%: once the rest cannot hold one call's minimum reservation.
        checks.append(
            check(
                "budget",
                "今日预算",
                "critical",
                f"{beijing(refused)} 起已因全站每日预算拒绝模型调用，至次日零点恢复；"
                f"今日 {today['tokens']:,} token{cost}"
                + (f"（{percent:.0f}%）" if percent is not None else "")
                + "；如需恢复服务请在管理页提高预算",
            )
        )
    elif percent is None:
        checks.append(
            check("budget", "今日预算", "ok", f"今日 {today['tokens']:,} token{cost}（未设上限）")
        )
    else:
        level = "critical" if percent >= 100 else "warning" if percent >= warn else "ok"
        checks.append(
            check(
                "budget",
                "今日预算",
                level,
                f"今日已用 {percent:.0f}%：{today['tokens']:,} token{cost}"
                + ("；新的模型调用将被拒绝至次日零点" if percent >= 100 else ""),
            )
        )
    paused = data.get("paused")
    if paused:
        who = "检测到异常消耗自动暂停" if paused.get("auto") else f"{paused.get('by')} 手动暂停"
        checks.append(
            check(
                "model_pause",
                "模型暂停",
                "critical" if paused.get("auto") else "warning",
                f"{who}（{beijing(paused['at'])}）：{paused.get('reason', '')}；在管理页恢复",
            )
        )
    else:
        checks.append(check("model_pause", "模型暂停", "ok", "模型调用正常"))
    hour = data["last_hour"]["tokens"]
    average = data.get("hourly_average_7d") or 0
    factor = number("ZHIMING_MONITOR_SPIKE_FACTOR", 4)
    floor = number("ZHIMING_MONITOR_SPIKE_MIN_TOKENS", 200_000)
    spiking = hour > max(floor, factor * average)
    checks.append(
        check(
            "spend_spike",
            "消耗突增",
            "warning" if spiking else "ok",
            f"近 1 小时 {hour:,} token，7 天小时均值 {average:,}",
        )
    )
    suspended = [e for e in data.get("events", []) if e["kind"] == "account_suspended_auto"]
    checks.append(
        check(
            "suspensions",
            "账号自动暂停",
            "warning" if suspended else "ok",
            f"近 24 小时自动暂停 {len(suspended)} 个账号，请在管理页核实"
            if suspended
            else f"当前暂停的账号 {data.get('suspended_accounts', 0)} 个",
        )
    )
    return checks


# ---------- alert channels ----------


def post_json(url: str, payload: dict, timeout: float = 15) -> bytes:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(64 * 1024)


def send_webhook(title: str, text: str, level: str, checks: list[dict]) -> None:
    url = env("ZHIMING_ALERT_WEBHOOK_URL")
    kind = env("ZHIMING_ALERT_WEBHOOK_KIND", "generic").lower()
    secret = env("ZHIMING_ALERT_WEBHOOK_SECRET")
    content = f"{title}\n{text}"
    if kind == "wecom":
        payload = {"msgtype": "text", "text": {"content": content}}
    elif kind == "dingtalk":
        payload = {"msgtype": "text", "text": {"content": content}}
        if secret:
            stamp = str(int(time.time() * 1000))
            digest = hmac.new(secret.encode(), f"{stamp}\n{secret}".encode(), hashlib.sha256)
            sign = urllib.parse.quote_plus(base64.b64encode(digest.digest()))
            url += ("&" if "?" in url else "?") + f"timestamp={stamp}&sign={sign}"
    elif kind == "feishu":
        payload = {"msg_type": "text", "content": {"text": content}}
        if secret:
            stamp = str(int(time.time()))
            digest = hmac.new(f"{stamp}\n{secret}".encode(), b"", hashlib.sha256).digest()
            payload.update(timestamp=stamp, sign=base64.b64encode(digest).decode())
    elif kind == "slack":
        payload = {"text": content}
    else:
        payload = {
            "title": title,
            "text": text,
            "level": level,
            "host": socket.gethostname(),
            "checks": checks,
        }
    reply = post_json(url, payload)
    if kind in ("wecom", "dingtalk", "feishu"):
        try:
            data = json.loads(reply)
        except ValueError:
            data = {}
        code = data.get("errcode", data.get("code", data.get("StatusCode", 0)))
        if code not in (0, None):
            raise RuntimeError(f"{kind} 返回错误码 {code}")


def send_serverchan(title: str, text: str) -> None:
    key = env("ZHIMING_ALERT_SERVERCHAN_KEY")
    if not key.replace("_", "").isalnum():
        raise ValueError("Server酱 SendKey 格式无效")
    form = urllib.parse.urlencode({"title": title[:32], "desp": text.replace("\n", "\n\n")})
    request = urllib.request.Request(
        f"https://sctapi.ftqq.com/{key}.send",
        data=form.encode(),
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.loads(response.read(64 * 1024) or b"{}")
    if data.get("code", 0) != 0:
        raise RuntimeError(f"Server酱 返回错误码 {data.get('code')}")


def send_email(title: str, text: str) -> None:
    host = env("ZHIMING_ALERT_SMTP_HOST")
    port = int(number("ZHIMING_ALERT_SMTP_PORT", 465))
    recipients = [a.strip() for a in env("ZHIMING_ALERT_SMTP_TO").split(",") if a.strip()]
    sender = env("ZHIMING_ALERT_SMTP_FROM") or env("ZHIMING_ALERT_SMTP_USER")
    if not recipients or not sender:
        raise ValueError("缺少收件人或发件人")
    message = EmailMessage()
    message["Subject"] = title
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(text)
    context = ssl.create_default_context()
    if port == 465:
        client = smtplib.SMTP_SSL(host, port, timeout=20, context=context)
    else:
        client = smtplib.SMTP(host, port, timeout=20)
    with client:
        if port != 465 and env("ZHIMING_ALERT_SMTP_STARTTLS", "1") != "0":
            client.starttls(context=context)
        if env("ZHIMING_ALERT_SMTP_USER"):
            client.login(env("ZHIMING_ALERT_SMTP_USER"), env("ZHIMING_ALERT_SMTP_PASSWORD"))
        client.send_message(message)


def channels() -> dict:
    found = {}
    if env("ZHIMING_ALERT_WEBHOOK_URL"):
        kind = env("ZHIMING_ALERT_WEBHOOK_KIND", "generic").lower()
        name = {"wecom": "企业微信机器人", "dingtalk": "钉钉机器人", "feishu": "飞书机器人"}.get(
            kind, f"Webhook（{kind}）"
        )
        found[name] = lambda title, text, level, checks: send_webhook(title, text, level, checks)
    if env("ZHIMING_ALERT_SERVERCHAN_KEY"):
        found["Server酱"] = lambda title, text, level, checks: send_serverchan(title, text)
    if env("ZHIMING_ALERT_SMTP_HOST"):
        found["邮件"] = lambda title, text, level, checks: send_email(title, text)
    return found


def deliver(title: str, text: str, level: str, checks: list[dict]) -> tuple[list, list]:
    """Send through every channel; returns (succeeded, failed) channel names."""
    succeeded, failed = [], []
    for name, send in channels().items():
        try:
            send(title, text, level, checks)
            succeeded.append(name)
        except Exception as exc:
            # Exception text can echo URLs with keys: report only the type.
            print(f"alert channel {name} failed: {type(exc).__name__}", file=sys.stderr)
            failed.append(f"{name}：{type(exc).__name__}")
    return succeeded, failed


# ---------- state and decisions ----------
#
# Two things are kept apart: what the checks see now (state["checks"]) and, per channel, what
# that channel has been told (state["notified"][channel]). A message is owed whenever the two
# differ in a way that matters; it is only acknowledged after that channel accepted it, so a
# failed escalation, recovery or reminder is simply owed again next round, channel by channel.

JOURNAL = "日志"


def observe(checks: list[dict], state: dict, now: float) -> None:
    """Record what is seen now. A problem is an episode from the round it turns bad (``since``)
    to the round it is seen ok again; ``raised`` is the last round its level went up within the
    episode. "Unknown" (e.g. metrics briefly unreadable) is not a recovery: an open episode
    stays open, at its last known level, until it is seen ok."""
    seen = state.setdefault("checks", {})
    for item in checks:
        previous = seen.get(item["name"])
        was_bad = previous is not None and RANK.get(previous["level"], 0) > 0
        if item["level"] == "unknown" and was_bad:
            item["level"] = previous["level"]
        if RANK[item["level"]] > 0:
            if was_bad and previous.get("since"):
                item["since"] = previous["since"]
                raised = RANK[item["level"]] > RANK[previous["level"]]
                item["raised"] = now if raised else previous.get("raised", previous["since"])
            else:
                item["since"] = item["raised"] = now
        else:
            item["since"] = item["raised"] = None
        seen[item["name"]] = {
            "level": item["level"],
            "since": item["since"],
            "raised": item["raised"],
            "summary": item["summary"],
        }
    for name in [n for n in seen if n not in {c["name"] for c in checks}]:
        seen.pop(name)


def owed(checks: list[dict], told: dict, now: float) -> tuple[list[dict], list[dict]]:
    """What one channel still has to hear: (problems, recoveries).

    A channel is owed a problem when it has not heard of this episode (even if it last heard
    of an earlier one whose recovery never reached it), when the level went up after what it
    heard (also critical → warning → critical), or when its reminder is due; and a recovery
    when the check is ok but the channel last heard of a problem."""
    repeat = number("ZHIMING_MONITOR_REPEAT_HOURS", 6) * 3600
    problems, recoveries = [], []
    for item in checks:
        last = told.get(item["name"])
        if RANK[item["level"]] > 0:
            if last is None or last.get("episode") != item["since"]:
                problems.append({**item, "reason": "new"})
            elif item["raised"] > last.get("raised", item["since"]):
                problems.append({**item, "reason": "worse"})
            elif now - last["at"] >= repeat:
                problems.append({**item, "reason": "repeat"})
        elif item["level"] == "ok" and last is not None:
            recoveries.append(item)
    return problems, recoveries


def acknowledge(told: dict, problems: list[dict], recoveries: list[dict], now: float) -> None:
    for item in problems:
        told[item["name"]] = {
            "level": item["level"],
            "at": now,
            "episode": item["since"],
            "raised": item["raised"],
        }
    for item in recoveries:
        told.pop(item["name"], None)


def compose(problems: list[dict], recoveries: list[dict], host: str) -> tuple[str, str, str]:
    critical = sum(1 for p in problems if p["level"] == "critical")
    warning = sum(1 for p in problems if p["level"] == "warning")
    if problems:
        parts = [f"{critical} 项严重" if critical else "", f"{warning} 项警告" if warning else ""]
        title = f"【知命告警】{'、'.join(p for p in parts if p)}"
        if recoveries:
            title += f"，{len(recoveries)} 项恢复"
    else:
        title = f"【知命恢复】{'、'.join(r['label'] for r in recoveries)}"
    lines = []
    reason = {"new": "", "worse": "（加重）", "repeat": "（仍未解决）"}
    for item in sorted(problems, key=lambda p: -RANK[p["level"]]):
        since = f"，始于 {beijing(item['since'])}" if item.get("since") else ""
        lines.append(
            f"{ICON[item['level']]} {LABEL[item['level']]}{reason[item['reason']]} · "
            f"{item['label']}：{item['summary']}{since}"
        )
    for item in recoveries:
        lines.append(f"✓ 已恢复 · {item['label']}：{item['summary']}")
    lines.append(f"主机 {host} · {beijing(time.time())}（北京时间）")
    level = "critical" if critical else "warning" if warning else "ok"
    return title, "\n".join(lines), level


def load_state(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path: str, data: dict, mode: int) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, mode=0o755, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=directory, prefix=".monitor-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=1)
            stream.write("\n")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def heartbeat() -> None:
    url = env("ZHIMING_MONITOR_HEARTBEAT_URL")
    if not url:
        return
    try:
        fetch(url, timeout=10)
    except (OSError, ValueError) as exc:
        print(f"heartbeat failed: {type(exc).__name__}", file=sys.stderr)


# ---------- rounds ----------


def server_checks(state: dict, now: float) -> list[dict]:
    local = env("ZHIMING_MONITOR_LOCAL_URL", "http://127.0.0.1:8765")
    public = env("ZHIMING_MONITOR_PUBLIC_URL") or env("ZHIMING_PUBLIC_ORIGIN")
    checks = [check_health("site_local", "本机服务", local)]
    if public:
        checks.append(check_health("site_public", "公网访问", public))
        checks.append(check_certificate(public, now))
    checks.append(
        check_disk(
            [
                p
                for p in env(
                    "ZHIMING_MONITOR_DISK_PATHS", "/,/opt/zhiming/data,/var/backups/zhiming"
                ).split(",")
                if p
            ]
        )
    )
    checks.append(
        check_backup(env("ZHIMING_MONITOR_BACKUP_DIR", "/var/backups/zhiming"), now, state)
    )
    checks.extend(check_services(state))
    checks.append(check_clock())
    checks.extend(check_app(local, env("ZHIMING_MONITOR_TOKEN"), now, state))
    return checks


def external_checks(base: str, now: float) -> list[dict]:
    return [
        check_health("site_public", "公网访问", base, slow_s=10),
        check_page("entrance", "入口页面", base.rstrip("/") + "/login"),
        check_certificate(base, now),
    ]


def run(
    checks: list[dict], state: dict, state_path: str | None, status_path: str | None, now: float
) -> int:
    observe(checks, state, now)
    host = env("ZHIMING_MONITOR_HOST") or socket.gethostname()
    targets = channels()
    if not targets:
        # Without any channel the journal is the only record; it is told like a channel, so a
        # problem is logged when it starts, worsens, is due a reminder and recovers.
        targets = {JOURNAL: lambda title, text, level, items: None}
    notified = state.setdefault("notified", {})
    delivery = state.setdefault("delivery", {})
    names = {c["name"] for c in checks}
    for channel, send in targets.items():
        told = notified.setdefault(channel, {})
        for name in [n for n in told if n not in names]:
            told.pop(name)
        problems, recoveries = owed(checks, told, now)
        if not problems and not recoveries:
            continue
        title, text, level = compose(problems, recoveries, host)
        print(f"[{channel}] {title}\n{text}")
        try:
            send(title, text, level, checks)
        except Exception as exc:
            # Exception text can echo URLs with keys: report only the type. Not acknowledged,
            # so the same news is owed to this channel next round.
            print(f"alert channel {channel} failed: {type(exc).__name__}", file=sys.stderr)
            delivery.setdefault(channel, {}).update(
                last_error=type(exc).__name__, last_error_at=now
            )
            continue
        acknowledge(told, problems, recoveries, now)
        delivery[channel] = {"last_ok": now}
    for channel in [c for c in notified if c not in targets]:
        notified.pop(channel)
        delivery.pop(channel, None)
    state["last_run"] = now
    if state_path:
        write_json(state_path, state, 0o600)
    if status_path:
        failing = [f"{c}：{d['last_error']}" for c, d in delivery.items() if d.get("last_error")]
        write_json(
            status_path,
            {
                "generated_at": now,
                "host": host,
                "channels": list(channels()),
                "delivery": {
                    "last_error": "；".join(failing) or None,
                    "channels": delivery,
                },
                "checks": [
                    {k: c.get(k) for k in ("name", "label", "level", "summary", "since")}
                    for c in checks
                ],
            },
            0o644,
        )
    return max((RANK[c["level"]] for c in checks), default=0)


DEFAULT_ENV = "/etc/zhiming/monitor.env"


def load_env(path: str, required: bool = False) -> None:
    """Read KEY=VALUE lines (as systemd's EnvironmentFile does) without overriding variables
    already set, so a manual run behaves like the timer's run."""
    try:
        with open(path, encoding="utf-8") as stream:
            lines = stream.read().splitlines()
    except FileNotFoundError:
        if required:
            raise SystemExit(f"找不到环境文件 {path}") from None
        return
    except PermissionError:
        raise SystemExit(f"无法读取 {path}，请以 root 运行") from None
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key.isidentifier():
            os.environ.setdefault(key, value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="知命服务器监控与告警")
    parser.add_argument("--dry-run", action="store_true", help="只打印检查结果，不发送、不写状态")
    parser.add_argument("--test-alert", action="store_true", help="通过所有渠道发送一条测试消息")
    parser.add_argument("--external", metavar="URL", help="从服务器之外探测公网地址（无状态）")
    parser.add_argument("--state", help="状态文件；--external 时可选，用于去重")
    parser.add_argument(
        "--env",
        help=f"告警渠道与阈值的环境文件（默认存在时读取 {DEFAULT_ENV}；已设置的变量优先）",
    )
    args = parser.parse_args(argv)
    load_env(args.env or DEFAULT_ENV, required=bool(args.env))
    now = time.time()
    if args.test_alert:
        if not channels():
            print("未配置任何告警渠道", file=sys.stderr)
            return 2
        succeeded, failed = deliver(
            "【知命】告警测试",
            f"这是一条测试消息，说明告警渠道可用。\n主机 {socket.gethostname()} · {beijing(now)}",
            "ok",
            [],
        )
        print(f"成功：{'、'.join(succeeded) or '无'}；失败：{'、'.join(failed) or '无'}")
        return 0 if not failed else 1
    if args.external:
        checks = external_checks(args.external, now)
        if args.dry_run:
            print(json.dumps(checks, ensure_ascii=False, indent=1))
            return 0
        return run(checks, load_state(args.state) if args.state else {}, args.state, None, now)
    state_dir = env("ZHIMING_MONITOR_STATE_DIR", "/var/lib/zhiming-monitor")
    state_path = os.path.join(state_dir, "state.json")
    state = load_state(state_path)
    checks = server_checks(state, now)
    if args.dry_run:
        print(json.dumps(checks, ensure_ascii=False, indent=1))
        return 0
    run(checks, state, state_path, os.path.join(state_dir, "status.json"), now)
    heartbeat()
    return 0


if __name__ == "__main__":
    sys.exit(main())
