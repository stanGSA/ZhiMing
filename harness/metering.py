"""Per-account call admission and settlement, including retries and auxiliary model calls."""

from __future__ import annotations

import json
from contextvars import ContextVar


class QuotaExceeded(Exception):
    code = "free_quota_exhausted"
    message = "免费额度已用完或不足以完成本次模型调用，可继续使用离线演示、排盘及查看历史记录。"


CURRENT_METER = ContextVar("account_meter", default=None)


class Attempt:
    def __init__(self, messages, tools, output_limit):
        self.meter = CURRENT_METER.get()
        self.call_id = None
        self.output_limit = output_limit
        if self.meter is not None:
            # UTF-8 bytes conservatively bound text tokens; include schemas and protocol overhead.
            # The provider's returned usage is authoritative when the call settles.
            size = len(json.dumps([messages, tools], ensure_ascii=False).encode("utf-8"))
            input_bound = size + 1024 + 32 * len(messages)
            self.call_id, self.output_limit = self.meter.reserve_tokens(input_bound, output_limit)

    def __enter__(self):
        return self

    def settle(self, input_tokens, output_tokens):
        if self.call_id is not None:
            self.meter.store.settle_tokens(self.call_id, input_tokens, output_tokens)
            self.call_id = None

    def __exit__(self, exc_type, exc, tb):
        if self.call_id is not None:
            # Explicit rejection is unbilled; cancellation, timeout or missing usage is uncertain.
            rejected = getattr(exc, "status_code", None) in (400, 401, 403, 404, 413, 422, 429)
            self.meter.store.settle_tokens(self.call_id, None, None, rejected=rejected)


class MeteredModel:
    def __init__(self, model, store, user_id):
        self.inner = model
        self.store = store
        self.user_id = user_id

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def reserve_tokens(self, input_bound, output_limit):
        return self.store.reserve_tokens(self.user_id, input_bound, output_limit)

    async def chat(self, messages, tools):
        token = CURRENT_METER.set(self)
        try:
            if getattr(self.inner, "supports_metering", False):
                return await self.inner.chat(messages, tools)
            # Injected/scripted models also exercise accounting in offline tests.
            with Attempt(messages, tools, 8192) as attempt:
                result = await self.inner.chat(messages, tools)
                attempt.settle(
                    result.input_tokens if result.usage_available else None,
                    result.output_tokens if result.usage_available else None,
                )
                return result
        finally:
            CURRENT_METER.reset(token)
