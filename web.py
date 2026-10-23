"""Local browser interface. Run with .venv/Scripts/python.exe web.py."""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import re
import secrets
import shutil
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date as CalendarDate
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import yaml
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from lunar_python import Solar
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import ROOT, Runtime, create_runtime
from common.regions import region_options, selected_region
from common.time_utils import NeedsInput
from harness.trace import Tracer
from memory.store import Store
from plugins.astro.calculator import natal_chart
from plugins.bazi.calculator import GAN, GAN_WX, WX, compute_bazi, ten_god
from plugins.name.strokes import UnihanMissing
from plugins.name.tools import HAN
from plugins.name.wuge import analyze, element
from plugins.tarot.draw import valid_picks

STATIC = Path(__file__).with_name("web_static")
COOKIE = "zhiming_session"
MAX_IDLE = 12 * 3600
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
            datetime.strptime(value, "%H:%M")
        return value

    @model_validator(mode="after")
    def consistent(self):
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
        if location["tz"] == "Asia/Urumqi" and not self.clock_tz:
            raise NeedsInput("confirm_clock_timezone", "请确认出生钟表使用北京时间还是新疆时间。")
        inputs = dict(
            birth_local=self.date.isoformat() + ("T" + self.time if self.time else ""),
            time_known=bool(self.time) and not self.unknown_time,
            tz=self.clock_tz or location["tz"],
            lon=location["lon"],
        )
        if system == "bazi":
            result = compute_bazi(
                **inputs,
                gender=self.gender or None,
                true_solar_time=self.true_solar_time,
                zishi_rule=self.zishi_rule,
            )
        else:
            result = natal_chart(**inputs, lat=location["lat"])
        return dict(
            system=system, result=result, location=location, birth=self.model_dump(mode="json")
        )


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)
    system: Literal["auto", "bazi", "astro", "tarot", "name", "dream", "daily"] = "auto"
    birth: BirthInfo = Field(default_factory=BirthInfo)
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


