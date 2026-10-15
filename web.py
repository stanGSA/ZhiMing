"""Local browser interface. Run with .venv/Scripts/python.exe web.py."""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date as CalendarDate
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import ROOT, Runtime, create_runtime
from common.regions import region_options, selected_region
from common.time_utils import NeedsInput
from plugins.astro.calculator import natal_chart
from plugins.bazi.calculator import compute_bazi

STATIC = Path(__file__).with_name("web_static")
COOKIE = "zhiming_session"
MAX_IDLE = 12 * 3600
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
    system: Literal["auto", "bazi", "astro", "tarot"] = "auto"
    birth: BirthInfo = Field(default_factory=BirthInfo)
    spread: Literal["single", "three_card", "decision"] = "three_card"

    @field_validator("message")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("请先写下你的问题")
        return value.strip()


class NewInput(BaseModel):
    provider: Literal["configured", "demo"] = "configured"


class ChartInput(BaseModel):
    system: Literal["bazi", "astro"]
    birth: BirthInfo


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

    async def close(session):
        try:
            await session.runtime.close_model()
        finally:
            session.runtime.close()

    async def reap():
        while True:
            await asyncio.sleep(60)
            for key, session in list(sessions.items()):
                if not session.lock.locked() and time.monotonic() - session.touched > MAX_IDLE:
                    sessions.pop(key, None)
                    await close(session)

    @asynccontextmanager
    async def lifespan(_app):
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
        response = await call_next(request)
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

    def get_session(request: Request):
        session = sessions.get(request.cookies.get(COOKIE, ""))
        if session is None:
            raise HTTPException(401, "会话已过期，请刷新页面重新开始。")
        session.touched = time.monotonic()
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
            "history": session.runtime.store.recent_readings(session.user_id, limit=30),
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
        session.touched = time.monotonic()
        return state(session)

    @app.post("/api/chat")
    async def chat(body: ChatInput, request: Request):
        session = get_session(request)
        available(session)
        async with session.lock:
            chart_question = None
            if body.system in ("bazi", "astro"):
                try:
                    session.chart = body.birth.chart(body.system)
                except NeedsInput as exc:
                    session.chart = None
                    chart_question = exc.question
            evidence = body.birth.evidence()
            message = body.message
            if evidence and body.system != "tarot":
                message += "\n\n我在出生信息表中填写的资料：" + evidence + "。"
            if body.system != "auto":
                message += (
                    "\n本次希望使用"
                    + {"bazi": "八字", "astro": "西方占星", "tarot": "塔罗"}[body.system]
                    + "来解读。"
                )
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
            try:
                outcome = await asyncio.wait_for(session.runtime.turn(message), timeout=360)
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
            session.birth = body.birth
            session.chart = None
            try:
                session.chart = body.birth.chart(body.system)
            except NeedsInput as exc:
                return {"chart": None, "question": exc.question, "code": exc.code}
        return {"chart": session.chart}

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

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
