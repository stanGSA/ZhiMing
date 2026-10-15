"""Run a password-protected Quick Tunnel. Stop with --stop or Ctrl+C."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "reports" / "web-share"


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        # Windows virtualenv Python may launch a second interpreter. Stop our whole tree.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run(port: int):
    executable = ROOT / ".bootstrap" / "cloudflared.exe"
    cloudflared = str(executable) if executable.exists() else shutil.which("cloudflared")
    if not cloudflared:
        raise RuntimeError("请先安装 cloudflared，或放入 .bootstrap/cloudflared.exe")
    # Do not expose a different service that is already using the selected port.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    stop_file = DIRECTORY / "stop"
    stop_file.unlink(missing_ok=True)
    password = secrets.token_urlsafe(24)
    password_file = DIRECTORY / "password.txt"
    password_file.write_text(password, encoding="utf-8")
    password_file.chmod(0o600)
    state_file = DIRECTORY / "state.json"
    invitation = DIRECTORY / "invitation.txt"
    invitation.unlink(missing_ok=True)
    state = {"running": False, "launcher_pid": os.getpid()}
    state_file.write_text(json.dumps(state), encoding="utf-8")
    processes = []
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        with (
            (DIRECTORY / "tunnel.log").open("w", encoding="utf-8") as tunnel_log,
            (DIRECTORY / "web.log").open("w", encoding="utf-8") as web_log,
        ):
            tunnel = subprocess.Popen(
                [
                    cloudflared,
                    "tunnel",
                    "--no-autoupdate",
                    "--protocol",
                    "http2",
                    "--url",
                    f"http://127.0.0.1:{port}",
                ],
                cwd=ROOT,
                stdout=tunnel_log,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
            processes.append(tunnel)
            deadline = time.monotonic() + 90
            origin = None
            while time.monotonic() < deadline and not stop_file.exists():
                if tunnel.poll() is not None:
                    raise RuntimeError("隧道未能启动，请查看 reports/web-share/tunnel.log")
                match = re.search(
                    r"https://[a-z0-9-]+\.trycloudflare\.com",
                    (DIRECTORY / "tunnel.log").read_text(encoding="utf-8", errors="replace"),
                )
                if match:
                    origin = match.group()
                    break
                time.sleep(0.5)
            if stop_file.exists():
                return
            if not origin:
                raise RuntimeError("获取临时链接超时，请查看 reports/web-share/tunnel.log")
            web = subprocess.Popen(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(ROOT / "web.py"),
                    "--port",
                    str(port),
                    "--public-origin",
                    origin,
                    "--share-password-file",
                    str(password_file),
                ],
                cwd=ROOT,
                stdout=web_log,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
            processes.append(web)
            deadline = time.monotonic() + 60
            ready = False
            with httpx.Client(trust_env=False, timeout=2) as client:
                while time.monotonic() < deadline and not stop_file.exists():
                    if web.poll() is not None or tunnel.poll() is not None:
                        raise RuntimeError("体验服务启动失败，请查看 reports/web-share/ 下的日志")
                    try:
                        address = f"http://127.0.0.1:{port}/"
                        locked = client.get(address)
                        page = client.get(address, auth=("friend", password))
                        if locked.status_code == 401 and page.status_code == 200:
                            ready = True
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.5)
            if stop_file.exists():
                return
            if not ready:
                raise RuntimeError("体验服务启动超时，请查看 reports/web-share/web.log")
            state.update(
                running=True, url=origin, web_pid=web.pid, tunnel_pid=tunnel.pid, port=port
            )
            state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
            invitation.write_text(
                f"知命 · 朋友体验\n链接：{origin}\n用户名：friend\n口令：{password}\n\n"
                "请在浏览器中打开。服务需要分享者的电脑开机联网。\n"
                "出生资料和聊天记录存储在分享者的电脑上，真实解读会调用模型服务。\n",
                encoding="utf-8",
            )
            invitation.chmod(0o600)
            print(f"体验入口已启动：{origin}", flush=True)
            print(f"用户名和口令保存在：{invitation}", flush=True)
            while not stop_file.exists():
                if any(process.poll() is not None for process in processes):
                    raise RuntimeError("体验服务或隧道已退出，请检查日志后重新启动")
                time.sleep(0.5)
    finally:
        for process in reversed(processes):
            stop_process(process)
        state["running"] = False
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="知命 · 朋友临时体验入口")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    if args.stop:
        (DIRECTORY / "stop").touch()
        print("已请求关闭朋友体验入口。")
        return
    # Hold a process-owned file lock; OS releases it even after a crash.
    with (DIRECTORY / "runner.lock").open("a+b") as lock:
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SystemExit(
                "体验入口已在运行，分享信息见 reports/web-share/invitation.txt"
            ) from exc
        try:
            run(args.port)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
