"""Afdian (爱发电) payment integration: OpenAPI client, verified order ingestion and billing ledger.

All writes run on ``AccountStore``'s SQLite connection inside ``BEGIN IMMEDIATE`` transactions so
webhook callbacks, background polling, user refreshes and admin manual bindings are strictly
idempotent on ``out_trade_no``.

Afdian webhooks are unsigned; the handler never trusts webhook payload fields directly and always
verifies the ``out_trade_no`` via signed OpenAPI ``query-order`` before crediting any account.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

import httpx

from memory.accounts import AccountStore, email_key

logger = logging.getLogger(__name__)

EMAIL_IN_TEXT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TRADE_NO_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
SYNC_INTERVAL_S = 300


class BillingError(ValueError):
    """A billing refusal safe to display to the caller."""

    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class PlanSpec:
    key: str
    name: str
    price: str
    price_display: str
    tokens_per_month: int
    plan_id: str
    product_type: int
    badge: str
    description: str

    def public(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "price": self.price,
            "price_display": self.price_display,
            "tokens_per_month": self.tokens_per_month,
            "product_type": self.product_type,
            "badge": self.badge,
            "description": self.description,
        }


PLAN_TEMPLATES: tuple[tuple[str, str, str, str, str, int, str, str], ...] = (
    (
        "tip",
        "AFDIAN_TIP_PLAN_ID",
        "一盏清茶",
        "5.00",
        "¥5.00 / 月",
        0,
        "一盏清茶",
        "本档为纯赞赏支持，不含额外 Token 额度；账号页展示清茶致谢徽章与赞赏记录。",
    ),
    (
        "plus",
        "AFDIAN_PLUS_PLAN_ID",
        "Zhiming Plus",
        "6.66",
        "¥6.66 / 月",
        500_000,
        "Zhiming Plus",
        "当月 50 万 Tokens（订阅日起至下月同日有效，优先扣减，同周期重复订阅/升级可叠加；从本站支付自动到账，直接从爱发电主页发电请备注知命注册邮箱）",
    ),
    (
        "pro",
        "AFDIAN_PRO_PLAN_ID",
        "ZhiMing Pro",
        "9.99",
        "¥9.99 / 月",
        1_000_000,
        "ZhiMing Pro",
        "当月 100 万 Tokens（订阅日起至下月同日有效，优先扣减，同周期重复订阅/升级可叠加；从本站支付自动到账，直接从爱发电主页发电请备注知命注册邮箱）",
    ),
)

PLAN_NAMES = {tpl[0]: tpl[2] for tpl in PLAN_TEMPLATES}


@dataclass(frozen=True)
class AfdianConfig:
    creator_url: str = ""
    user_id: str = ""
    api_token: str = ""
    webhook_secret: str = ""
    plans: tuple[PlanSpec, ...] = ()
    api_base: str = "https://afdian.com"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> AfdianConfig:
        source = os.environ if env is None else env
        plans: list[PlanSpec] = []
        for key, env_key, name, price, price_display, tokens, badge, desc in PLAN_TEMPLATES:
            plan_id = (source.get(env_key) or "").strip()
            if plan_id:
                plans.append(
                    PlanSpec(
                        key=key,
                        name=name,
                        price=price,
                        price_display=price_display,
                        tokens_per_month=tokens,
                        plan_id=plan_id,
                        product_type=0,
                        badge=badge,
                        description=desc,
                    )
                )
        return cls(
            creator_url=(source.get("AFDIAN_CREATOR_URL") or "").strip(),
            user_id=(source.get("AFDIAN_USER_ID") or "").strip(),
            api_token=(source.get("AFDIAN_API_TOKEN") or "").strip(),
            webhook_secret=(source.get("AFDIAN_WEBHOOK_SECRET") or "").strip(),
            plans=tuple(plans),
            api_base=(source.get("AFDIAN_API_BASE") or "https://afdian.com").strip().rstrip("/"),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.user_id and self.api_token and self.plans)

    def plan_by_key(self, key: str) -> PlanSpec | None:
        for plan in self.plans:
            if plan.key == key:
                return plan
        return None

    def plan_by_id(self, plan_id: str) -> PlanSpec | None:
        for plan in self.plans:
            if plan.plan_id == plan_id:
                return plan
        return None

    def public_plans(self) -> list[dict]:
        return [plan.public() for plan in self.plans]

    def verify_webhook_secret(self, candidate: str) -> bool:
        return bool(
            self.webhook_secret
            and candidate
            and hmac.compare_digest(candidate.encode("utf-8"), self.webhook_secret.encode("utf-8"))
        )


def sign_afdian_request(user_id: str, api_token: str, params_json: str, ts: int) -> str:
    """Official Afdian OpenAPI MD5 signature: md5(token + 'params' + params + 'ts' + ts + 'user_id' + user_id)."""
    payload = f"{api_token}params{params_json}ts{ts}user_id{user_id}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


class AfdianClient:
    """Minimal async client for Afdian OpenAPI v1 (``ping`` and ``query-order``)."""

    def __init__(
        self,
        config: AfdianConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 15.0,
    ):
        self.config = config
        self._transport = transport
        self._timeout_s = timeout_s

    async def _post(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.config.user_id or not self.config.api_token:
            raise BillingError("afdian_not_configured", "爱发电服务尚未配置。", status_code=503)
        params_json = json.dumps(params, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        ts = int(time.time())
        body = {
            "user_id": self.config.user_id,
            "params": params_json,
            "ts": ts,
            "sign": sign_afdian_request(
                self.config.user_id, self.config.api_token, params_json, ts
            ),
        }
        url = f"{self.config.api_base}{path}"
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=self._timeout_s
            ) as client:
                response = await client.post(url, json=body)
        except httpx.HTTPError as exc:
            logger.warning("Afdian OpenAPI request failed for %s: %s", path, type(exc).__name__)
            raise BillingError(
                "afdian_unreachable",
                "暂时无法连接爱发电接口，请稍后重试。",
                status_code=502,
            ) from exc
        if response.status_code != 200:
            logger.warning("Afdian OpenAPI %s returned HTTP %s", path, response.status_code)
            raise BillingError(
                "afdian_http_error",
                f"爱发电接口返回异常状态（HTTP {response.status_code}），请稍后重试。",
                status_code=502,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise BillingError(
                "afdian_invalid_response", "爱发电接口返回格式异常。", status_code=502
            ) from exc
        if payload.get("ec") != 200:
            logger.warning(
                "Afdian OpenAPI %s rejected: ec=%s em=%s",
                path,
                payload.get("ec"),
                payload.get("em"),
            )
            raise BillingError(
                "afdian_api_error",
                "爱发电订单查询失败，请稍后重试或联系管理员。",
                status_code=502,
            )
        return payload.get("data") or {}

    async def ping(self) -> dict[str, Any]:
        return await self._post("/api/open/ping", {"a": 1})

    async def query_orders(
        self, *, out_trade_no: str | None = None, page: int = 1, per_page: int = 50
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if out_trade_no:
            params["out_trade_no"] = out_trade_no
        return await self._post("/api/open/query-order", params)


BILLING_SCHEMA = """
CREATE TABLE IF NOT EXISTS afdian_checkouts(
  custom_order_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES accounts(user_id) ON DELETE CASCADE,
  plan_key TEXT NOT NULL,
  plan_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  out_trade_no TEXT,
  created_at REAL NOT NULL,
  completed_at REAL
);
CREATE INDEX IF NOT EXISTS afdian_checkouts_user ON afdian_checkouts(user_id, created_at);
CREATE TABLE IF NOT EXISTS afdian_orders(
  out_trade_no TEXT PRIMARY KEY,
  afdian_user_id TEXT NOT NULL DEFAULT '',
  user_id TEXT REFERENCES accounts(user_id) ON DELETE SET NULL,
  custom_order_id TEXT NOT NULL DEFAULT '',
  plan_id TEXT NOT NULL DEFAULT '',
  plan_key TEXT NOT NULL DEFAULT 'unknown',
  product_type INTEGER NOT NULL DEFAULT 0,
  month INTEGER NOT NULL DEFAULT 1,
  total_amount TEXT NOT NULL DEFAULT '0',
  remark TEXT NOT NULL DEFAULT '',
  afdian_status INTEGER NOT NULL DEFAULT 0,
  process_status TEXT NOT NULL,
  tokens_granted INTEGER NOT NULL DEFAULT 0,
  grants_json TEXT NOT NULL DEFAULT '[]',
  raw_json TEXT NOT NULL DEFAULT '{}',
  received_at REAL NOT NULL,
  credited_at REAL
);
CREATE INDEX IF NOT EXISTS afdian_orders_user ON afdian_orders(user_id, received_at);
CREATE INDEX IF NOT EXISTS afdian_orders_status ON afdian_orders(process_status, received_at);
CREATE TABLE IF NOT EXISTS afdian_user_links(
  afdian_user_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES accounts(user_id) ON DELETE CASCADE,
  linked_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS afdian_user_links_user ON afdian_user_links(user_id);
"""


def _parse_order_timestamp(order: dict[str, Any], fallback: float) -> float:
    for field in ("pay_time", "create_time"):
        value = order.get(field)
        if isinstance(value, (int, float)) and value > 1_500_000_000:
            return float(value)
        if isinstance(value, str) and value.isdigit() and int(value) > 1_500_000_000:
            return float(int(value))
    return fallback


def _extract_emails(text: str) -> list[str]:
    if not text:
        return []
    return list(dict.fromkeys(email_key(m) for m in EMAIL_IN_TEXT.findall(text)))


def _safe_decimal(raw: Any) -> Decimal:
    try:
        return Decimal(str(raw or "0").strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


class BillingStore:
    """Durable Afdian checkout intents, verified order ledger and rolling-month grant fulfillment."""

    def __init__(self, accounts: AccountStore, config: AfdianConfig):
        self.accounts = accounts
        self.db = accounts.db
        self.config = config
        self.db.executescript(BILLING_SCHEMA)

    def create_checkout(
        self, user_id: str, plan_key: str, *, now: float | None = None
    ) -> dict[str, Any]:
        if not self.config.enabled:
            raise BillingError("afdian_not_configured", "赞赏与订阅暂未开放。", status_code=503)
        plan = self.config.plan_by_key(plan_key)
        if plan is None:
            raise BillingError("invalid_plan", "未找到对应的赞助方案。", status_code=422)
        account = self.accounts.get(user_id)
        if account is None:
            raise BillingError("account_not_found", "找不到当前账号，请重新登录。", status_code=404)
        created_at = time.time() if now is None else now
        custom_order_id = "zm_" + secrets.token_hex(8)
        with self.db:
            self.db.execute(
                "INSERT INTO afdian_checkouts"
                "(custom_order_id,user_id,plan_key,plan_id,status,out_trade_no,created_at,completed_at) "
                "VALUES(?,?,?,?,'pending',NULL,?,NULL)",
                (custom_order_id, user_id, plan.key, plan.plan_id, created_at),
            )
        query = urlencode(
            {
                "plan_id": plan.plan_id,
                "product_type": str(plan.product_type),
                "custom_order_id": custom_order_id,
                "remark": account["email"],
            }
        )
        pay_url = f"{self.config.api_base}/order/create?{query}"
        return {
            "custom_order_id": custom_order_id,
            "plan": plan.public(),
            "pay_url": pay_url,
            "creator_url": self.config.creator_url,
        }

    def _resolve_user_in_tx(
        self, custom_order_id: str, afdian_user_id: str, remark: str
    ) -> tuple[str | None, str]:
        if custom_order_id:
            row = self.db.execute(
                "SELECT user_id FROM afdian_checkouts WHERE custom_order_id=?",
                (custom_order_id,),
            ).fetchone()
            if (
                row
                and self.db.execute(
                    "SELECT 1 FROM accounts WHERE user_id=?", (row["user_id"],)
                ).fetchone()
            ):
                return row["user_id"], "checkout"
        if afdian_user_id:
            row = self.db.execute(
                "SELECT user_id FROM afdian_user_links WHERE afdian_user_id=?",
                (afdian_user_id,),
            ).fetchone()
            if (
                row
                and self.db.execute(
                    "SELECT 1 FROM accounts WHERE user_id=?", (row["user_id"],)
                ).fetchone()
            ):
                return row["user_id"], "afdian_link"
        emails = _extract_emails(remark)
        matched_ids: list[str] = []
        for candidate in emails:
            row = self.db.execute(
                "SELECT user_id FROM accounts WHERE username_key=?", (candidate,)
            ).fetchone()
            if row:
                matched_ids.append(row["user_id"])
        if len(matched_ids) == 1:
            return matched_ids[0], "remark_email"
        return None, "unmatched"

    def ingest_verified_order(
        self,
        order: dict[str, Any],
        *,
        now: float | None = None,
        forced_user_id: str | None = None,
        match_source: str | None = None,
        admin: str | None = None,
    ) -> dict[str, Any]:
        """Atomically record and fulfill an order already verified via Afdian OpenAPI."""
        out_trade_no = str(order.get("out_trade_no") or "").strip()
        if not out_trade_no:
            raise BillingError("invalid_order", "订单缺少交易单号。", status_code=422)
        afdian_user_id = str(order.get("user_id") or "").strip()
        custom_order_id = str(order.get("custom_order_id") or "").strip()
        plan_id = str(order.get("plan_id") or "").strip()
        try:
            product_type = int(order.get("product_type") or 0)
        except (TypeError, ValueError):
            product_type = 0
        try:
            month = max(1, int(order.get("month") or 1))
        except (TypeError, ValueError):
            month = 1
        total_amount = str(order.get("total_amount") or "0").strip()
        remark = str(order.get("remark") or "").strip()
        try:
            afdian_status = int(order.get("status") or 0)
        except (TypeError, ValueError):
            afdian_status = 0

        plan = self.config.plan_by_id(plan_id)
        plan_key = plan.key if plan else "unknown"
        ts_now = time.time() if now is None else now
        raw_json = json.dumps(order, ensure_ascii=False, sort_keys=True)

        try:
            self.db.execute("BEGIN IMMEDIATE")
            existing = self.db.execute(
                "SELECT * FROM afdian_orders WHERE out_trade_no=?", (out_trade_no,)
            ).fetchone()
            if existing and existing["process_status"] in ("credited", "tip_recorded"):
                self.db.commit()
                return {
                    "out_trade_no": out_trade_no,
                    "process_status": existing["process_status"],
                    "user_id": existing["user_id"],
                    "plan_key": existing["plan_key"],
                    "tokens_granted": existing["tokens_granted"],
                    "replayed": True,
                }

            amount = _safe_decimal(total_amount)
            if afdian_status != 2 or plan is None or amount <= 0:
                self.db.execute(
                    "INSERT INTO afdian_orders"
                    "(out_trade_no,afdian_user_id,user_id,custom_order_id,plan_id,plan_key,"
                    "product_type,month,total_amount,remark,afdian_status,process_status,"
                    "tokens_granted,grants_json,raw_json,received_at,credited_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,'ignored',0,'[]',?,?,NULL) "
                    "ON CONFLICT(out_trade_no) DO UPDATE SET "
                    "afdian_status=excluded.afdian_status,raw_json=excluded.raw_json",
                    (
                        out_trade_no,
                        afdian_user_id,
                        None,
                        custom_order_id,
                        plan_id,
                        plan_key,
                        product_type,
                        month,
                        total_amount,
                        remark,
                        afdian_status,
                        raw_json,
                        ts_now,
                    ),
                )
                self.db.commit()
                return {
                    "out_trade_no": out_trade_no,
                    "process_status": "ignored",
                    "user_id": None,
                    "plan_key": plan_key,
                    "tokens_granted": 0,
                    "replayed": False,
                }

            if forced_user_id is not None:
                user_id = forced_user_id
                matched_via = match_source or ("admin" if admin else "claim")
                if not self.db.execute(
                    "SELECT 1 FROM accounts WHERE user_id=?", (user_id,)
                ).fetchone():
                    raise BillingError("account_not_found", "找不到目标账号。", status_code=404)
            else:
                user_id, matched_via = self._resolve_user_in_tx(
                    custom_order_id, afdian_user_id, remark
                )

            if user_id is None:
                is_new = existing is None
                self.db.execute(
                    "INSERT INTO afdian_orders"
                    "(out_trade_no,afdian_user_id,user_id,custom_order_id,plan_id,plan_key,"
                    "product_type,month,total_amount,remark,afdian_status,process_status,"
                    "tokens_granted,grants_json,raw_json,received_at,credited_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,'unmatched',0,'[]',?,?,NULL) "
                    "ON CONFLICT(out_trade_no) DO UPDATE SET "
                    "afdian_user_id=excluded.afdian_user_id,remark=excluded.remark,"
                    "afdian_status=excluded.afdian_status,raw_json=excluded.raw_json",
                    (
                        out_trade_no,
                        afdian_user_id,
                        None,
                        custom_order_id,
                        plan_id,
                        plan_key,
                        product_type,
                        month,
                        total_amount,
                        remark,
                        afdian_status,
                        raw_json,
                        ts_now,
                    ),
                )
                if is_new:
                    self.accounts.costs.event(
                        "afdian_order_unmatched",
                        "warning",
                        {
                            "out_trade_no": out_trade_no,
                            "plan_key": plan_key,
                            "total_amount": total_amount,
                        },
                        ts_now,
                    )
                self.db.commit()
                return {
                    "out_trade_no": out_trade_no,
                    "process_status": "unmatched",
                    "user_id": None,
                    "plan_key": plan_key,
                    "tokens_granted": 0,
                    "replayed": False,
                }

            starts_at = _parse_order_timestamp(order, ts_now)
            grants: list[dict] = []
            if plan.tokens_per_month > 0:
                grants = self.accounts.add_subscription_grants(
                    user_id,
                    order_out_trade_no=out_trade_no,
                    plan_key=plan.key,
                    tokens_per_month=plan.tokens_per_month,
                    months=month,
                    starts_at=starts_at,
                    source="afdian",
                    now=ts_now,
                )
                process_status = "credited"
                tokens_granted = plan.tokens_per_month * month
            else:
                process_status = "tip_recorded"
                tokens_granted = 0

            if afdian_user_id:
                self.db.execute(
                    "INSERT INTO afdian_user_links(afdian_user_id,user_id,linked_at) VALUES(?,?,?) "
                    "ON CONFLICT(afdian_user_id) DO UPDATE SET "
                    "user_id=excluded.user_id,linked_at=excluded.linked_at",
                    (afdian_user_id, user_id, ts_now),
                )
            if custom_order_id:
                self.db.execute(
                    "UPDATE afdian_checkouts SET status='completed',out_trade_no=?,completed_at=? "
                    "WHERE custom_order_id=? AND user_id=?",
                    (out_trade_no, ts_now, custom_order_id, user_id),
                )
            self.db.execute(
                "INSERT INTO afdian_orders"
                "(out_trade_no,afdian_user_id,user_id,custom_order_id,plan_id,plan_key,"
                "product_type,month,total_amount,remark,afdian_status,process_status,"
                "tokens_granted,grants_json,raw_json,received_at,credited_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(out_trade_no) DO UPDATE SET "
                "user_id=excluded.user_id,process_status=excluded.process_status,"
                "tokens_granted=excluded.tokens_granted,grants_json=excluded.grants_json,"
                "raw_json=excluded.raw_json,credited_at=excluded.credited_at",
                (
                    out_trade_no,
                    afdian_user_id,
                    user_id,
                    custom_order_id,
                    plan_id,
                    plan_key,
                    product_type,
                    month,
                    total_amount,
                    remark,
                    afdian_status,
                    process_status,
                    tokens_granted,
                    json.dumps(grants, ensure_ascii=False),
                    raw_json,
                    existing["received_at"] if existing else ts_now,
                    ts_now,
                ),
            )
            self.accounts.costs.event(
                "afdian_order_credited" if process_status == "credited" else "afdian_tip_recorded",
                "info",
                {
                    "out_trade_no": out_trade_no,
                    "user_id": user_id,
                    "plan_key": plan_key,
                    "month": month,
                    "tokens_granted": tokens_granted,
                    "matched_via": matched_via,
                },
                ts_now,
            )
            if admin:
                self.accounts.costs.audit(
                    admin,
                    "afdian_bind_order",
                    {
                        "out_trade_no": out_trade_no,
                        "user_id": user_id,
                        "plan_key": plan_key,
                        "tokens_granted": tokens_granted,
                    },
                    ts_now,
                )
            self.db.commit()
            return {
                "out_trade_no": out_trade_no,
                "process_status": process_status,
                "user_id": user_id,
                "plan_key": plan_key,
                "tokens_granted": tokens_granted,
                "grants": grants,
                "matched_via": matched_via,
                "replayed": False,
            }
        except BaseException:
            self.db.rollback()
            raise

    def bind_order_admin(
        self, out_trade_no: str, target_identifier: str, admin: str, *, now: float | None = None
    ) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM afdian_orders WHERE out_trade_no=?", (out_trade_no,)
        ).fetchone()
        if row is None:
            raise BillingError("order_not_found", "找不到该爱发电订单。", status_code=404)
        if row["process_status"] in ("credited", "tip_recorded"):
            raise BillingError(
                "order_already_bound", "该订单已完成到账，无需重复绑定。", status_code=409
            )
        if row["process_status"] != "unmatched":
            raise BillingError("order_not_bindable", "该订单状态不可绑定发放。", status_code=422)
        target = target_identifier.strip()
        account = self.accounts.get(target)
        if account is None:
            creds = self.accounts.credentials(target)
            account = creds[0] if creds else None
        if account is None:
            raise BillingError(
                "account_not_found", "找不到目标账号（请填写注册邮箱或账号 ID）。", status_code=404
            )
        raw_order = json.loads(row["raw_json"] or "{}")
        if not raw_order:
            raw_order = {
                "out_trade_no": row["out_trade_no"],
                "user_id": row["afdian_user_id"],
                "custom_order_id": row["custom_order_id"],
                "plan_id": row["plan_id"],
                "product_type": row["product_type"],
                "month": row["month"],
                "total_amount": row["total_amount"],
                "remark": row["remark"],
                "status": row["afdian_status"],
            }
        return self.ingest_verified_order(
            raw_order,
            now=now,
            forced_user_id=account["user_id"],
            match_source="admin",
            admin=admin,
        )

    def validate_self_claim(self, user_id: str, user_email: str, order: dict[str, Any]) -> None:
        """Guard against claiming someone else's order."""
        out_trade_no = str(order.get("out_trade_no") or "").strip()
        existing = self.db.execute(
            "SELECT user_id,process_status FROM afdian_orders WHERE out_trade_no=?",
            (out_trade_no,),
        ).fetchone()
        if existing and existing["process_status"] in ("credited", "tip_recorded"):
            if existing["user_id"] != user_id:
                raise BillingError(
                    "order_already_claimed",
                    "该订单已绑定到其他账号，如有疑问请联系管理员。",
                    status_code=409,
                )
            return

        custom_order_id = str(order.get("custom_order_id") or "").strip()
        if custom_order_id:
            checkout = self.db.execute(
                "SELECT user_id FROM afdian_checkouts WHERE custom_order_id=?",
                (custom_order_id,),
            ).fetchone()
            if checkout and checkout["user_id"] != user_id:
                raise BillingError(
                    "order_owner_mismatch",
                    "该订单由其他账号发起，无法认领。",
                    status_code=403,
                )

        afdian_user_id = str(order.get("user_id") or "").strip()
        if afdian_user_id:
            linked = self.db.execute(
                "SELECT user_id FROM afdian_user_links WHERE afdian_user_id=?",
                (afdian_user_id,),
            ).fetchone()
            if linked and linked["user_id"] != user_id:
                raise BillingError(
                    "afdian_user_mismatch",
                    "该爱发电账号已绑定其他知命账号，请联系管理员处理。",
                    status_code=403,
                )

        remark_emails = _extract_emails(str(order.get("remark") or ""))
        if remark_emails and email_key(user_email) not in remark_emails:
            for other in remark_emails:
                row = self.db.execute(
                    "SELECT user_id FROM accounts WHERE username_key=?", (other,)
                ).fetchone()
                if row and row["user_id"] != user_id:
                    raise BillingError(
                        "remark_email_mismatch",
                        "该订单备注的邮箱属于其他账号，无法认领。",
                        status_code=403,
                    )

    def user_orders(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT out_trade_no,plan_key,month,total_amount,process_status,"
            "tokens_granted,grants_json,received_at,credited_at "
            "FROM afdian_orders WHERE user_id=? ORDER BY COALESCE(credited_at,received_at) DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        items = []
        for row in rows:
            grants = json.loads(row["grants_json"] or "[]")
            items.append(
                {
                    "out_trade_no": row["out_trade_no"],
                    "plan_key": row["plan_key"],
                    "plan_name": PLAN_NAMES.get(row["plan_key"], row["plan_key"]),
                    "month": row["month"],
                    "total_amount": row["total_amount"],
                    "status": row["process_status"],
                    "tokens_granted": row["tokens_granted"],
                    "starts_at": grants[0]["starts_at"] if grants else None,
                    "expires_at": grants[-1]["expires_at"] if grants else None,
                    "at": row["credited_at"] or row["received_at"],
                }
            )
        return items

    def user_summary(self, user_id: str, *, now: float | None = None) -> dict[str, Any]:
        ts_now = time.time() if now is None else now
        detail = self.accounts.quota_detail(user_id, now=ts_now)
        tip_row = self.db.execute(
            "SELECT COUNT(*), COALESCE(SUM(month),0), MAX(credited_at) "
            "FROM afdian_orders WHERE user_id=? AND plan_key='tip' AND process_status='tip_recorded'",
            (user_id,),
        ).fetchone()
        tea_count = int(tip_row[0] or 0)
        tea_months = int(tip_row[1] or 0)
        tea_last_at = tip_row[2]

        badges: list[dict[str, Any]] = []
        active_by_plan: dict[str, float] = {}
        for grant in detail["subscription"]["active_grants"]:
            key = grant["plan_key"]
            active_by_plan[key] = max(active_by_plan.get(key, 0.0), grant["expires_at"])
        for key in ("pro", "plus"):
            if key in active_by_plan:
                badges.append(
                    {
                        "key": key,
                        "label": PLAN_NAMES.get(key, key),
                        "expires_at": active_by_plan[key],
                    }
                )
        if tea_count > 0:
            badges.append(
                {
                    "key": "tip",
                    "label": "一盏清茶 · 感谢赞赏",
                    "count": tea_count,
                    "months": tea_months,
                    "last_at": tea_last_at,
                }
            )
        return {
            "enabled": self.config.enabled,
            "creator_url": self.config.creator_url,
            "quota": detail,
            "badges": badges,
            "tea_support": {
                "count": tea_count,
                "months": tea_months,
                "last_at": tea_last_at,
            },
            "orders": self.user_orders(user_id, limit=20),
        }

    def list_orders_admin(
        self, *, status: str = "", query: str = "", offset: int = 0, limit: int = 50
    ) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("o.process_status=?")
            params.append(status)
        q = query.strip()
        if q:
            like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            clauses.append(
                "(o.out_trade_no LIKE ? ESCAPE '\\' OR o.remark LIKE ? ESCAPE '\\' "
                "OR COALESCE(a.username,'') LIKE ? ESCAPE '\\' OR o.custom_order_id LIKE ? ESCAPE '\\')"
            )
            params.extend([like, like, like, like])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        total = self.db.execute(
            f"SELECT COUNT(*) FROM afdian_orders o LEFT JOIN accounts a ON a.user_id=o.user_id {where}",
            params,
        ).fetchone()[0]
        rows = self.db.execute(
            "SELECT o.out_trade_no,o.afdian_user_id,o.user_id,a.username,o.custom_order_id,"
            "o.plan_key,o.month,o.total_amount,o.remark,o.afdian_status,o.process_status,"
            "o.tokens_granted,o.grants_json,o.received_at,o.credited_at "
            "FROM afdian_orders o LEFT JOIN accounts a ON a.user_id=o.user_id "
            f"{where} ORDER BY o.received_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        items = []
        for row in rows:
            grants = json.loads(row["grants_json"] or "[]")
            items.append(
                {
                    "out_trade_no": row["out_trade_no"],
                    "afdian_user_id": row["afdian_user_id"],
                    "user_id": row["user_id"],
                    "email": row["username"],
                    "custom_order_id": row["custom_order_id"],
                    "plan_key": row["plan_key"],
                    "plan_name": PLAN_NAMES.get(row["plan_key"], row["plan_key"]),
                    "month": row["month"],
                    "total_amount": row["total_amount"],
                    "remark": row["remark"],
                    "afdian_status": row["afdian_status"],
                    "process_status": row["process_status"],
                    "tokens_granted": row["tokens_granted"],
                    "starts_at": grants[0]["starts_at"] if grants else None,
                    "expires_at": grants[-1]["expires_at"] if grants else None,
                    "received_at": row["received_at"],
                    "credited_at": row["credited_at"],
                }
            )
        return items, total

    def admin_stats(self) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT COUNT(*),"
            "COALESCE(SUM(CASE WHEN process_status IN ('credited','tip_recorded') THEN 1 ELSE 0 END),0),"
            "COALESCE(SUM(CASE WHEN process_status='unmatched' THEN 1 ELSE 0 END),0),"
            "COALESCE(SUM(tokens_granted),0) "
            "FROM afdian_orders"
        ).fetchone()
        return {
            "enabled": self.config.enabled,
            "webhook_configured": bool(self.config.webhook_secret),
            "creator_url": self.config.creator_url,
            "plans": self.config.public_plans(),
            "total_orders": int(row[0] or 0),
            "fulfilled_orders": int(row[1] or 0),
            "unmatched_orders": int(row[2] or 0),
            "total_tokens_granted": int(row[3] or 0),
        }


class AfdianService:
    """High-level coordinator for webhook verification, polling sync and self-service claims."""

    def __init__(
        self,
        billing_factory: Callable[[], BillingStore],
        config: AfdianConfig,
        *,
        client: AfdianClient | None = None,
        sync_interval_s: float = SYNC_INTERVAL_S,
    ):
        self.billing = billing_factory
        self.config = config
        self.client = client or AfdianClient(config)
        self.sync_interval_s = sync_interval_s
        self._lock = asyncio.Lock()
        self.last_sync_at: float | None = None
        self.last_sync_error: str | None = None
        self.last_sync_summary: dict[str, int] | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            **self.billing().admin_stats(),
            "last_sync_at": self.last_sync_at,
            "last_sync_error": self.last_sync_error,
            "last_sync_summary": self.last_sync_summary,
        }

    async def handle_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Accept an Afdian webhook, verify the trade number via OpenAPI, and credit idempotently."""
        data = payload.get("data") if isinstance(payload, dict) else None
        order = data.get("order") if isinstance(data, dict) else None
        out_trade_no = str((order or {}).get("out_trade_no") or "").strip()
        if not out_trade_no:
            # Afdian's dashboard "Test" button may send a ping/minimal payload without an order.
            return {"ec": 200, "em": ""}
        if not TRADE_NO_RE.fullmatch(out_trade_no):
            raise BillingError("invalid_trade_no", "交易单号格式无效。", status_code=400)
        # Never trust webhook fields directly: verify authoritatively via signed OpenAPI query-order.
        result = await self.client.query_orders(out_trade_no=out_trade_no, page=1, per_page=5)
        orders = result.get("list") or []
        matched = next(
            (item for item in orders if str(item.get("out_trade_no") or "") == out_trade_no),
            None,
        )
        if matched is None:
            logger.warning("Afdian webhook trade %s not found via query-order", out_trade_no)
            self.billing().accounts.costs.event(
                "afdian_webhook_unverified",
                "warning",
                {"out_trade_no": out_trade_no},
            )
            self.billing().db.commit()
            return {"ec": 200, "em": ""}
        self.billing().ingest_verified_order(matched)
        return {"ec": 200, "em": ""}

    async def sync_recent(self, *, max_pages: int = 2, per_page: int = 50) -> dict[str, Any]:
        if not self.config.enabled:
            raise BillingError("afdian_not_configured", "爱发电服务尚未配置。", status_code=503)
        async with self._lock:
            counts = {
                "checked": 0,
                "credited": 0,
                "tip_recorded": 0,
                "unmatched": 0,
                "replayed": 0,
                "ignored": 0,
            }
            try:
                store = self.billing()
                for page in range(1, max_pages + 1):
                    data = await self.client.query_orders(page=page, per_page=per_page)
                    items = data.get("list") or []
                    if not items:
                        break
                    for item in items:
                        counts["checked"] += 1
                        res = store.ingest_verified_order(item)
                        if res["replayed"]:
                            counts["replayed"] += 1
                        else:
                            status = res["process_status"]
                            counts[status] = counts.get(status, 0) + 1
                    total_page = int(data.get("total_page") or 1)
                    if page >= total_page:
                        break
                self.last_sync_at = time.time()
                self.last_sync_error = None
                self.last_sync_summary = counts
                return counts
            except Exception as exc:
                self.last_sync_at = time.time()
                self.last_sync_error = str(exc)[:200]
                raise

    async def claim_order(self, user_id: str, user_email: str, out_trade_no: str) -> dict[str, Any]:
        if not self.config.enabled:
            raise BillingError("afdian_not_configured", "爱发电服务尚未配置。", status_code=503)
        trade_no = out_trade_no.strip()
        if not TRADE_NO_RE.fullmatch(trade_no):
            raise BillingError("invalid_trade_no", "请输入有效的爱发电订单号。", status_code=422)
        data = await self.client.query_orders(out_trade_no=trade_no, page=1, per_page=5)
        orders = data.get("list") or []
        matched = next(
            (item for item in orders if str(item.get("out_trade_no") or "") == trade_no),
            None,
        )
        if matched is None:
            raise BillingError(
                "order_not_found",
                "未在爱发电查询到该订单号，请核对后重试（若刚支付请稍候几秒）。",
                status_code=404,
            )
        if int(matched.get("status") or 0) != 2:
            raise BillingError("order_not_paid", "该订单尚未完成支付。", status_code=422)
        if self.config.plan_by_id(str(matched.get("plan_id") or "")) is None:
            raise BillingError(
                "unsupported_plan", "该订单不属于当前支持的知命赞助方案。", status_code=422
            )
        store = self.billing()
        store.validate_self_claim(user_id, user_email, matched)
        return store.ingest_verified_order(matched, forced_user_id=user_id, match_source="claim")

    async def schedule(self) -> None:
        if not self.config.enabled or self.sync_interval_s <= 0:
            return
        while True:
            await asyncio.sleep(self.sync_interval_s)
            try:
                await self.sync_recent(max_pages=2)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Periodic Afdian order sync failed")