class ChartInput(BaseModel):
    system: Literal["bazi", "astro"]
    birth: BirthInfo


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
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    touched: float = field(default_factory=time.monotonic)


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
    sessions: dict[str, BrowserSession] = {}
    cleanup_lock = asyncio.Lock()
    config = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))

    async def purge_expired(adopt: bool = False):
        async with cleanup_lock:
            store = Store(root / config["paths"]["app_db"])
            try:
                now = time.time()
                if adopt:
                    # Pre-lease records exist only before the first start of this version.
                    store.adopt_web_identities(now + MAX_IDLE)
                for user_id in store.expired_web_identities(now):
                    active = [(k, s) for k, s in sessions.items() if s.user_id == user_id]
                    if any(s.lock.locked() for _, s in active):
                        continue
                    try:
                        for key, session in active:
                            sessions.pop(key, None)
                            await close(session)
                        # Trace first: forget() also drops the deadline row, so any failure
                        # before it leaves the identity listed and the next pass retries.
                        tracer = Tracer(root / config["paths"]["runs"])
                        directory = tracer.user_dir(user_id).resolve()
                        if directory.is_relative_to(tracer.root.resolve()) and directory.exists():
                            shutil.rmtree(directory)
                        store.forget(user_id)
                    except Exception:
                        logger.exception("Could not remove an expired browser identity")
            finally:
                store.close()

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
        for session in sessions.values():
            await close(session)
        sessions.clear()

    app = FastAPI(title="知命", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if share_credentials is not None:
            scheme, _, token = request.headers.get("authorization", "").partition(" ")
            try:
                credentials = base64.b64decode(token, validate=True)
            except (ValueError, binascii.Error):
                credentials = b""
            if scheme.lower() != "basic" or not secrets.compare_digest(
                credentials, share_credentials
            ):
                return JSONResponse(
                    {"detail": "请输入朋友体验的用户名和访问口令"},
                    status_code=401,
                    headers={
                        "WWW-Authenticate": 'Basic realm="ZhiMing Friends", charset="UTF-8"',
                        "Cache-Control": "no-store",
                    },
                )
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            expected_origin = public_origin or str(request.base_url).rstrip("/")
            if origin and origin != expected_origin:
                return JSONResponse({"detail": "请从知命页面发起请求"}, status_code=403)
            if request.headers.get("x-zhiming-client") != "web":
                return JSONResponse({"detail": "请求来源无效"}, status_code=403)
        await purge_safely()
        response = await call_next(request)
        key = request.cookies.get(COOKIE, "")
        session = sessions.get(key)
        if session is not None:
            touch(session)
            response.set_cookie(
                COOKIE,
                key,
                httponly=True,
                secure=public_origin is not None,
                samesite="strict",
                max_age=MAX_IDLE,
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

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
        session.runtime.store.touch_web_identity(session.user_id, time.time() + MAX_IDLE)

    def get_session(request: Request):
        session = sessions.get(request.cookies.get(COOKIE, ""))
        if session is None:
            raise HTTPException(401, "会话已过期，请刷新页面重新开始。")
        touch(session)
        return session

    def available(session):
        if session.lock.locked():
            raise HTTPException(409, "正在解读，请等待本轮完成。")

    def state(session):
        return {
            "provider": session.provider,
            "messages": session.messages,
            "birth": session.birth.model_dump(mode="json"),
            "reading": session.reading,
            "chart": session.chart,
            "history": session.runtime.store.reading_history(session.user_id, limit=30),
            "busy": session.lock.locked(),
        }

    @app.get("/api/session")
    async def session_info(
        request: Request,
        response: Response,
        provider: Literal["configured", "demo"] = "configured",
    ):
        session = sessions.get(request.cookies.get(COOKIE, ""))
        if session is None:
            if len(sessions) >= 64:
                raise HTTPException(503, "当前会话过多，请稍后再试。")
            key = secrets.token_urlsafe(32)
            user_id = "web-" + secrets.token_hex(16)
            session = BrowserSession(user_id, build(user_id, provider), provider)
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
        return state(session)

    @app.post("/api/chat")
    async def chat(body: ChatInput, request: Request):
        session = get_session(request)
        available(session)
        async with session.lock:
            # The direct/demo chart path also passes safety before any computation.
            safety_profile = {}
            if body.birth.location_id:
                safety_profile["tz"] = selected_region(body.birth.location_id)["tz"]
            safety = await session.runtime.safety_response(body.message, safety_profile)
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
            if body.system in ("bazi", "astro"):
                try:
                    session.chart = body.birth.chart(body.system)
                except NeedsInput as exc:
                    session.chart = None
                    chart_question = exc.question
            evidence = body.birth.evidence()
            message = body.message
            if evidence and body.system in BIRTH_SYSTEMS:
                message += "\n\n我在出生信息表中填写的资料：" + evidence + "。"
            if body.system != "auto":
                message += "\n本次希望使用" + SYSTEM_LABELS[body.system] + "来解读。"
            if body.system == "tarot":
                message += (
                    "\n我选择的牌阵为："
                    + {"single": "单张牌", "three_card": "三张牌", "decision": "A/B二选一决策牌阵"}[
                        body.spread
                    ]
                    + "。"
                )
            session.birth = body.birth
            session.messages.append({"role": "user", "text": body.message, "system": body.system})
            if session.provider == "demo" and body.system in DEMO_UNSUPPORTED:
                # The offline demo only draws tarot; never answer a dream or name with cards.
                session.messages.append(
                    {
                        "role": "assistant",
                        "text": DEMO_UNSUPPORTED[body.system],
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
                outcome = None
                answer = "本轮解读超时，已保留对话。你可以稍后继续。"
            except Exception:
                logger.exception("Browser turn failed")
                outcome = None
                answer = "这次解读暂时未能完成。请检查模型连接，或切换离线演示后重试。"
            if outcome:
                answer = outcome.text or "本轮未形成解读，你可以补充信息后继续。"
                if outcome.data.get("reading"):
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
                    }
            session.messages.append(
                {
                    "role": "assistant",
                    "text": answer,
                    "status": outcome.status if outcome else "error",
                    "system": body.system,
                }
            )
            session.touched = time.monotonic()
        return state(session)

    @app.post("/api/new")
    async def new_chat(body: NewInput, request: Request):
        session = get_session(request)
        available(session)
        async with session.lock:
            replacement = build(session.user_id, body.provider)
            replacement.session.safety_pending = session.runtime.session.safety_pending
            await close(session)
            session.runtime = replacement
            session.provider = body.provider
            session.messages.clear()
            session.last_birth = ""
            session.reading = None
            session.chart = None
        return state(session)

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
        }

    @app.delete("/api/session")
    async def forget(request: Request):
        session = get_session(request)
        available(session)
        async with session.lock:
            session.runtime.forget()
            session.messages.clear()
            session.birth = BirthInfo()
            session.last_birth = ""
            session.reading = None
            session.chart = None
        return state(session)

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
        session = get_session(request)
        available(session)
        async with session.lock:
            if session.runtime.session.safety_pending:
                return {
                    "chart": None,
                    "question": "请先在对话中确认此刻安全，再继续排盘。",
                    "code": "safety_confirmation_required",
                }
            session.birth = body.birth
            session.chart = None
            try:
                session.chart = body.birth.chart(body.system)
            except NeedsInput as exc:
                return {"chart": None, "question": exc.question, "code": exc.code}
        return {"chart": session.chart}

    @app.put("/api/birth")
    async def save_birth(body: BirthInfo, request: Request):
        session = get_session(request)
        available(session)
        async with session.lock:
            if body != session.birth:
                # A chart drawn from the previous birth data no longer belongs to this profile.
                session.chart = None
            session.birth = body
        return {"birth": session.birth.model_dump(mode="json"), "chart": session.chart}

    @app.post("/api/name")
    async def name_grids(body: NameQuery, request: Request):
        session = get_session(request)
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
        return {"result": result}

    @app.post("/api/almanac")
    async def day_almanac(body: AlmanacInput, request: Request):
        session = get_session(request)
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
        # A live browser session skips the entrance and returns to the consultation hall.
        if request.cookies.get(COOKIE, "") in sessions:
            return RedirectResponse("/ask", status_code=303)
        # Never cache the entrance: the answer depends on whether the session is alive.
        return FileResponse(STATIC / "login.html", headers={"Cache-Control": "no-store"})

    @app.get("/login", include_in_schema=False)
    async def login():
        return FileResponse(STATIC / "login.html")

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
