"""Local browser interface. Run with .venv/Scripts/python.exe web.py."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import re
import secrets
import shutil
import sqlite3
import time
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from datetime import date as CalendarDate
from datetime import datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import yaml
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from lunar_python import Solar
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import MEMORY_NOTE, ROOT, Runtime, create_runtime, memory_note
from common.regions import region_options, selected_region
from common.schemas import ReadInput
from common.time_utils import NeedsInput
from harness.failures import failure
from harness.progress import progress_label
from harness.trace import Tracer
from memory.accounts import (
    AccountError,
    AccountStore,
    check_password,
    check_username,
    dummy_verify,
    hash_password,
    token_digest,
    username_key,
    verify_password,
)
from memory.store import Store
from plugins.astro.calculator import natal_chart
from plugins.bazi.calculator import GAN, GAN_WX, WX, compute_bazi, ten_god
from plugins.direct import birth_inputs
from plugins.name.strokes import UnihanMissing
from plugins.name.tools import HAN
from plugins.name.wuge import analyze, element
from plugins.tarot.draw import valid_picks

STATIC = Path(__file__).with_name("web_static")
EVALUATION_PROGRESS = Path("reports/p1/codego-v4/web-progress.json")
COOKIE = "zhiming_session"
MAX_IDLE = 12 * 3600
# An account's login lasts this long after its last use; its records stay until deleted.
ACCOUNT_IDLE = 30 * 24 * 3600
# Each consultation has its own page; "/" is the entrance (login) page.
PAGES = {
    "ask": "ask.html",
    "bazi": "bazi.html",
    "astro": "astro.html",
    "tarot": "tarot.html",
    "name": "name.html",
    "dream": "dream.html",
    "daily": "daily.html",
}
SYSTEM_LABELS = {
    "bazi": "八字",
    "astro": "西方占星",
    "tarot": "塔罗",
    "name": "姓名五格",
    "dream": "解梦",
    "daily": "每日运势",
}
# Only these consultations use the birth form; tarot, dreams and names never receive it.
BIRTH_SYSTEMS = ("auto", "bazi", "astro", "daily")
DEMO_UNSUPPORTED = {
    "name": "离线演示不调用模型，姓名解读需切换真实模型。五格笔画与三才可在上方点「推演」直接计算。",
    "dream": "离线演示不调用模型，解梦需切换真实模型后再试。你的梦境描述已保留在对话中。",
    "daily": "离线演示不调用模型，今日运势解读需切换真实模型。上方的流日干支与十神由历法直接计算，可先参考。",
}
WEEKDAYS = "一二三四五六日"
logger = logging.getLogger(__name__)


class BirthInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: CalendarDate | None = None
    time: str = ""
    unknown_time: bool = False
    place: str = Field(default="", max_length=100)
    gender: Literal["", "male", "female"] = ""
    location_id: str = Field(default="", max_length=30)
    clock_tz: Literal["", "Asia/Shanghai", "Asia/Urumqi"] = ""
    true_solar_time: bool = False
    zishi_rule: Literal["next_day", "same_day"] = "next_day"

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        if (
            value
            and not CalendarDate(1850, 1, 1)
            <= value
            <= datetime.now(ZoneInfo("Asia/Shanghai")).date()
        ):
            raise ValueError("请输入有效的出生日期")
        return value

    @field_validator("time")
    @classmethod
    def valid_time(cls, value):
        if value:
            value = datetime.strptime(value, "%H:%M").strftime("%H:%M")
        return value

    @model_validator(mode="after")
    def consistent(self):
        self.place = self.place.strip()
        if self.time and not self.date:
            raise ValueError("填写出生时刻前请先填写日期")
        if self.unknown_time:
            self.time = ""
        if self.location_id:
            location = selected_region(self.location_id)
            self.place = location["display_name"]
            if self.clock_tz and location["tz"] != "Asia/Urumqi":
                raise ValueError("此地点无需指定新疆钟表时间制")
        return self

    def canonical(self):
        values = self.model_dump(mode="json")
        values["unknown_time"] = not bool(self.time)
        return values

    def evidence(self) -> str:
        parts = []
        if self.date:
            parts.append(f"我的出生日期是公历 {self.date.isoformat()}")
            if self.time:
                # Keep the date and its clock time in the same sentence: the evidence
                # parser deliberately refuses to associate a later sentence's time.
                parts[-1] += f" {self.time}（出生时间确定）"
            else:
                parts.append("出生时间不确定，请不要假定出生时刻")
        if self.place.strip():
            parts.append(f"出生地点是{self.place.strip()}")
        if self.gender:
            parts.append("性别为" + {"male": "男", "female": "女"}[self.gender])
        if self.location_id:
            location = selected_region(self.location_id)
            parts.append(
                f"我选择的地点编号为{location['location_id']}，经度{location['lon']}，纬度{location['lat']}"
            )
            if location["tz"] == "Asia/Urumqi" and not self.clock_tz:
                parts.append("出生钟表采用北京时间还是新疆时间尚未确认，请先问我")
            else:
                parts.append(f"出生钟表时区为{self.clock_tz or location['tz']}")
            parts.append("使用真太阳时" if self.true_solar_time else "不用真太阳时")
            parts.append("23点换日" if self.zishi_rule == "next_day" else "0点换日")
        return "；".join(parts)

    def chart(self, system):
        if not self.date or not self.location_id:
            raise NeedsInput("missing_birth", "请先填写公历出生日期，并逐级选择出生地点。")
        location = selected_region(self.location_id)
        inputs = birth_inputs(
            self.date.isoformat() + ("T" + self.time if self.time else ""),
            bool(self.time) and not self.unknown_time,
            location,
            self.clock_tz,
        )
        if system == "bazi":
            inputs.pop("lat")
            result = compute_bazi(
                **inputs,
                gender=self.gender or None,
                true_solar_time=self.true_solar_time,
                zishi_rule=self.zishi_rule,
            )
        else:
            result = natal_chart(**inputs)
        return dict(
            system=system, result=result, location=location, birth=self.model_dump(mode="json")
        )


SystemName = Literal["auto", "bazi", "astro", "tarot", "name", "dream", "daily"]


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)
    system: SystemName = "auto"
    reading_id: str | None = Field(default=None, min_length=1, max_length=80)
    birth: BirthInfo = Field(default_factory=BirthInfo)
    expected_birth_version: int | None = Field(default=None, ge=0)
    spread: Literal["single", "three_card", "decision"] = "three_card"
    # Positions (0-77) chosen from the face-down deck on the tarot page, in spread order.
    picks: list[int] | None = Field(default=None, max_length=3)

    @field_validator("message")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("请先写下你的问题")
        return value.strip()

    @model_validator(mode="after")
    def picks_fit_spread(self):
        if self.picks is not None and (
            self.system != "tarot" or not valid_picks(self.picks, self.spread)
        ):
            raise ValueError("所选的牌与牌阵不符，请重新选牌")
        return self


class NewInput(BaseModel):
    provider: Literal["configured", "demo"] = "configured"
    system: SystemName = "auto"


class ChartInput(BaseModel):
    system: Literal["bazi", "astro"]
    birth: BirthInfo
    expected_birth_version: int | None = Field(default=None, ge=0)


class NameQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    surname: str = Field(min_length=1, max_length=2)
    given: str = Field(min_length=1, max_length=3)
    forms: dict[str, str] = Field(default_factory=dict, max_length=5)

    @field_validator("surname", "given", mode="before")
    @classmethod
    def trimmed(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def han_only(self):
        full = self.surname + self.given
        if not re.fullmatch(f"{HAN}+", full):
            raise ValueError("姓名只能包含汉字")
        for char, form in self.forms.items():
            if char not in full or not re.fullmatch(HAN, form):
                raise ValueError("写法确认只能针对本名中的字，且为单个汉字")
        return self


class AlmanacInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: CalendarDate | None = None
    birth: BirthInfo = Field(default_factory=BirthInfo)

    @field_validator("date")
    @classmethod
    def supported(cls, value):
        if value and not CalendarDate(1901, 1, 1) <= value <= CalendarDate(2099, 12, 31):
            raise ValueError("请选择 1901 至 2099 年之间的日期")
        return value


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    # Move this browser's guest records into the account instead of deleting them.
    keep_guest_records: bool = False


class Registration(Credentials):
    accept_privacy: bool = False


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class PasswordConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=256)


# Every error the browser receives has the shape {"detail": {"code": ..., "message": ...}}.
STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "invalid_input",
    429: "rate_limited",
    503: "unavailable",
}
STATUS_MESSAGES = {
    404: "找不到请求的内容。",
    405: "不支持这种请求方式。",
}
FIELD_LABELS = {
    "message": "问题",
    "date": "日期",
    "time": "时间",
    "place": "出生地点",
    "location_id": "出生地点",
    "gender": "性别",
    "surname": "姓",
    "given": "名",
    "system": "功能",
    "spread": "牌阵",
    "picks": "所选的牌",
    "provider": "体验模式",
    "username": "账号名",
    "password": "密码",
    "current_password": "当前密码",
    "new_password": "新密码",
    "q": "搜索词",
}


HAN_TEXT = re.compile(r"[\u4e00-\u9fff]")


def problem(status: int, code: str, message: str, headers=None, **extra) -> JSONResponse:
    return JSONResponse(
        {"detail": {"code": code, "message": message, **extra}},
        status_code=status,
        headers={"Cache-Control": "no-store", **(headers or {})},
    )


def readable_error(error: dict) -> str:
    """One validation error in plain Chinese; model validators already speak Chinese."""
    kind, context = error.get("type", ""), error.get("ctx") or {}
    names = [str(part) for part in error.get("loc", ()) if isinstance(part, str)]
    label = next((FIELD_LABELS[name] for name in reversed(names) if name in FIELD_LABELS), "")
    if kind == "value_error":
        text = str(error.get("msg", "")).removeprefix("Value error, ")
        if HAN_TEXT.search(text):
            return text
        return f"{label or '填写的内容'}格式不正确。"
    if kind == "string_too_short":
        minimum = context.get("min_length", 1)
        reason = "不能为空" if minimum <= 1 else f"至少需要 {minimum} 个字符"
    elif kind == "string_too_long":
        reason = f"过长（最多 {context.get('max_length')} 个字符）"
    else:
        reason = {
            "missing": "缺少必填项",
            "too_long": "项目过多",
            "too_short": "项目过少",
            "literal_error": "选项无效",
            "enum": "选项无效",
            "extra_forbidden": "包含不支持的字段",
            "json_invalid": "请求格式无效",
            "date_parsing": "日期格式无效",
            "date_from_datetime_parsing": "日期格式无效",
            "date_type": "日期格式无效",
            "int_parsing": "需要填写整数",
            "bool_parsing": "需要选择是或否",
            "string_type": "需要填写文字",
            "greater_than_equal": "超出允许范围",
            "less_than_equal": "超出允许范围",
        }.get(kind, "格式不正确")
    return f"{label}{reason}。" if label else f"填写的内容{reason}。"


class AttemptLimiter:
    """Attempts per key in a sliding window: failed sign-ins, new accounts."""

    def __init__(self):
        self.attempts: dict[str, list[float]] = {}

    def retry_after(self, key: str, limit: int, window: float) -> int:
        now = time.monotonic()
        recent = [t for t in self.attempts.get(key, []) if t > now - window]
        if recent:
            self.attempts[key] = recent
        else:
            self.attempts.pop(key, None)
        return int(recent[0] + window - now) + 1 if len(recent) >= limit else 0

    def record(self, key: str) -> None:
        if len(self.attempts) > 4096:
            # Bounded memory: drop keys whose attempts are all older than the longest window.
            horizon = time.monotonic() - 3600
            self.attempts = {k: v for k, v in self.attempts.items() if v[-1] > horizon}
        self.attempts.setdefault(key, []).append(time.monotonic())

    def reset(self, key: str) -> None:
        self.attempts.pop(key, None)


# Stated in every export, so nobody mistakes the file for a backup.
EXPORT_SCOPE = {
    "purpose": "个人数据副本，供查阅与留存；不是备份，本服务不提供导入。",
    "included": [
        "账号名、注册时间、同意的隐私说明版本与同意时间",
        "生辰档案、画像及其修改记录（含当时的原话依据）",
        "全部解读：问题、正文、牌面、计算结果、信号、跨体系合并表、专家报告、审校意见与历次追问",
    ],
    "excluded": [
        "排盘与每日运势缓存：可由生辰档案重新计算",
        "运行日志（trace）：诊断用的工具调用记录，可向部署者申请获取；清除记录或注销账号时删除",
        "密码散列与登录凭证",
    ],
}


def checkpoint(path: Path) -> None:
    """Fold the write-ahead log, which still holds pages of deleted rows, into the database
    and truncate it. Run in a worker thread with its own connection."""
    db = sqlite3.connect(path, timeout=30)
    try:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        db.close()


def almanac(day: CalendarDate, day_master: str | None, kb) -> dict:
    """Calendar facts for one day and its week; the day pillar is taken at local noon."""

    def lunar_of(value):
        return Solar.fromYmdHms(value.year, value.month, value.day, 12, 0, 0).getLunar()

    def brief(value):
        lunar = lunar_of(value)
        pillar = lunar.getDayInGanZhiExact()
        return dict(
            date=value.isoformat(),
            weekday=WEEKDAYS[value.weekday()],
            day_pillar=pillar,
            term=lunar.getJieQi() or None,
            ten_god=ten_god(day_master[0], pillar[0]) if day_master else None,
        )

    lunar = lunar_of(day)
    today = brief(day)
    stem = today["day_pillar"][0]
    day_element = WX[GAN_WX[GAN.index(stem)]]
    entry = kb.lookup("daily", "day_element", day_element)
    upcoming = lunar.getNextJieQi(True)
    monday = day - timedelta(days=day.weekday())
    return dict(
        **today,
        lunar_date=("闰" if lunar.getMonth() < 0 else "")
        + lunar.getMonthInChinese()
        + "月"
        + lunar.getDayInChinese(),
        year_pillar=lunar.getYearInGanZhiByLiChun(),
        month_pillar=lunar.getMonthInGanZhiExact(),
        current_term=lunar.getPrevJieQi(True).getName(),
        hou=lunar.getHou(),
        wuhou=lunar.getWuHou(),
        next_term=dict(name=upcoming.getName(), date=upcoming.getSolar().toYmd()),
        day_element=day_element,
        day_element_note=entry["text"] if entry else None,
        day_master=day_master,
        week=[brief(monday + timedelta(days=offset)) for offset in range(7)],
        conventions=dict(
            day_pillar="流日取当地正午所在日柱",
            ten_god="十神以出生日主对流日天干推算",
            calendar="立春换年、节气换月",
        ),
    )


@dataclass
class BrowserSession:
    user_id: str
    runtime: Runtime
    provider: str
    messages: list = field(default_factory=list)
    birth: BirthInfo = field(default_factory=BirthInfo)
    last_birth: str = ""
    reading: dict | None = None
    chart: dict | None = None
    name_analysis: dict | None = None
    # A tarot draw sent but not yet answered with cards (e.g. the model asked something back):
    # its question, spread and positions, so a reloaded page can continue the same round.
    tarot_round: dict | None = None
    progress: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=128))
    progress_streams: dict = field(default_factory=dict)
    progress_id: str = ""
    progress_active: bool = False
    progress_readers: set[str] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    touched: float = field(default_factory=time.monotonic)
    system: str = "auto"
    owner: BrowserSession | None = field(default=None, repr=False)
    contexts: dict[str, BrowserSession] = field(default_factory=dict, repr=False)
    safety_pending: bool = False
    bound_birth: BirthInfo | None = None
    birth_version: int = 0
    birth_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    active_birth_requests: set[str] = field(default_factory=set)
    birth_stale: bool = False
    session_revision: int = 0
    # The signed-in account ({"username", "created_at"}); None for a guest. Root sessions only.
    account: dict | None = None


def create_web_app(
    root: Path = ROOT,
    runtime_factory=create_runtime,
    *,
    public_origin: str | None = None,
    share_password: str | None = None,
) -> FastAPI:
    """Keep local access as the default; sharing requires an exact HTTPS origin and password."""
    if (public_origin is None) != (share_password is None):
        raise ValueError("分享模式必须同时配置 HTTPS 地址和访问口令")
    allowed_hosts = ["127.0.0.1", "localhost", "testserver"]
    if public_origin is not None:
        public_origin = public_origin.rstrip("/")
        parsed = urlsplit(public_origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.port not in (None, 443)
            or "*" in parsed.netloc
            or len(share_password or "") < 16
        ):
            raise ValueError("分享地址必须为 HTTPS 域名，访问口令至少 16 个字符")
        allowed_hosts.append(parsed.hostname)
    share_credentials = f"friend:{share_password}".encode() if share_password else None
    # Cookie key -> root session. A guest key lives only in memory; an account key is also a
    # login token in the database, so several browsers (and restarts) reach one account.
    sessions: dict[str, BrowserSession] = {}
    # Account user id -> its root session while loaded in memory.
    accounts_live: dict[str, BrowserSession] = {}
    cleanup_lock = asyncio.Lock()
    config = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    limiter = AttemptLimiter()
    # Changes on every start: a page that sees a new value knows earlier revisions are gone.
    instance = secrets.token_hex(4)
    extended: dict[str, float] = {}
    account_db: list[AccountStore] = []
    checkpoints: dict[str, object] = {"task": None, "again": False}

    def accounts() -> AccountStore:
        if not account_db:
            account_db.append(AccountStore(root / config["paths"]["app_db"]))
        return account_db[0]

    def live_roots():
        roots = {id(s): s for s in [*sessions.values(), *accounts_live.values()]}
        return list(roots.values())

    def keys_of(root_session):
        return [key for key, value in sessions.items() if value is root_session]

    async def purge_expired(adopt: bool = False):
        async with cleanup_lock:
            store = Store(root / config["paths"]["app_db"])
            try:
                now = time.time()
                discard_trace_copies(store)
                if adopt:
                    # Pre-lease records exist only before the first start of this version.
                    store.adopt_web_identities(now + MAX_IDLE)
                for user_id in store.expired_web_identities(now):
                    active = [(k, s) for k, s in sessions.items() if s.user_id == user_id]
                    if any(c.lock.locked() for _, s in active for c in family(s)):
                        continue
                    try:
                        for key, session in active:
                            sessions.pop(key, None)
                            for context in family(session):
                                await close(context)
                        # Trace first: forget() also drops the deadline row, so any failure
                        # before it leaves the identity listed and the next pass retries.
                        tracer = Tracer(root / config["paths"]["runs"])
                        directory = tracer.user_dir(user_id).resolve()
                        if directory.is_relative_to(tracer.root.resolve()) and directory.exists():
                            shutil.rmtree(directory)
                        store.forget(user_id, compact=False)
                        checkpoint_later()
                    except Exception:
                        logger.exception("Could not remove an expired browser identity")
            finally:
                store.close()
            # Accounts keep their records; only ended logins and idle memory are released.
            ended = set(accounts().purge_sessions(time.time()))
            for key in [k for k, s in sessions.items() if s.account and token_digest(k) in ended]:
                sessions.pop(key, None)
            for key in [k for k in extended if k not in sessions]:
                extended.pop(key)
            for root_session in list(accounts_live.values()):
                idle = time.monotonic() - root_session.touched > MAX_IDLE
                if (idle or not keys_of(root_session)) and not any(
                    c.lock.locked() for c in family(root_session)
                ):
                    await release(root_session)

    async def purge_safely():
        try:
            await purge_expired()
        except Exception:
            # A cleanup fault must not take down serving or the periodic reaper.
            logger.exception("Expired browser data cleanup failed")

    async def close(session):
        try:
            await session.runtime.close_model()
        finally:
            session.runtime.close()

    async def release(root_session):
        """Drop a session family's cookies from memory and close its runtimes."""
        for key in keys_of(root_session):
            sessions.pop(key, None)
        if accounts_live.get(root_session.user_id) is root_session:
            accounts_live.pop(root_session.user_id)
        for context in family(root_session):
            try:
                await close(context)
            except Exception:
                # The records are already settled; a client that will not close is only logged.
                logger.exception("Could not close a released browser runtime")

    def checkpoint_later():
        """After deletions, checkpoint in a worker thread instead of blocking every request.
        One run at a time; requests during a run queue exactly one more."""
        running = checkpoints["task"]
        if running is not None and not running.done():
            checkpoints["again"] = True
            return
        checkpoints["task"] = asyncio.create_task(run_checkpoints())

    async def run_checkpoints():
        while True:
            checkpoints["again"] = False
            try:
                await asyncio.to_thread(checkpoint, root / config["paths"]["app_db"])
            except Exception:
                logger.exception("Background database checkpoint failed")
            if not checkpoints["again"]:
                return

    async def reap():
        while True:
            await asyncio.sleep(60)
            await purge_safely()

    @asynccontextmanager
    async def lifespan(_app):
        await purge_expired(adopt=True)
        cleanup = asyncio.create_task(reap())
        yield
        cleanup.cancel()
        await asyncio.gather(cleanup, return_exceptions=True)
        for root_session in live_roots():
            for context in family(root_session):
                await close(context)
        sessions.clear()
        accounts_live.clear()
        if checkpoints["task"] is not None:
            await asyncio.gather(checkpoints["task"], return_exceptions=True)
        if account_db:
            account_db.pop().close()

    app = FastAPI(title="知命", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    @app.get("/api/evaluation-progress")
    async def evaluation_progress():
        """Return the redacted live status of the external evaluation queue."""
        path = root / EVALUATION_PROGRESS
        if not path.is_file():
            return {
                "schema_version": 1,
                "status": "not_started",
                "planned_cases": 0,
                "completed_cases": 0,
                "percent": 0,
                "batches": [],
                "error_count": 0,
                "recent_errors": [],
            }
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return JSONResponse(
                {"schema_version": 1, "status": "unavailable", "error_count": 1},
                headers={"Cache-Control": "no-store"},
            )
        # Keep this API useful to the browser while excluding traces, prompts,
        # answers, credentials, and arbitrary fields from the progress file.
        batches = []
        for batch in payload.get("batches", []):
            batches.append(
                {
                    key: batch.get(key)
                    for key in ("name", "expected", "completed", "terminal", "status", "last_case")
                    if key in batch
                }
            )
        errors = []
        for error in payload.get("recent_errors", [])[-100:]:
            item = {
                key: error.get(key)
                for key in ("batch", "case", "repeat", "kind", "tool", "code", "message")
                if key in error
            }
            errors.append(item)
        response = {
            key: payload.get(key)
            for key in (
                "schema_version",
                "updated",
                "status",
                "active_job",
                "runtime_model",
                "judge_model",
                "planned_cases",
                "completed_cases",
                "percent",
                "error_count",
            )
            if key in payload
        }
        response.update({"batches": batches, "recent_errors": errors})
        return JSONResponse(response, headers={"Cache-Control": "no-store"})

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        # Quoted in unexpected-error replies and the server log, so a report can be traced.
        request.state.request_id = secrets.token_hex(6)
        response = await respond(request, call_next)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    async def respond(request: Request, call_next):
        if share_credentials is not None:
            scheme, _, token = request.headers.get("authorization", "").partition(" ")
            try:
                credentials = base64.b64decode(token, validate=True)
            except (ValueError, binascii.Error):
                credentials = b""
            if scheme.lower() != "basic" or not secrets.compare_digest(
                credentials, share_credentials
            ):
                return problem(
                    401,
                    "share_auth_required",
                    "请输入朋友体验的用户名和访问口令。",
                    headers={"WWW-Authenticate": 'Basic realm="ZhiMing Friends", charset="UTF-8"'},
                )
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            expected_origin = public_origin or str(request.base_url).rstrip("/")
            if origin and origin != expected_origin:
                return problem(403, "origin_rejected", "请从知命页面发起请求。")
            if request.headers.get("x-zhiming-client") != "web":
                return problem(403, "client_rejected", "请求来源无效，请从知命页面操作。")
        await purge_safely()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled error in %s %s [%s]",
                request.method,
                request.url.path,
                request.state.request_id,
            )
            return problem(
                500,
                "internal_error",
                "服务出现意外错误，请稍后重试；若反复出现，请附上错误编号反馈。",
                request_id=request.state.request_id,
            )
        key = request.cookies.get(COOKIE, "")
        session = sessions.get(key)
        if session is not None:
            touch(session)
            if session.account:
                keep_login(key)
            response.set_cookie(
                COOKIE,
                key,
                httponly=True,
                secure=public_origin is not None,
                samesite="strict",
                max_age=ACCOUNT_IDLE if session.account else MAX_IDLE,
            )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        path = request.url.path
        if exc.status_code == 404 and request.method in ("GET", "HEAD"):
            if not path.startswith(("/api/", "/static/")):
                return FileResponse(STATIC / "notfound.html", status_code=404)
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        if detail:
            message = detail.get("message", "")
        elif isinstance(exc.detail, str) and exc.detail != HTTPStatus(exc.status_code).phrase:
            message = exc.detail
        else:
            # Framework defaults ("Not Found") are replaced by plain Chinese.
            message = STATUS_MESSAGES.get(exc.status_code, "请求未能完成，请稍后重试。")
        extra = {k: v for k, v in detail.items() if k not in ("code", "message")}
        return problem(
            exc.status_code,
            detail.get("code") or STATUS_CODES.get(exc.status_code, "error"),
            message,
            headers=exc.headers,
            **extra,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError):
        errors = [
            {
                "field": ".".join(
                    str(part) for part in error.get("loc", ()) if part not in ("body", "query")
                ),
                "message": readable_error(error),
            }
            for error in exc.errors()
        ]
        message = errors[0]["message"] if errors else "请检查填写的内容是否正确。"
        return problem(422, "invalid_input", message, errors=errors)

    @app.exception_handler(AccountError)
    async def account_refused(request: Request, exc: AccountError):
        status = 409 if exc.code == "username_taken" else 422
        return problem(status, exc.code, exc.message)

    def keep_login(key):
        """Slide an account login's expiry; written at most every five minutes."""
        now = time.monotonic()
        if now - extended.get(key, -3600.0) > 300:
            extended[key] = now
            accounts().extend_session(key, time.time() + ACCOUNT_IDLE)

    def build(user_id, provider):
        try:
            return runtime_factory(
                root=root, user_id=user_id, provider="demo" if provider == "demo" else None
            )
        except Exception as exc:
            logger.exception("Could not start browser runtime")
            raise HTTPException(503, "服务暂时无法启动，请检查本地模型配置与知识库。") from exc

    def touch(session):
        session.touched = time.monotonic()
        if session.account is None:
            # Guests are cleared after an idle period; accounts keep their records.
            session.runtime.store.touch_web_identity(session.user_id, time.time() + MAX_IDLE)

    def family(session):
        root_session = session.owner or session
        return [root_session, *root_session.contexts.values()]

    def context_for(root_session, system):
        if system == "auto":
            return root_session
        if system not in root_session.contexts:
            context = BrowserSession(
                root_session.user_id,
                build(root_session.user_id, root_session.provider),
                root_session.provider,
                system=system,
                owner=root_session,
            )
            attach_progress(context)
            root_session.contexts[system] = context
        return root_session.contexts[system]

    def resolve(key: str, provider: str = "configured"):
        """The root session for a cookie: in memory, or an account login kept in the database."""
        session = sessions.get(key)
        if session is not None or not key or len(key) > 128:
            return session
        user_id = accounts().session_user(key, time.time())
        account = accounts().get(user_id) if user_id else None
        if account is None:
            return None
        session = accounts_live.get(user_id)
        if session is None:
            if len(live_roots()) >= 64:
                raise HTTPException(503, {"code": "busy", "message": "当前会话过多，请稍后再试。"})
            session = BrowserSession(user_id, build(user_id, provider), provider)
            session.account = public_account(account)
            attach_progress(session)
            restore_birth(session)
            accounts_live[user_id] = session
        sessions[key] = session
        return session

    def public_account(account):
        return {"username": account["username"], "created_at": account["created_at"]}

    def restore_birth(root_session):
        saved = root_session.runtime.store.get_web_birth(root_session.user_id)
        if saved is None:
            return
        try:
            root_session.birth = BirthInfo.model_validate(saved[0])
        except ValueError:
            # A saved place may have left the region data; keep the revision, ask again.
            root_session.birth = BirthInfo()
        root_session.birth_version = saved[1]

    def get_session(request: Request, system: str | None = None):
        session = resolve(request.cookies.get(COOKIE, ""))
        if session is None:
            raise HTTPException(
                401,
                {
                    "code": "session_expired",
                    "message": "会话已过期。访客请刷新页面重新开始；账号用户请重新登录，云端记录不受影响。",
                },
            )
        touch(session)
        selected = system or request.query_params.get("system", "auto")
        if selected not in ("auto", *SYSTEM_LABELS):
            raise HTTPException(422, "咨询功能无效")
        context = context_for(session, selected)
        session.safety_pending = session.safety_pending or any(
            c.runtime.session.safety_pending for c in family(session)
        )
        context.runtime.session.safety_pending = session.safety_pending
        return context

    def expected_birth_version(request, explicit=None):
        if explicit is not None:
            return explicit
        value = request.headers.get("x-zhiming-birth-version")
        if value is None:
            return None
        if not value.isdecimal():
            raise HTTPException(422, "出生资料版本无效")
        return int(value)

    def birth_conflict(code, message):
        raise HTTPException(409, {"code": code, "message": message})

    def share_birth(session, birth, expected):
        """Caller holds the owner's short birth_lock; no model calls in this section."""
        owner = session.owner or session
        changed = birth.canonical() != owner.birth.canonical()
        if expected is not None and expected != owner.birth_version:
            birth_conflict("birth_version_conflict", "出生资料已在其他页面更新，请同步后重新提交。")
        if changed:
            # Initial imports remain compatible; every later mutation needs a revision.
            if owner.birth_version and expected is None:
                birth_conflict("birth_version_required", "修改出生资料前请先同步当前资料版本。")
            if owner.active_birth_requests:
                birth_conflict("birth_in_use", "正在按当前生辰解读，请等待完成后再修改出生资料。")
            # A database failure must not advance the in-memory birth revision.
            values, _ = birth_profile(birth)
            profile = session.runtime.store.get_profile(session.user_id)
            if any(profile.get(k) != v for k, v in values.items()):
                session.runtime.store.update_profile_fields(
                    session.user_id, values, birth.evidence()
                )
            # Saved with its revision, so an account restores both on its next login.
            session.runtime.store.save_web_birth(
                session.user_id, birth.model_dump(mode="json"), owner.birth_version + 1
            )
            owner.birth = birth.model_copy(deep=True)
            owner.birth_version += 1
            for context in family(owner):
                context.chart = None
                if not context.runtime.session.pinned_reading_id:
                    invalidate_birth(context)

    def birth_profile(birth):
        location = selected_region(birth.location_id) if birth.location_id else None
        tz = (birth.clock_tz or location["tz"]) if location else None
        if location and location["tz"] == "Asia/Urumqi" and not birth.clock_tz:
            tz = None
        values = dict(
            birth_local_dt=(birth.date.isoformat() + (" " + birth.time if birth.time else ""))
            if birth.date
            else None,
            time_known=bool(birth.time) and not birth.unknown_time,
            birth_place=birth.place or None,
            location_id=location["location_id"] if location else None,
            tz=tz,
            lat=location["lat"] if location else None,
            lon=location["lon"] if location else None,
            gender=birth.gender or None,
            true_solar_time=birth.true_solar_time,
            zishi_rule=birth.zishi_rule,
            calendar_input="solar",
            dayun_time_basis="civil",
            lunar_date=None,
            leap_month=None,
        )
        return values, location

    def invalidate_birth(session):
        target = session.runtime.session
        dependent = any(target.state.get(k) for k in ("bazi_id", "chart_id", "daily_result"))
        dependent = (
            dependent
            or bool(set(target.state.get("specialist_facts", {})) & {"bazi", "astro", "daily"})
            or bool(
                set((session.reading or {}).get("output", {}).get("systems_used", []))
                & {"bazi", "astro", "daily"}
            )
        )
        if dependent:
            selected = {
                k: v
                for k, v in target.state.items()
                if k in ("selected_systems", "selected_spread", "ref_alias")
            }
            # Keep an unfinished draw even when its accompanying birth calculation is
            # corrected. The model must never silently redraw an existing set of cards.
            kept_tarot = target.state.get("specialist_facts", {}).get("tarot", {})
            pending_tarot = target.state.get("tarot_result") or kept_tarot.get("values", {}).get(
                "tarot_result"
            )
            if pending_tarot and not target.state.get("complete"):
                keep = {
                    k: target.state[k]
                    for k in (
                        "active_reading_id",
                        "parent_reading_id",
                        "question",
                        "question_message_index",
                        "seed",
                        "requested_spread",
                        "tarot_drawn",
                        "tarot_result",
                        "systems",
                    )
                    if k in target.state
                }
                signals = [
                    s for s in target.state.get("signals", []) if s["system"] == "tarot"
                ] or kept_tarot.get("signals", [])
                selected.update(
                    keep,
                    signals=signals,
                    complete=False,
                    allowed_refs={s["ref_id"] for s in signals},
                    kb_refs={s["kb_ref"] for s in signals},
                    facts=[c["name"] for c in pending_tarot["cards"]],
                    tarot_result=pending_tarot,
                    tarot_drawn=True,
                    kb_version=target.state.get("kb_version") or pending_tarot.get("kb_version"),
                )
                if kept_tarot:
                    selected["specialist_facts"] = {"tarot": kept_tarot}
            target.state = selected
            target.cache.clear()
            target.messages = [m for m in target.messages if m["role"] == "system"]
            session.reading = None
            session.birth_stale = True
            for message in session.messages:
                message["stale"] = True
        target.birth_binding = None
        target.birth_context = None
        target.birth_version_valid = None
        session.bound_birth = None

    def bind_birth(session, birth, *, authoritative=False):
        runtime = session.runtime
        target = runtime.session
        target.profile = runtime.store.get_profile(session.user_id)
        target.birth_binding = None
        if not birth.date and not authoritative:
            return
        values, location = birth_profile(birth)
        changed = any(target.profile.get(k) != v for k, v in values.items())
        if session.bound_birth is not None and session.bound_birth.canonical() != birth.canonical():
            invalidate_birth(session)
        if changed:
            target.profile = runtime.store.update_profile_fields(
                session.user_id, values, birth.evidence()
            )
        target.birth_binding = {"profile": values, "location": location}
        session.bound_birth = birth.model_copy(deep=True)
        if location:
            target.state.setdefault("locations", {})[location["location_id"]] = location

    def shared_safety(session):
        owner = session.owner or session
        owner.safety_pending = session.runtime.session.safety_pending
        for context in family(owner):
            context.runtime.session.safety_pending = owner.safety_pending

    def available(session):
        if session.lock.locked():
            raise HTTPException(409, "正在解读，请等待本轮完成。")

    def state(session):
        reading = session.reading
        if reading:
            reading = {
                **reading,
                "responses": session.runtime.store.reading_responses(
                    session.user_id, reading["reading_id"]
                ),
                "stale": reading_is_stale(session, reading.get("birth_context")),
            }
        owner = session.owner or session
        history, total = session.runtime.store.reading_page(session.user_id, limit=30)
        return {
            "system": session.system,
            "instance": instance,
            "account": owner.account,
            "session_epoch": session.runtime.session.id,
            "session_revision": session.session_revision,
            "birth_version": (session.owner or session).birth_version,
            "birth_stale": session.birth_stale,
            "followup_reading_id": session.runtime.session.pinned_reading_id,
            "provider": session.provider,
            "messages": session.messages,
            "birth": (session.owner or session).birth.model_dump(mode="json"),
            "reading": reading,
            "chart": session.chart,
            "name_analysis": session.name_analysis,
            "tarot_round": session.tarot_round,
            "history": history,
            "history_total": total,
            "busy": session.lock.locked(),
        }

    def reading_is_stale(session, context):
        return bool(context) and context.get("version") != (session.owner or session).birth_version

    @app.get("/api/session")
    async def session_info(
        request: Request,
        response: Response,
        provider: Literal["configured", "demo"] = "configured",
        system: SystemName = "auto",
    ):
        session = resolve(request.cookies.get(COOKIE, ""), provider)
        if session is None:
            if len(live_roots()) >= 64:
                raise HTTPException(503, {"code": "busy", "message": "当前会话过多，请稍后再试。"})
            key = secrets.token_urlsafe(32)
            user_id = "web-" + secrets.token_hex(16)
            session = BrowserSession(user_id, build(user_id, provider), provider)
            attach_progress(session)
            sessions[key] = session
            response.set_cookie(
                COOKIE,
                key,
                httponly=True,
                secure=public_origin is not None,
                samesite="strict",
                max_age=MAX_IDLE,
            )
        touch(session)
        return state(context_for(session, system))

    def attach_progress(session):
        def listen(record):
            label = progress_label(record)
            if label and session.progress_active:
                if session.progress.full():
                    session.progress.get_nowait()
                session.progress.put_nowait({"label": label})

        session.runtime.tracer.listeners.append(listen)

    def progress_queue(session, identity):
        if not identity:
            return session.progress
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identity):
            raise HTTPException(400, "进度请求编号无效")
        if identity == session.progress_id:
            return session.progress
        if identity not in session.progress_streams:
            if len(session.progress_streams) >= 8:
                raise HTTPException(429, "进度连接过多")
            session.progress_streams[identity] = asyncio.Queue(maxsize=128)
        return session.progress_streams[identity]

    @app.get("/api/progress")
    async def progress(request: Request, request_id: str = ""):
        session = get_session(request)
        queue = progress_queue(session, request_id)
        if request_id in session.progress_readers:
            raise HTTPException(409, "此请求已有进度连接")
        session.progress_readers.add(request_id)

        async def events():
            try:
                while not await request.is_disconnected():
                    if (
                        request_id == session.progress_id
                        and not session.progress_active
                        and queue.empty()
                    ):
                        yield "event: done\ndata: {}\n\n"
                        break
                    try:
                        item = await asyncio.wait_for(queue.get(), 15)
                    except TimeoutError:
                        yield ": ping\n\n"
                        continue
                    if item is None:
                        yield "event: done\ndata: {}\n\n"
                        break
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

            finally:
                session.progress_readers.discard(request_id)
                if session.progress_streams.get(request_id) is queue:
                    session.progress_streams.pop(request_id, None)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/chat")
    async def chat(body: ChatInput, request: Request):
        session = get_session(request, body.system)
        owner = session.owner or session
        available(session)
        async with session.lock:
            saved_target = None
            if body.reading_id:
                saved_target = session.runtime.store.get_reading(session.user_id, body.reading_id)
                if not saved_target:
                    raise HTTPException(404, "找不到这份解读。")
                if body.system != "auto" and body.system not in saved_target["systems_used"]:
                    raise HTTPException(422, "请在对应功能页面继续这份解读。")
            identity = request.headers.get("x-zhiming-progress", "")
            queue = progress_queue(session, identity)
            session.progress = queue
            session.progress_id = identity
            if identity:
                session.progress_streams.pop(identity, None)
            while not session.progress.empty():
                session.progress.get_nowait()
            session.progress_active = True
            session.progress.put_nowait({"label": "正在理解你的问题"})
            uses_birth = False
            birth_version = None
            try:
                if body.picks:
                    # The first draw opens the round; a reply within it keeps its question and
                    # takes the latest choice, as Session.choose_picks does for the reading.
                    session.tarot_round = {
                        "question": (session.tarot_round or {}).get("question", body.message),
                        "spread": body.spread,
                        "picks": list(body.picks),
                    }
                # The direct/demo chart path also passes safety before any computation.
                safety_profile = {}
                if body.birth.location_id:
                    safety_profile["tz"] = selected_region(body.birth.location_id)["tz"]
                safety = await session.runtime.safety_response(body.message, safety_profile)
                shared_safety(session)
                if safety is not None:
                    session.messages.extend(
                        [
                            {"role": "user", "text": body.message, "system": body.system},
                            {
                                "role": "assistant",
                                "text": safety.text,
                                "status": safety.status,
                                "system": body.system,
                            },
                        ]
                    )
                    return {**state(session), "busy": False}
                chart_question = None
                if not saved_target:
                    session.runtime.session.pinned_reading_id = None
                if body.system in BIRTH_SYSTEMS and not saved_target:
                    async with owner.birth_lock:
                        if "birth" in body.model_fields_set:
                            share_birth(
                                session,
                                body.birth,
                                expected_birth_version(request, body.expected_birth_version),
                            )
                        else:
                            body.birth = owner.birth.model_copy(deep=True)
                        birth_version = owner.birth_version
                        owner.active_birth_requests.add(session.system)
                        uses_birth = True
                if body.system in ("bazi", "astro") and not saved_target:
                    try:
                        session.chart = body.birth.chart(body.system)
                        session.chart["birth_version"] = birth_version
                    except NeedsInput as exc:
                        session.chart = None
                        chart_question = exc.question
                evidence = body.birth.evidence()
                message = body.message
                if evidence and body.system in BIRTH_SYSTEMS and not saved_target:
                    message += "\n\n我在出生信息表中填写的资料：" + evidence + "。"
                session.runtime.session.state["selected_systems"] = (
                    [body.system] if body.system != "auto" else None
                )
                session.runtime.session.state["selected_spread"] = (
                    body.spread if body.system == "tarot" else None
                )
                if body.system == "tarot":
                    message += (
                        "\n我选择的牌阵为："
                        + {
                            "single": "单张牌",
                            "three_card": "三张牌",
                            "decision": "A/B二选一决策牌阵",
                        }[body.spread]
                        + "。"
                    )
                session.runtime.session.pinned_reading_id = body.reading_id
                if saved_target:
                    try:
                        restored = await session.runtime.registry.run(
                            "read_reading",
                            ReadInput(reading_id=body.reading_id),
                            session.runtime.session,
                        )
                    except (FileNotFoundError, ValueError) as exc:
                        raise HTTPException(
                            409, "这份解读的历史数据暂时无法恢复，请检查对应知识库版本。"
                        ) from exc
                    if not restored.ok:
                        raise HTTPException(409, "无法恢复这份解读，请刷新后重试。")
                    # run_turn appends the pending user question after this restoration.
                    session.runtime.session.state["question_message_index"] = len(
                        session.runtime.session.user_messages
                    )
                    session.reading = {
                        "view": body.system,
                        "reading_id": body.reading_id,
                        "question": saved_target["question"],
                        "output": saved_target["output_json"],
                        "tarot": saved_target["tarot_json"],
                        "calculations": saved_target.get("calculations_json"),
                        "birth_context": saved_target.get("birth_context_json"),
                        "historical": True,
                    }
                    session.runtime.session.birth_binding = None
                    session.runtime.session.birth_version_valid = None
                    message += f"\n本次只追问历史解读 {body.reading_id}；请先read_reading读取该记录，不要重新计算。"
                elif body.system in BIRTH_SYSTEMS:
                    bind_birth(session, body.birth, authoritative=body.system in ("bazi", "astro"))
                    session.runtime.session.birth_context = {
                        "version": birth_version,
                        "birth": body.birth.model_dump(mode="json"),
                    }
                    session.runtime.session.birth_version_valid = lambda: (
                        owner.birth_version == birth_version
                    )
                session.messages.append(
                    {"role": "user", "text": body.message, "system": body.system}
                )
                if session.provider == "demo" and (
                    body.system in DEMO_UNSUPPORTED
                    or (saved_target and body.system in ("bazi", "astro"))
                ):
                    # The offline demo only draws tarot; never answer a dream or name with cards.
                    session.messages.append(
                        {
                            "role": "assistant",
                            "text": DEMO_UNSUPPORTED.get(
                                body.system,
                                "历史解读已恢复；离线演示仅支持排盘，继续解读请切换真实模型后从足迹选择这份记录。",
                            ),
                            "status": "demo_unsupported",
                            "system": body.system,
                        }
                    )
                    return {**state(session), "busy": False}
                if session.provider == "demo" and body.system in ("bazi", "astro"):
                    if chart_question:
                        answer = chart_question
                    elif body.system == "bazi":
                        pillars = session.chart["result"]["pillars"]
                        answer = (
                            "你的"
                            + ("四柱" if "time" in pillars else "三柱")
                            + "为："
                            + "，".join(
                                label + str(pillars[key])
                                for key, label in (
                                    ("year", "年柱"),
                                    ("month", "月柱"),
                                    ("day", "日柱"),
                                    ("time", "时柱"),
                                )
                                if key in pillars
                            )
                            + "。日主为"
                            + session.chart["result"]["day_master"]
                            + "。"
                        )
                    else:
                        answer = (
                            "本命星盘已计算："
                            + "，".join(
                                p["body_zh"] + "在" + p["sign_zh"] + "座"
                                for p in session.chart["result"]["planets"][:2]
                            )
                            + "。"
                        )
                    answer += "\n当前为离线排盘，未调用模型解读；深度咨询可切换真实模型。"
                    session.messages.append(
                        {
                            "role": "assistant",
                            "text": answer,
                            "status": "chart_only",
                            "system": body.system,
                        }
                    )
                    return {**state(session), "busy": False}
                # Set on every request, so a choice never carries over to a later question.
                session.runtime.session.choose_picks(tuple(body.picks) if body.picks else None)
                try:
                    outcome = await asyncio.wait_for(
                        session.runtime.turn(message, safety_checked=True), timeout=360
                    )
                    session.last_birth = evidence
                except TimeoutError:
                    outcome = failure(
                        session.runtime.session,
                        "timeout",
                        "request_timeout",
                        "本轮达到请求时限，请稍后继续或缩小问题范围。",
                    )
                except Exception:
                    logger.exception("Browser turn failed")
                    outcome = None
                    answer = "这次解读暂时未能完成。请检查模型连接，或切换离线演示后重试。"
                if outcome:
                    answer = outcome.text or "本轮未形成解读，你可以补充信息后继续。"
                    if outcome.data.get("reading"):
                        session.tarot_round = None
                        saved = session.runtime.store.get_reading(
                            session.user_id, outcome.data["reading_id"]
                        )
                        session.reading = {
                            "view": body.system,
                            "reading_id": outcome.data["reading_id"],
                            "question": saved.get("question") if saved else None,
                            "output": outcome.data["reading"],
                            "tarot": saved.get("tarot_json") if saved else None,
                            "calculations": saved.get("calculations_json") if saved else None,
                            "birth_context": saved.get("birth_context_json") if saved else None,
                            "historical": bool(saved_target),
                        }
                        session.birth_stale = False
                session.messages.append(
                    {
                        "role": "assistant",
                        "text": answer,
                        "status": outcome.status if outcome else "error",
                        "failure": outcome.data.get("failure") if outcome else None,
                        "system": body.system,
                    }
                )
                session.touched = time.monotonic()
            finally:
                if uses_birth:
                    async with owner.birth_lock:
                        owner.active_birth_requests.discard(session.system)
                session.progress_active = False
                if session.progress.full():
                    session.progress.get_nowait()
                session.progress.put_nowait(None)
        return state(session)

    @app.post("/api/new")
    async def new_chat(body: NewInput, request: Request):
        session = get_session(request, body.system)
        available(session)
        async with session.lock:
            await restart(session, body.provider)
        return state(session)

    async def restart(session, provider):
        """Start this feature's conversation afresh; the caller holds its lock."""
        replacement = build(session.user_id, provider)
        replacement.session.safety_pending = session.runtime.session.safety_pending
        await close(session)
        session.runtime = replacement
        session.session_revision += 1
        attach_progress(session)
        session.provider = provider
        session.messages.clear()
        session.last_birth = ""
        session.reading = None
        session.chart = None
        session.tarot_round = None
        session.name_analysis = None
        session.bound_birth = None
        session.birth_stale = False

    @app.get("/api/readings/{reading_id}")
    async def reading(reading_id: str, request: Request):
        session = get_session(request)
        saved = session.runtime.store.get_reading(session.user_id, reading_id)
        if not saved:
            raise HTTPException(404, "找不到这份解读。")
        return {
            "reading_id": reading_id,
            "question": saved["question"],
            "output": saved["output_json"],
            "tarot": saved["tarot_json"],
            "calculations": saved.get("calculations_json"),
            "birth_context": saved.get("birth_context_json"),
            "historical": True,
            "stale": reading_is_stale(session, saved.get("birth_context_json")),
            "responses": session.runtime.store.reading_responses(session.user_id, reading_id),
        }

    @app.delete("/api/session")
    async def forget(request: Request):
        session = get_session(request)
        for context in family(session):
            available(context)
        async with session.lock:
            try:
                session.runtime.forget(compact=False)
            except OSError as exc:
                raise records_not_removed() from exc
            checkpoint_later()
            for context in family(session):
                context.session_revision += 1
                if context is not session:
                    # The database and traces are already removed for the shared identity.
                    context.runtime.session.profile = {"version": 0}
                    context.runtime.session.messages = [
                        {"role": "system", "content": context.runtime.system_prompt}
                    ]
                    context.runtime.session.state.clear()
                    context.runtime.session.cache.clear()
                    context.runtime.session.user_messages.clear()
                context.runtime.session.birth_binding = None
                context.runtime.session.pinned_reading_id = None
                context.runtime.session.birth_context = None
                context.runtime.session.birth_version_valid = None
                context.bound_birth = None
                context.birth_stale = False
                context.messages.clear()
                context.last_birth = ""
                context.reading = context.chart = context.tarot_round = context.name_analysis = None
            owner = session.owner or session
            owner.birth = BirthInfo()
            owner.birth_version += 1
            # Keep the revision moving forward for pages that reload after a restart.
            session.runtime.store.save_web_birth(
                session.user_id, owner.birth.model_dump(mode="json"), owner.birth_version
            )
        return state(session)

    # ---------- History management ----------

    @app.get("/api/history")
    async def history_page(
        request: Request,
        system: Literal["", "bazi", "astro", "tarot", "name", "dream", "daily"] = "",
        q: str = Query("", max_length=100),
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=50),
    ):
        # The filter names a system; the session itself is always the shared root.
        session = get_session(request, "auto")
        items, total = session.runtime.store.reading_page(
            session.user_id, system or None, q, offset, limit
        )
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    @app.delete("/api/readings/{reading_id}")
    async def delete_reading(reading_id: str, request: Request):
        session = get_session(request, "auto")
        async with every_lock(session):
            if not session.runtime.store.delete_reading(session.user_id, reading_id):
                raise HTTPException(404, "找不到这份解读，可能已被删除。")
            detach_readings(session, {reading_id})
        checkpoint_later()
        return {"deleted": [reading_id]}

    @app.delete("/api/readings")
    async def delete_all_readings(request: Request):
        session = get_session(request, "auto")
        async with every_lock(session):
            deleted = session.runtime.store.delete_readings(session.user_id)
            detach_readings(session, set(deleted))
        checkpoint_later()
        return {"deleted": deleted}

    @asynccontextmanager
    async def every_lock(session):
        """One critical section over every feature of the session family: no conversation
        runs, starts or reads its state while records are removed. A busy feature refuses
        the deletion instead of being waited for."""
        contexts = family(session)
        for context in contexts:
            available(context)
        async with AsyncExitStack() as stack:
            # Always the same order (root first); no other path holds more than one lock.
            for context in contexts:
                await stack.enter_async_context(context.lock)
            yield

    def detach_readings(root_session, reading_ids):
        """Under every_lock: nothing on the page, in a conversation or in the model's memory
        note may refer to deleted records. Clears state in memory; never rebuilds a runtime,
        so it cannot fail half-way for want of a model configuration."""
        scrub_traces(root_session.user_id, reading_ids)
        for context in family(root_session):
            if reading_ids:
                # Earlier rounds survive in messages even when the active reading changes.
                # Without per-message provenance, reset every loaded conversation rather
                # than sending deleted questions or answers to the model again.
                clear_conversation(context)
            refresh_memory(context)

    def clear_conversation(context):
        """What a new conversation starts with, keeping the runtime and its model client."""
        target = context.runtime.session
        target.messages = [m for m in target.messages if m["role"] == "system"]
        target.state.clear()
        target.cache.clear()
        target.user_messages.clear()
        target.pending_picks = None
        target.pinned_reading_id = None
        target.birth_binding = None
        target.birth_context = None
        target.birth_version_valid = None
        context.session_revision += 1
        context.messages.clear()
        context.last_birth = ""
        context.reading = None
        context.tarot_round = None
        context.bound_birth = None
        context.birth_stale = False

    def refresh_memory(context):
        target = context.runtime.session
        recent = context.runtime.store.recent_readings(context.user_id)
        for message in target.messages:
            if message["role"] == "system" and str(message.get("content", "")).startswith(
                MEMORY_NOTE
            ):
                message["content"] = memory_note(target.profile, recent)

    def scrub_traces(user_id, reading_ids):
        """Best effort: drop trace records tagged with deleted readings."""
        tracer = Tracer(root / config["paths"]["runs"])
        directory = tracer.user_dir(user_id).resolve()
        if not reading_ids or not directory.is_relative_to(tracer.root.resolve()):
            return
        for path in directory.glob("*.jsonl") if directory.is_dir() else ():
            try:
                lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
                kept = []
                for line in lines:
                    try:
                        tagged = json.loads(line).get("reading_id") in reading_ids
                    except (ValueError, AttributeError):
                        tagged = False
                    if not tagged:
                        kept.append(line)
                if len(kept) == len(lines):
                    continue
                if kept:
                    temporary = path.with_suffix(".scrub")
                    temporary.write_text("".join(kept), encoding="utf-8")
                    temporary.replace(path)
                else:
                    path.unlink()
            except OSError:
                logger.exception("Could not remove trace records of deleted readings")

    @app.get("/api/export")
    async def export_records(request: Request):
        session = get_session(request, "auto")
        owner = session.owner or session
        account = accounts().get(owner.user_id) if owner.account else None
        payload = {
            "format": "zhiming-export",
            "format_version": 2,
            "exported_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
            "scope": EXPORT_SCOPE,
            "account": {k: v for k, v in account.items() if k != "user_id"} if account else None,
            **session.runtime.store.export_user(session.user_id),
        }
        day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        return Response(
            json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="zhiming-records-{day}.json"',
                "Cache-Control": "no-store",
            },
        )

    # ---------- Accounts ----------

    def client_of(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def throttle(*limits):
        """limits: (key, attempts, window seconds); refuse while any is exhausted."""
        wait = max(limiter.retry_after(key, count, window) for key, count, window in limits)
        if wait:
            minutes = max(1, -(-wait // 60))
            raise HTTPException(
                429,
                {"code": "rate_limited", "message": f"尝试次数过多，请约 {minutes} 分钟后再试。"},
                headers={"Retry-After": str(wait)},
            )

    def require_account(session):
        owner = session.owner or session
        if owner.account is None:
            raise HTTPException(403, {"code": "account_required", "message": "请先登录账号。"})
        return owner

    def idle_guest(request: Request):
        """The browser's guest session, checked to be free before its records move."""
        current = sessions.get(request.cookies.get(COOKIE, ""))
        if current is None or current.account is not None:
            return None
        for context in family(current):
            if context.lock.locked():
                raise HTTPException(
                    409,
                    {"code": "busy", "message": "访客会话正在解读，请等待本轮完成后再登录。"},
                )
        return current

    def same_birth(first, second):
        try:
            return (
                BirthInfo.model_validate(first).canonical()
                == BirthInfo.model_validate(second).canonical()
            )
        except ValueError:
            return False

    def hand_over(guest, user_id, keep):
        """Import guest records without moving the originals before commit. Failed imports
        keep their originals and durably queue any unremovable copies for cleanup."""
        if guest is None:
            return {"readings": 0, "adopted_birth": False}
        if not keep:
            try:
                # Traces go first; the records are only deleted once they are gone.
                guest.runtime.forget(compact=False)
            except OSError as exc:
                raise records_not_removed() from exc
            checkpoint_later()
            return {"readings": 0, "adopted_birth": False}
        try:
            copies = copy_traces(guest.runtime.store, guest.user_id, user_id)
        except OSError as exc:
            raise HTTPException(
                503,
                {
                    "code": "records_not_moved",
                    "message": "访客记录暂时无法转入账号，原记录已保留；临时副本将自动清理，请稍后重试。",
                },
            ) from exc
        try:
            moved = guest.runtime.store.merge_user(
                guest.user_id, user_id, same_birth, trace_copies=copies
            )
        except Exception:
            discard_trace_copies(guest.runtime.store, guest.user_id, user_id)
            raise
        if not remove_trace_dir(guest.user_id):
            # Something is left in the guest's trace directory: an expired lease makes the
            # regular guest cleanup remove it, instead of leaving it behind for good.
            guest.runtime.store.touch_web_identity(guest.user_id, time.time())
        checkpoint_later()
        live = accounts_live.get(user_id)
        if live is not None and moved["adopted_birth"]:
            # Signed in elsewhere with no birth yet: show the adopted one there too.
            restore_birth(live)
        return moved

    def records_not_removed():
        return HTTPException(
            503,
            {
                "code": "records_not_removed",
                "message": "记录暂时无法删除，没有做任何改动，请稍后重试。",
            },
        )

    def trace_dirs(source, target):
        tracer = Tracer(root / config["paths"]["runs"])
        base = tracer.root.resolve()
        old, new = tracer.user_dir(source).resolve(), tracer.user_dir(target).resolve()
        if not old.is_relative_to(base) or not new.is_relative_to(base):
            raise OSError("trace directory outside the trace root")
        return old, new

    def copy_traces(store, source, target):
        """Keep originals until the database commits. Journal copies before touching files,
        so even a failed rollback or a process crash has a durable cleanup path."""
        old, new = trace_dirs(source, target)
        if not old.is_dir():
            return []
        copies = []
        for path in sorted(old.glob("*.jsonl")):
            # Never reuse another attempt's destination, even when its cleanup is pending.
            destination = new / f"{path.stem}-{secrets.token_hex(16)}.jsonl"
            copies.append((path, destination))
        store.stage_trace_copies(source, target, [destination.name for _, destination in copies])
        try:
            new.mkdir(parents=True, exist_ok=True)
            for path, destination in copies:
                shutil.copyfile(path, destination)
        except OSError:
            discard_trace_copies(store, source, target)
            raise
        return [destination.name for _, destination in copies]

    def discard_trace_copies(store, source=None, target=None):
        """Retry uncommitted imports at startup and during ordinary cleanup. Queue entries
        survive failed unlink calls and deletion of either identity's business records."""
        for copy in store.pending_trace_copies():
            if source is not None and copy["source_user_id"] != source:
                continue
            if target is not None and copy["target_user_id"] != target:
                continue
            try:
                _, directory = trace_dirs(copy["source_user_id"], copy["target_user_id"])
                filename = copy["filename"]
                destination = (directory / filename).resolve()
                if Path(filename).name != filename or destination.parent != directory:
                    raise OSError("invalid trace copy path")
                destination.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not remove an uncommitted trace copy; cleanup will retry")
            else:
                store.clear_trace_copy(copy["target_user_id"], filename)

    def remove_trace_dir(user_id):
        old, _ = trace_dirs(user_id, user_id)
        try:
            if old.exists():
                shutil.rmtree(old)
        except OSError:
            logger.exception("Could not remove the guest trace directory")
            return False
        return True

    async def end_login(key):
        accounts().revoke(key)
        current = sessions.pop(key, None)
        extended.pop(key, None)
        if current is not None and not keys_of(current):
            if not any(c.lock.locked() for c in family(current)):
                await release(current)

    def signed_in(account, moved, status=200):
        now = time.time()
        token = accounts().open_session(account["user_id"], now, now + ACCOUNT_IDLE)
        response = JSONResponse(
            {"account": public_account(account), "moved_readings": moved["readings"]},
            status_code=status,
        )
        response.set_cookie(
            COOKIE,
            token,
            httponly=True,
            secure=public_origin is not None,
            samesite="strict",
            max_age=ACCOUNT_IDLE,
        )
        return response

    @app.get("/api/account")
    async def account_info(request: Request):
        """Who this browser is, without creating a session."""
        key = request.cookies.get(COOKIE, "")
        current = sessions.get(key)
        if current is None:
            user_id = accounts().session_user(key, time.time()) if key else None
            account = accounts().get(user_id) if user_id else None
            return {"account": public_account(account) if account else None, "guest": None}
        if current.account is not None:
            return {"account": current.account, "guest": None}
        _, total = current.runtime.store.reading_page(current.user_id, limit=1)
        return {
            "account": None,
            "guest": {"readings": total, "birth": bool(current.birth.date)},
        }

    @app.post("/api/account/register")
    async def register(body: Registration, request: Request):
        client = "register:" + client_of(request)
        throttle((client, 10, 3600))
        if not body.accept_privacy:
            raise HTTPException(
                422,
                {"code": "privacy_consent_required", "message": "请先阅读并同意《隐私说明》。"},
            )
        username = check_username(body.username)
        check_password(body.password, username)
        # Counted from here: typos above are free, probing for taken names is not.
        limiter.record(client)
        if accounts().credentials(username):
            raise AccountError("username_taken", "该账号名已被使用，请换一个。")
        password_hash = await asyncio.to_thread(hash_password, body.password)
        # From here on nothing awaits until the records have moved.
        guest = idle_guest(request)
        account = accounts().create(username, password_hash)
        key = request.cookies.get(COOKIE, "")
        previous = sessions.get(key)
        try:
            moved = hand_over(guest, account["user_id"], body.keep_guest_records)
        except BaseException:
            # Nothing moved: remove the new, empty account so the name can be used again.
            accounts().delete(account["user_id"])
            raise
        if guest is not None:
            await release(guest)
        if key and (previous is None or previous.account is not None):
            # Replace any login this browser held, loaded or only stored.
            await end_login(key)
        return signed_in(account, moved, status=201)

    @app.post("/api/account/login")
    async def sign_in(body: Credentials, request: Request):
        name = "login:" + username_key(body.username)
        client = "login-client:" + client_of(request)
        throttle((name, 5, 900), (client, 20, 900))
        found = accounts().credentials(body.username)
        if found is None:
            await asyncio.to_thread(dummy_verify, body.password)
        if found is None or not await asyncio.to_thread(verify_password, body.password, found[1]):
            limiter.record(name)
            limiter.record(client)
            raise HTTPException(
                401, {"code": "invalid_credentials", "message": "账号或密码不正确。"}
            )
        limiter.reset(name)
        account = found[0]
        guest = idle_guest(request)
        key = request.cookies.get(COOKIE, "")
        previous = sessions.get(key)
        moved = hand_over(guest, account["user_id"], body.keep_guest_records)
        if guest is not None:
            await release(guest)
        if key and (previous is None or previous.account is not None):
            # Replace any login this browser held, loaded or only stored.
            await end_login(key)
        return signed_in(account, moved)

    @app.post("/api/account/logout")
    async def sign_out(request: Request):
        key = request.cookies.get(COOKIE, "")
        current = sessions.get(key)
        if current is not None and current.account is None:
            raise HTTPException(400, {"code": "not_signed_in", "message": "当前是访客身份。"})
        if key:
            await end_login(key)
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, secure=public_origin is not None, samesite="strict")
        return response

    @app.post("/api/account/password")
    async def change_password(body: PasswordChange, request: Request):
        session = get_session(request, "auto")
        owner = require_account(session)
        attempts = "secret:" + owner.user_id
        throttle((attempts, 5, 900))
        current = accounts().password_hash(owner.user_id) or ""
        if not await asyncio.to_thread(verify_password, body.current_password, current):
            limiter.record(attempts)
            raise HTTPException(403, {"code": "wrong_password", "message": "当前密码不正确。"})
        check_password(body.new_password, owner.account["username"])
        new_hash = await asyncio.to_thread(hash_password, body.new_password)
        accounts().set_password(owner.user_id, new_hash)
        limiter.reset(attempts)
        key = request.cookies.get(COOKIE, "")
        ended = set(accounts().revoke_others(owner.user_id, key))
        for other in [k for k, s in sessions.items() if s is owner and token_digest(k) in ended]:
            sessions.pop(other, None)
        return {"ok": True, "signed_out_elsewhere": len(ended)}

    @app.post("/api/account/delete")
    async def delete_account(body: PasswordConfirmation, request: Request):
        session = get_session(request, "auto")
        owner = require_account(session)
        attempts = "secret:" + owner.user_id
        throttle((attempts, 5, 900))
        current = accounts().password_hash(owner.user_id) or ""
        if not await asyncio.to_thread(verify_password, body.password, current):
            limiter.record(attempts)
            raise HTTPException(403, {"code": "wrong_password", "message": "密码不正确。"})
        async with every_lock(owner):
            # Traces, then records, then the account: a failure leaves the account usable.
            try:
                owner.runtime.forget(compact=False)
            except OSError as exc:
                raise records_not_removed() from exc
            accounts().delete(owner.user_id)
        checkpoint_later()
        await release(owner)
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE, secure=public_origin is not None, samesite="strict")
        return response

    @app.get("/api/locations")
    async def locations(parent: str | None = None):
        return {"options": region_options(parent)}

    @app.get("/api/locations/{identity}")
    async def location(identity: str):
        try:
            return selected_region(identity)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/chart")
    async def chart(body: ChartInput, request: Request):
        session = get_session(request, body.system)
        available(session)
        async with session.lock:
            if session.runtime.session.safety_pending:
                return {
                    **state(session),
                    "busy": False,
                    "chart": None,
                    "question": "请先在对话中确认此刻安全，再继续排盘。",
                    "code": "safety_confirmation_required",
                }
            async with (session.owner or session).birth_lock:
                share_birth(
                    session,
                    body.birth,
                    expected_birth_version(request, body.expected_birth_version),
                )
                session.chart = None
                try:
                    session.chart = body.birth.chart(body.system)
                    session.chart["birth_version"] = (session.owner or session).birth_version
                except NeedsInput as exc:
                    return {
                        **state(session),
                        "busy": False,
                        "question": exc.question,
                        "code": exc.code,
                    }
        return state(session)

    @app.put("/api/birth")
    async def save_birth(body: BirthInfo, request: Request):
        session = get_session(request)
        available(session)
        async with session.lock:
            async with (session.owner or session).birth_lock:
                share_birth(session, body, expected_birth_version(request))
        return state(session)

    @app.post("/api/name")
    async def name_grids(body: NameQuery, request: Request):
        session = get_session(request, "name")
        available(session)
        if session.runtime.session.safety_pending:
            return {
                "result": None,
                "question": "请先在对话中确认此刻安全，再继续测名。",
                "code": "safety_confirmation_required",
            }
        try:
            result = analyze(body.surname, body.given, body.forms)
        except UnihanMissing as exc:
            raise HTTPException(503, "缺少康熙笔画数据，请先运行 scripts.fetch_data。") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if result["status"] != "ok":
            chars = "、".join(f"“{c}”" for c in result["unknown"])
            return {
                "result": None,
                "question": f"无法确定{chars}的康熙笔画，请确认写法（可提供繁体或常用异体）；不会猜测笔画。",
                "code": "unknown_name_char",
            }
        result["elements"] = {grid: element(number) for grid, number in result["grids"].items()}
        # Keep the original choices so confirmed variants can still be changed after navigation.
        choices = (
            analyze(body.surname, body.given).get("ambiguities", [])
            if body.forms
            else result["ambiguities"]
        )
        session.name_analysis = {"result": result, "forms": dict(body.forms), "choices": choices}
        return {"result": result}

    @app.post("/api/almanac")
    async def day_almanac(body: AlmanacInput, request: Request):
        session = get_session(request, "daily")
        day = body.date or datetime.now(ZoneInfo("Asia/Shanghai")).date()
        day_master, question = None, None
        if body.birth.date and body.birth.location_id:
            if session.runtime.session.safety_pending:
                question = "请先在对话中确认此刻安全，再查看个人流日。"
            else:
                try:
                    day_master = body.birth.chart("bazi")["result"]["day_master"] or None
                except NeedsInput as exc:
                    question = exc.question
        return {**almanac(day, day_master, session.runtime.kb), "question": question}

    @app.get("/")
    async def index(request: Request):
        # A live browser session or a kept login skips the entrance and returns to the hall.
        key = request.cookies.get(COOKIE, "")
        if key in sessions or (key and accounts().session_user(key, time.time())):
            return RedirectResponse("/ask", status_code=303)
        # Never cache the entrance: the answer depends on whether the session is alive.
        return FileResponse(STATIC / "login.html", headers={"Cache-Control": "no-store"})

    @app.get("/login", include_in_schema=False)
    async def login():
        return FileResponse(STATIC / "login.html", headers={"Cache-Control": "no-store"})

    @app.get("/privacy", include_in_schema=False)
    async def privacy():
        return FileResponse(STATIC / "privacy.html")

    def page(filename):
        async def serve():
            return FileResponse(STATIC / filename)

        return serve

    for slug, filename in PAGES.items():
        app.add_api_route(f"/{slug}", page(filename), methods=["GET"], include_in_schema=False)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="知命 · 本地网页版")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--public-origin", help="朋友体验的 HTTPS 地址（不含路径）")
    parser.add_argument("--share-password-file", type=Path, help="本地访问口令文件")
    args = parser.parse_args()
    password = (
        args.share_password_file.read_text(encoding="utf-8").strip()
        if args.share_password_file
        else None
    )
    uvicorn.run(
        create_web_app(public_origin=args.public_origin, share_password=password),
        host="127.0.0.1",
        port=args.port,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )
