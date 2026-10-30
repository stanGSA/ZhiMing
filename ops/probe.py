"""Small, metered real-model probes. The web app owns scheduling; root monitor owns alerts."""

from __future__ import annotations

import asyncio
import copy
import logging
import time
import uuid

from app import build_model
from harness.metering import MeteredModel, QuotaExceeded, SiteBudgetExhausted

logger = logging.getLogger(__name__)


class ProbeStore:
    """Meter probe retries into the site ledger without borrowing any person's allowance."""

    def __init__(self, store):
        self.store = store

    def reserve_tokens(self, user_id, input_bound, output_limit, *, model=None):
        costs, db, now = self.store.costs, self.store.db, time.time()
        try:
            db.execute("BEGIN IMMEDIATE")
            costs.gatekeep(None, now)
            room = costs.budget_room(now)
            if room is not None and room < input_bound + min(256, output_limit):
                costs.budget_exhausted(now, input_bound + min(256, output_limit))
                raise SiteBudgetExhausted()
            output = min(output_limit, room - input_bound) if room is not None else output_limit
            refusal = costs.trip(None, input_bound + output, now)
            if refusal:
                raise refusal
            call = "probe-" + uuid.uuid4().hex
            costs.reserve(call, None, model, input_bound + output, now)
            db.commit()
            return call, output
        except QuotaExceeded:
            db.commit()
            raise
        except BaseException:
            db.rollback()
            raise

    def settle_tokens(self, call, input_tokens, output_tokens, *, rejected=False, error=None):
        known = all(type(x) is int and x >= 0 for x in (input_tokens, output_tokens))
        status = "rejected" if rejected else "settled" if known else "uncertain"
        with self.store.db:
            self.store.costs.settle(call, input_tokens, output_tokens, status, error, time.time())


class ProbeService:
    def __init__(self, accounts, gate, config, factory=None):
        self.accounts, self.gate, self.config = accounts, gate, config
        self.factory = factory or self.make_model
        self.lock = asyncio.Lock()

    def make_model(self):
        config = copy.deepcopy(self.config)
        provider = config["llm"]["provider"]
        if provider == "demo":
            raise ValueError("真实模型未配置")
        config["llm"]["timeout_s"] = 20
        options = config.setdefault("model_options", {}).setdefault("orchestrator", {})
        options.update(max_tokens=32)
        if provider == "deepseek":
            options["thinking"] = "disabled"
            options.pop("reasoning_effort", None)
        name = config.get("models", {}).get("orchestrator") or config["llm"].get("model")
        model = build_model(provider, name, config, None)
        # The adapters support a bounded output even when the normal request has a larger cap.
        if provider == "anthropic":
            model.max_tokens = 32
        else:
            model.request_options["max_tokens"] = 32
        return model

    def snapshot(self):
        costs = self.accounts().costs
        interval = costs._get("model_probe_interval_min") or 0
        result = costs._get("model_probe_result")
        last = costs._get("model_probe_completed_at") or 0
        now = time.time()
        return {
            "interval_min": interval,
            "running": self.lock.locked(),
            "latest": result,
            "next_at": max(now, last + interval * 60) if interval else None,
            "history": costs._get("model_probe_history") or [],
        }

    def configure(self, interval, admin):
        if type(interval) is not int or not 0 <= interval <= 10080:
            raise ValueError("检测周期须为 0–10080 分钟的整数")
        with self.accounts().db:
            self.accounts().costs._put("model_probe_interval_min", interval)
            self.accounts().costs.audit(admin, "probe_interval", {"minutes": interval})

    async def run(self, by="timer"):
        if self.lock.locked():
            return {"busy": True, **self.snapshot()}
        async with self.lock:
            store = self.accounts()
            started = time.time()
            result = {
                "started_at": started,
                "by": by,
                "status": "failure",
                "error": None,
                "provider": self.config["llm"]["provider"],
                "model": self.config.get("models", {}).get("orchestrator")
                or self.config["llm"].get("model"),
            }
            model = None
            try:
                model = self.factory()
                metered = MeteredModel(model, ProbeStore(store), None, self.gate)
                async with asyncio.timeout(45):
                    reply = await metered.chat(
                        [{"role": "user", "content": "Reply with OK only."}], []
                    )
                if not reply.text.strip() or reply.planned:
                    raise ValueError("empty response")
                result.update(
                    status="success",
                    input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens,
                )
            except QuotaExceeded as exc:
                result.update(status="skipped", error=type(exc).__name__)
            except asyncio.CancelledError:
                result.update(status="failure", error="Interrupted")
                raise
            except Exception as exc:
                # Exception text can include provider URLs, auth headers, or upstream content.
                result.update(error=type(exc).__name__)
            finally:
                if model is not None and getattr(model, "close", None):
                    try:
                        async with asyncio.timeout(3):
                            await model.close()
                    except Exception:
                        logger.warning("Probe client close failed")
                finished = time.time()
                result.update(completed_at=finished, latency_ms=round((finished - started) * 1000))
                costs = store.costs
                with store.db:
                    costs._put("model_probe_result", result)
                    costs._put("model_probe_completed_at", finished)
                    history = costs._get("model_probe_history") or []
                    costs._put("model_probe_history", [result, *history][:30])
                    if by != "timer":
                        costs.audit(by, "probe_model", {"status": result["status"]})
            return self.snapshot()

    async def schedule(self):
        while True:
            try:
                snapshot = self.snapshot()
                if snapshot["next_at"] is not None and snapshot["next_at"] <= time.time():
                    await self.run()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Model probe scheduler failed")
            await asyncio.sleep(15)
