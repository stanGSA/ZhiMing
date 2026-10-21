"""Shared, persistent reservations for review, revision, retries and resumed runs.

Amounts are estimates at the configured rates, never a provider invoice. Before each
chat reserve three HTTP attempts at a conservative UTF-8 input bound plus max_tokens.
Unreported usage and failed/interrupted requests retain their reservation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
from pathlib import Path


class BudgetExceeded(ValueError):
    pass


def amount(value) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("预算和单价须为有限非负数")
    return result


class ReviewBudget:
    def __init__(self, config: dict, root: Path):
        spec = (config.get("kb_review") or {}).get("budget")
        if not spec or not spec.get("state_path"):
            raise ValueError("真实调用须先配置 kb_review.budget 和 state_path")
        self.limit = None if spec.get("unlimited") is True else amount(spec["limit"])
        self.currency = spec.get("currency")
        if self.limit is not None and not self.currency:
            raise ValueError("有上限的预算须配置 currency")
        self.path = root / spec["state_path"]

    @contextmanager
    def transaction(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(self.path.suffix + ".lock")
        deadline = time.monotonic() + 1
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError as exc:
                if time.monotonic() >= deadline:
                    raise ValueError(
                        "预算账本正被其他进程使用；核实无运行进程后才可清理遗留锁"
                    ) from exc
                time.sleep(0.01)
        try:
            os.close(fd)
            state = (
                json.loads(self.path.read_text(encoding="utf-8"))
                if self.path.exists()
                else dict(
                    limit=str(self.limit) if self.limit is not None else None,
                    currency=self.currency,
                    requests=[],
                )
            )
            stored_limit = amount(state["limit"]) if state["limit"] is not None else None
            if stored_limit != self.limit or state["currency"] != self.currency:
                raise ValueError("预算账本已绑定另一上限或币种，请使用新的 state_path")
            yield state
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        finally:
            lock.unlink(missing_ok=True)

    def reserve(self, role, spec, messages) -> str:
        if self.limit is not None and (
            spec.currency != self.currency
            or any(price is None for price in (spec.input_per_mtok, spec.output_per_mtok))
        ):
            raise ValueError("真实调用须配置与预算同币种的输入、输出单价")
        priced = spec.input_per_mtok is not None and spec.output_per_mtok is not None
        price_in = amount(spec.input_per_mtok) if priced else None
        price_out = amount(spec.output_per_mtok) if priced else None
        payload = json.dumps(messages, ensure_ascii=False).encode("utf-8")
        # Ordinary text tokenization cannot need more tokens than its UTF-8 bytes;
        # keep an extra allowance for API message wrappers. Not the plan's heuristic.
        input_bound = len(payload) + 2048
        per_attempt = (
            (input_bound * price_in + spec.max_tokens * price_out) / 1_000_000 if priced else None
        )
        reservation = per_attempt * 3 if priced else None
        request_id = uuid.uuid4().hex
        with self.transaction() as state:
            if state.get("blocked"):
                raise BudgetExceeded("服务返回用量超过保守预留边界，须先核对计费再继续")
            held = sum(amount(r["held"]) for r in state["requests"] if r["held"] is not None)
            if self.limit is not None and held + reservation > self.limit:
                raise BudgetExceeded("本次调用的保守费用预留将超过总预算，已停止调用")
            state["requests"].append(
                dict(
                    id=request_id,
                    role=role,
                    vendor=spec.vendor,
                    requested_model=spec.model,
                    input_per_mtok=str(price_in) if priced else None,
                    output_per_mtok=str(price_out) if priced else None,
                    currency=spec.currency,
                    prompt_sha256=hashlib.sha256(payload).hexdigest(),
                    input_token_bound=input_bound,
                    output_token_bound=spec.max_tokens,
                    per_attempt=str(per_attempt) if priced else None,
                    reserved=str(reservation) if priced else None,
                    held=str(reservation) if priced else None,
                    status="reserved_or_unknown",
                )
            )
        return request_id

    def settle(self, request_id, response, attempts):
        with self.transaction() as state:
            row = next(r for r in state["requests"] if r["id"] == request_id)
            row.update(
                returned_model=response.model,
                http_attempts=attempts,
                usage_available=response.usage_available,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
            )
            if response.usage_available and row["input_per_mtok"] is not None:
                known = (
                    response.input_tokens * amount(row["input_per_mtok"])
                    + response.output_tokens * amount(row["output_per_mtok"])
                ) / 1_000_000
                held = known + max(0, attempts - 1) * amount(row["per_attempt"])
                # A provider violating the assumed bound blocks all subsequent spending.
                row["held"] = str(
                    max(held, amount(row["reserved"]))
                    if (
                        attempts > 3
                        or response.input_tokens > row["input_token_bound"]
                        or response.output_tokens > row["output_token_bound"]
                    )
                    else held
                )
                row["known_cost_estimate"] = str(known)
                row["status"] = "estimated" if attempts == 1 else "estimated_with_unknown_retries"
                if (
                    attempts > 3
                    or response.input_tokens > row["input_token_bound"]
                    or response.output_tokens > row["output_token_bound"]
                ):
                    state["blocked"] = True


class BudgetModel:
    def __init__(self, model, role, spec, budget, *, make_model=None):
        self.model, self.role, self.spec, self.budget = model, role, spec, budget
        self.make_model = make_model
        self.lock = asyncio.Lock()
        self.attempt_counter = ContextVar(f"attempts_{role}", default=0)

    @property
    def request_attempts(self):
        return self.attempt_counter.get()

    async def chat(self, messages, tools):
        if self.make_model is not None:
            return await self.one(messages, tools)
        # A shared adapter must serialize to make its attempt counter attributable.
        async with self.lock:
            return await self.one(messages, tools)

    async def one(self, messages, tools):
        request_id = self.budget.reserve(self.role, self.spec, messages)
        model = self.make_model() if self.make_model is not None else self.model
        before = getattr(model, "request_attempts", 0)
        try:
            response = await model.chat(messages, tools)
            attempts = max(1, getattr(model, "request_attempts", 0) - before)
            self.budget.settle(request_id, response, attempts)
            return response
        finally:
            attempts = max(1, getattr(model, "request_attempts", 0) - before)
            self.attempt_counter.set(self.request_attempts + attempts)
            close = getattr(model, "close", None)
            if self.make_model is not None and close:
                await close()

    async def close(self):
        close = getattr(self.model, "close", None)
        if close:
            await close()
