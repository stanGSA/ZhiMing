"""Admin console API, health check and the monitor's metrics endpoint.

Only the account ids listed in ``ZHIMING_ADMIN_IDS`` see the console; everyone else gets 404.
Rights follow the id, never the name: account names become free again when an account is
deleted, ids are random and never reused. The monitor reads ``/api/ops/metrics`` from the
same host with a bearer token; it never needs a browser session.
State-changing requests pass the web app's Origin and client-header checks like any other.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import platform
import re
import shutil
import sqlite3
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr

from harness.metering import ConcurrencyGate
from memory.accounts import AccountStore, username_key
from memory.costs import SettingsError

STATIC = Path(__file__).resolve().parent.parent / "web_static"
ACCOUNT_ID = re.compile(r"acct-[0-9a-f]{32}")
# Error rate and spend windows reported to the monitor.
ERROR_WINDOW = 30 * 60
HOUR = 3600


class Reason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field("", max_length=200)


class Grant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tokens: int = Field(ge=-10_000_000, le=10_000_000)


@dataclass
class AdminContext:
    accounts: Callable[[], AccountStore]
    # The signed-in root session for a request, or None; never creates one.
    current: Callable[[Request], object | None]
    # Drop the in-memory logins whose token hashes were ended.
    drop_logins: Callable[[str, list[str]], Awaitable[None]]
    gate: ConcurrencyGate
    admins: frozenset[str]
    monitor_token: str | None
    monitor_status: Path | None
    release_file: Path | None
    data_dir: Path
    stats: Callable[[], dict]


def parse_admin_ids(value: str | list[str] | None) -> frozenset[str]:
    items = value.split(",") if isinstance(value, str) else list(value or ())
    ids = frozenset(item.strip() for item in items if item.strip())
    invalid = [item for item in ids if not ACCOUNT_ID.fullmatch(item)]
    if invalid:
        # Names are refused outright: after a deletion a name can belong to someone else.
        raise ValueError(
            "管理员必须以账号 ID（acct-…）指定，不接受账号名；"
            "用 python -m ops.admin resolve 账号名 查询"
        )
    return ids


def resolve_admins(db_path: Path, names: list[str]) -> list[str]:
    """Account ids for account names, read-only. Raises LookupError for a name not registered."""
    db = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        ids = []
        for name in names:
            row = db.execute(
                "SELECT user_id FROM accounts WHERE username_key=?", (username_key(name),)
            ).fetchone()
            if row is None:
                raise LookupError(name)
            ids.append(row[0])
        return ids
    finally:
        db.close()


def not_found():
    return HTTPException(404)


def site_snapshot(store: AccountStore, gate: ConcurrencyGate, now: float) -> dict:
    """What both the monitor and the console need: budget, error rate, pause state."""
    costs = store.costs
    settings = costs.settings()
    start = costs.day_start(now)
    today = costs.spend(start, now)
    percents = []
    if settings["daily_token_budget"] > 0:
        percents.append(100 * today["tokens"] / settings["daily_token_budget"])
    priced = max(settings["input_price_per_mtok"], settings["output_price_per_mtok"]) > 0
    if settings["daily_cost_budget"] > 0 and priced:
        percents.append(100 * today["cost"] / settings["daily_cost_budget"])
    recent = costs.spend(now - ERROR_WINDOW, now)
    hour = costs.spend(now - HOUR, now)
    first = store.db.execute("SELECT MIN(created_at) FROM site_usage").fetchone()[0]
    week_hours = 0.0 if first is None else min(168.0, max(1.0, (now - first) / HOUR))
    week = costs.spend(now - 168 * HOUR, now)
    suspended = store.db.execute(
        "SELECT COUNT(*) FROM account_controls WHERE suspended_at IS NOT NULL"
    ).fetchone()[0]
    return {
        "generated_at": now,
        "paused": costs.pause_state(),
        "today": {
            **today,
            "day_start": start,
            "resets_at": costs.next_day(now),
            "token_budget": settings["daily_token_budget"],
            "cost_budget": settings["daily_cost_budget"] if priced else 0,
            "currency": settings["currency"],
            "priced": priced,
            "budget_percent": round(max(percents), 1) if percents else None,
            "budget_refused_at": costs.budget_refused_since(now),
        },
        "errors": {
            "window_s": ERROR_WINDOW,
            "calls": recent["calls"],
            "errors": recent["errors"],
            "rate": round(recent["errors"] / recent["calls"], 4) if recent["calls"] else 0.0,
            "kinds": costs.error_kinds(now - ERROR_WINDOW),
        },
        "last_hour": hour,
        "hourly_average_7d": round(week["tokens"] / week_hours) if week_hours else 0,
        "concurrency": gate.snapshot(),
        "suspended_accounts": suspended,
        "events": costs.events(since=now - 86400, limit=50),
    }


def read_json(path: Path | None, limit: int = 256 * 1024) -> dict | None:
    if path is None:
        return None
    try:
        if path.stat().st_size > limit:
            return {"error": "文件过大"}
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {"error": "无法读取"}


def install(app: FastAPI, ctx: AdminContext) -> None:
    def admin_of(request: Request) -> str:
        session = ctx.current(request)
        account = getattr(session, "account", None)
        user_id = getattr(session, "user_id", None)
        if not account or user_id not in ctx.admins or ctx.accounts().get(user_id) is None:
            raise not_found()
        return account["username"]

    def known(user_id: str) -> None:
        if ctx.accounts().get(user_id) is None:
            raise HTTPException(404, {"code": "not_found", "message": "找不到该账号。"})

    @app.api_route("/healthz", methods=["GET", "HEAD"], include_in_schema=False)
    async def health():
        """For uptime probes: the app answers and its database is readable. Says nothing else."""
        try:
            ctx.accounts().db.execute("SELECT 1").fetchone()
        except Exception:
            return JSONResponse(
                {"status": "error"}, status_code=503, headers={"Cache-Control": "no-store"}
            )
        return JSONResponse({"status": "ok"}, headers={"Cache-Control": "no-store"})

    @app.get("/api/ops/metrics", include_in_schema=False)
    async def metrics(request: Request):
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        # Behind Nginx the client is the real remote address, so only on-host callers pass.
        loopback = request.client is not None and request.client.host in ("127.0.0.1", "::1")
        if (
            not loopback
            or not ctx.monitor_token
            or scheme.lower() != "bearer"
            or not hmac.compare_digest(token.encode(), ctx.monitor_token.encode())
        ):
            raise not_found()
        return {
            **site_snapshot(ctx.accounts(), ctx.gate, time.time()),
            "settings": ctx.accounts().costs.settings(),
            "process": ctx.stats(),
        }

    @app.get("/admin", include_in_schema=False)
    async def console(request: Request):
        if ctx.current(request) is None:
            return RedirectResponse("/login?next=/admin", status_code=303)
        try:
            admin_of(request)
        except HTTPException:
            return FileResponse(STATIC / "notfound.html", status_code=404)
        return FileResponse(STATIC / "admin.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/admin/overview")
    async def overview(request: Request):
        admin = admin_of(request)
        store = ctx.accounts()
        now = time.time()
        costs = store.costs
        try:
            disk = shutil.disk_usage(ctx.data_dir)
            disk_info = {"total": disk.total, "free": disk.free, "path": str(ctx.data_dir)}
        except OSError:
            disk_info = None
        monitor = read_json(ctx.monitor_status)
        return {
            "admin": admin,
            "site": site_snapshot(store, ctx.gate, now),
            "hourly": costs.hourly(now),
            "top_accounts": costs.top_accounts(costs.day_start(now)),
            "settings": {
                "effective": costs.settings(),
                "defaults": costs.defaults,
                "overrides": costs.overrides(),
            },
            "audit": costs.audit_log(30),
            "monitor": monitor,
            "system": {
                **ctx.stats(),
                "accounts": store.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0],
                "disk": disk_info,
                "python": platform.python_version(),
                "pid": os.getpid(),
                "release": read_json(ctx.release_file, 64 * 1024),
            },
        }

    @app.put("/api/admin/settings")
    async def update_settings(
        request: Request, body: dict[str, StrictInt | StrictFloat | StrictStr]
    ):
        admin = admin_of(request)
        try:
            settings = ctx.accounts().costs.update(body, admin)
        except SettingsError as exc:
            raise HTTPException(
                422, {"code": "invalid_setting", "message": exc.message, "field": exc.key}
            ) from None
        ctx.gate.dispatch()
        return {"settings": settings}

    @app.post("/api/admin/settings/reset")
    async def reset_settings(request: Request):
        settings = ctx.accounts().costs.reset(admin_of(request))
        ctx.gate.dispatch()
        return {"settings": settings}

    @app.post("/api/admin/models/pause")
    async def pause(body: Reason, request: Request):
        state = ctx.accounts().costs.manual_pause(body.reason.strip(), admin_of(request))
        return {"paused": state}

    @app.post("/api/admin/models/resume")
    async def resume(request: Request):
        ctx.accounts().costs.manual_resume(admin_of(request))
        return {"paused": None}

    @app.get("/api/admin/accounts")
    async def list_accounts(
        request: Request,
        q: str = Query("", max_length=32),
        offset: int = Query(0, ge=0, le=1_000_000),
        limit: int = Query(50, ge=1, le=200),
    ):
        admin_of(request)
        store = ctx.accounts()
        items, total = store.list_accounts(
            q, offset, limit, since=store.costs.day_start(time.time())
        )
        return {"items": items, "total": total, "offset": offset}

    @app.post("/api/admin/accounts/{user_id}/suspend")
    async def suspend(user_id: str, body: Reason, request: Request):
        admin = admin_of(request)
        known(user_id)
        ctx.accounts().set_suspended(user_id, body.reason.strip() or "管理员暂停", admin)
        return {"ok": True}

    @app.post("/api/admin/accounts/{user_id}/unsuspend")
    async def unsuspend(user_id: str, request: Request):
        admin = admin_of(request)
        known(user_id)
        ctx.accounts().set_suspended(user_id, None, admin)
        return {"ok": True}

    @app.post("/api/admin/accounts/{user_id}/grant")
    async def grant(user_id: str, body: Grant, request: Request):
        admin = admin_of(request)
        known(user_id)
        ctx.accounts().grant_tokens(user_id, body.tokens, admin)
        return {"quota": ctx.accounts().quota(user_id)}

    @app.post("/api/admin/accounts/{user_id}/logout")
    async def logout(user_id: str, request: Request):
        admin = admin_of(request)
        known(user_id)
        ended = ctx.accounts().revoke_all(user_id, admin)
        await ctx.drop_logins(user_id, ended)
        return {"ended": len(ended)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="知命管理员账号 ID 查询")
    commands = parser.add_subparsers(dest="command", required=True)
    resolve = commands.add_parser("resolve", help="按账号名查询账号 ID，输出逗号分隔的 ID")
    resolve.add_argument("names", nargs="+", help="已注册的管理员账号名")
    resolve.add_argument("--db", type=Path, default=Path("data/app.db"), help="业务库路径")
    args = parser.parse_args(argv)
    try:
        print(",".join(resolve_admins(args.db, args.names)))
    except LookupError as exc:
        print(f"账号不存在：{exc.args[0]}（请先在网站注册）", file=sys.stderr)
        return 1
    except sqlite3.Error as exc:
        print(f"无法读取业务库：{type(exc).__name__}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
