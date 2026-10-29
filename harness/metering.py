"""Per-account call admission and settlement, including retries and auxiliary model calls.

Site-wide controls (daily budget, auto-pause, suspended accounts) are checked by the store in
the same transaction as the account reservation; the concurrency gate is in-process.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Callable
from contextvars import ContextVar


class QuotaExceeded(Exception):
    code = "free_quota_exhausted"
    message = "免费额度已用完或不足以完成本次模型调用，可继续使用离线演示、排盘及查看历史记录。"
    retryable = False


class AccountSuspended(QuotaExceeded):
    code = "account_suspended"
    message = "该账号的模型调用已被暂停，如有疑问请联系管理员；离线演示、排盘及历史记录不受影响。"


class SiteLimited(QuotaExceeded):
    """A site-wide refusal: it lifts by itself or by an administrator, not by this account."""

    retryable = True


class SitePaused(SiteLimited):
    code = "model_paused"
    message = (
        "模型服务暂时暂停（维护中或检测到异常消耗），请稍后再试；离线演示、排盘及历史记录不受影响。"
    )


class SiteBudgetExhausted(SiteLimited):
    code = "site_budget_exhausted"
    message = (
        "今日全站模型用量已达上限，次日零点（北京时间）恢复；离线演示、排盘及历史记录不受影响。"
    )


class ModelBusy(SiteLimited):
    code = "model_busy"
    message = "当前使用人数较多，模型调用排队超时，请稍后重试。"


CURRENT_METER = ContextVar("account_meter", default=None)


def error_kind(exc: BaseException | None) -> str | None:
    """A short, credential-free label for a failed attempt; never the exception text."""
    if exc is None:
        return None
    if isinstance(exc, asyncio.CancelledError):
        return "cancelled"
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return f"http_{status}"
    name = type(exc).__name__
    if isinstance(exc, TimeoutError) or name == "APITimeoutError":
        return "timeout"
    if name == "APIConnectionError":
        return "connection"
    return name[:40]


class ConcurrencyGate:
    """Bounds simultaneous model requests across the process; the limit can change live.

    A limit of zero or less means unlimited. Waiters are woken in arrival order and give up
    with ModelBusy after ``wait_s`` seconds.
    """

    def __init__(self, limit: Callable[[], int], wait_s: Callable[[], float] | float = 20):
        self.limit = limit
        self.wait_s = wait_s if callable(wait_s) else (lambda: wait_s)
        self.active = 0
        self.waiters: deque[asyncio.Future] = deque()

    def _full(self) -> bool:
        limit = self.limit()
        return limit > 0 and self.active >= limit

    async def acquire(self) -> None:
        self.dispatch()
        if not self.waiters and not self._full():
            self.active += 1
            return
        waiter = asyncio.get_running_loop().create_future()
        self.waiters.append(waiter)
        try:
            await asyncio.wait_for(waiter, max(0.0, float(self.wait_s())))
        except (TimeoutError, asyncio.CancelledError) as exc:
            if waiter.done() and not waiter.cancelled():
                # The slot was handed over just as this caller gave up: pass it on.
                self.release()
            elif waiter in self.waiters:
                self.waiters.remove(waiter)
            if isinstance(exc, TimeoutError):
                raise ModelBusy() from None
            raise

    def release(self) -> None:
        self.active = max(0, self.active - 1)
        self.dispatch()

    def dispatch(self) -> None:
        """Hand free slots to waiters in arrival order (also after the limit is raised)."""
        while self.waiters and not self._full():
            waiter = self.waiters.popleft()
            if not waiter.done():
                self.active += 1
                waiter.set_result(None)

    def snapshot(self) -> dict:
        return {"active": self.active, "waiting": len(self.waiters), "limit": self.limit()}


class Attempt:
    def __init__(self, messages, tools, output_limit, *, model: str | None = None):
        self.meter = CURRENT_METER.get()
        self.call_id = None
        self.admitted = False
        self.output_limit = output_limit
        self.model = model
        self.messages = messages
        self.tools = tools

    async def __aenter__(self):
        if self.meter is not None:
            # UTF-8 bytes conservatively bound text tokens; include schemas and protocol overhead.
            # The provider's returned usage is authoritative when the call settles.
            size = len(json.dumps([self.messages, self.tools], ensure_ascii=False).encode("utf-8"))
            input_bound = size + 1024 + 32 * len(self.messages)
            await self.meter.admit()
            self.admitted = True
            try:
                self.call_id, self.output_limit = self.meter.reserve_tokens(
                    input_bound, self.output_limit, self.model
                )
            except BaseException:
                self.admitted = False
                self.meter.leave()
                raise
        return self

    def settle(self, input_tokens, output_tokens):
        if self.call_id is not None:
            self.meter.store.settle_tokens(self.call_id, input_tokens, output_tokens)
            self.call_id = None

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if self.call_id is not None:
                # Explicit rejection is unbilled; cancellation, timeout or missing usage is
                # uncertain.
                rejected = getattr(exc, "status_code", None) in (400, 401, 403, 404, 413, 422, 429)
                self.meter.store.settle_tokens(
                    self.call_id, None, None, rejected=rejected, error=error_kind(exc)
                )
                self.call_id = None
        finally:
            if self.admitted:
                self.admitted = False
                self.meter.leave()


class MeteredModel:
    def __init__(self, model, store, user_id, gate: ConcurrencyGate | None = None):
        self.inner = model
        self.store = store
        self.user_id = user_id
        self.gate = gate

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def admit(self):
        if self.gate is not None:
            await self.gate.acquire()

    def leave(self):
        if self.gate is not None:
            self.gate.release()

    def reserve_tokens(self, input_bound, output_limit, model=None):
        return self.store.reserve_tokens(self.user_id, input_bound, output_limit, model=model)

    async def chat(self, messages, tools):
        token = CURRENT_METER.set(self)
        try:
            if getattr(self.inner, "supports_metering", False):
                return await self.inner.chat(messages, tools)
            # Injected/scripted models also exercise accounting in offline tests.
            name = getattr(self.inner, "model", None)
            async with Attempt(
                messages, tools, 8192, model=name if isinstance(name, str) else None
            ) as attempt:
                result = await self.inner.chat(messages, tools)
                attempt.settle(
                    result.input_tokens if result.usage_available else None,
                    result.output_tokens if result.usage_available else None,
                )
                return result
        finally:
            CURRENT_METER.reset(token)
