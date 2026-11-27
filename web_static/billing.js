"use strict";

/* Standalone quota & billing page (/billing). CSP-safe: no inline styles or scripts. */
const $ = (selector, root = document) => root.querySelector(selector);

const SAFE_BACK_RE = /^\/(ask|bazi|astro|tarot|name|dream|daily|login|privacy)$/;
const BACK_LABELS = {
  "/ask": "问道",
  "/bazi": "八字",
  "/astro": "星盘",
  "/tarot": "塔罗",
  "/name": "姓名",
  "/dream": "解梦",
  "/daily": "运势",
  "/login": "登录页",
  "/privacy": "隐私说明",
};

function resolveBackTarget() {
  const params = new URLSearchParams(location.search);
  const from = params.get("from") || "";
  if (SAFE_BACK_RE.test(from)) {
    try {
      sessionStorage.setItem("zhiming.billing_from", from);
    } catch {
      // Ignore storage failures.
    }
    return from;
  }
  let stored = "";
  try {
    stored = sessionStorage.getItem("zhiming.billing_from") || "";
  } catch {
    stored = "";
  }
  if (document.referrer) {
    try {
      const ref = new URL(document.referrer);
      if (ref.origin === location.origin && SAFE_BACK_RE.test(ref.pathname)) {
        if (ref.pathname === "/login" && SAFE_BACK_RE.test(stored) && stored !== "/login") {
          return stored;
        }
        try {
          sessionStorage.setItem("zhiming.billing_from", ref.pathname);
        } catch {
          // Ignore storage failures.
        }
        return ref.pathname;
      }
    } catch {
      // Ignore invalid referrer URL.
    }
  }
  if (SAFE_BACK_RE.test(stored)) return stored;
  return "/ask";
}

const backTarget = resolveBackTarget();
const backBtn = $("#billing-back-btn");
if (backBtn) {
  const label = BACK_LABELS[backTarget];
  if (label) backBtn.title = `返回${label}`;
  backBtn.addEventListener("click", () => {
    location.assign(backTarget);
  });
}

let accountState = null;
let plansData = null;
let toastTimer = null;

function node(tag, className = "", text = "") {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text) el.textContent = text;
  return el;
}

function button(label, className = "btn", type = "button") {
  const el = node("button", className, label);
  el.type = type;
  return el;
}

function toast(text) {
  const box = $("#toast");
  if (!box) return;
  box.textContent = text;
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    box.hidden = true;
  }, 4200);
}

function formatShanghaiTime(seconds) {
  if (!seconds) return "";
  return new Date(seconds * 1000).toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Zhiming-Client": "web",
      ...options.headers,
    },
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    const detail = data?.detail;
    const msg =
      detail?.message ||
      (typeof detail === "string" ? detail : "") ||
      "请求未能完成，请稍后重试。";
    const err = new Error(msg);
    err.code = detail?.code;
    err.status = response.status;
    throw err;
  }
  return data;
}

function showCheckoutStatus(planName, payUrl, opened) {
  const box = $("#billing-status-box");
  if (!box) return;
  box.hidden = false;
  const text = opened
    ? `已在新标签页打开「${planName}」支付页。支付完成后通常数秒自动到账，也可点击下方「我已支付，刷新额度」。`
    : "浏览器拦截了新标签页，请点击下方链接前往爱发电完成支付：";
  const link = node("a", "account-link", `前往爱发电完成「${planName}」支付 →`);
  link.href = payUrl;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  box.replaceChildren(node("p", "", text), link);
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderAccountSummary() {
  const emailEl = $("#billing-account-email");
  const headerLink = $("#billing-account-link");
  const badgesEl = $("#billing-badges");
  const detailEl = $("#billing-quota-detail");
  const guestBox = $("#billing-guest-box");
  const guestCopy = $("#billing-guest-copy");
  const actionsRow = $("#billing-account-actions");
  const selfHelp = $("#billing-self-help");
  const ordersSection = $("#billing-orders-section");
  const ordersList = $("#billing-orders-list");

  const account = accountState?.account;
  const freeReg = plansData?.free_registration_tokens ?? accountState?.registration_free_tokens;

  if (!account) {
    emailEl.textContent = "访客身份（未登录）";
    headerLink.textContent = "登录 / 注册";
    headerLink.href = "/login?tab=account&next=/billing";
    headerLink.classList.remove("signed");
    badgesEl.hidden = true;
    detailEl.hidden = true;
    actionsRow.hidden = true;
    selfHelp.hidden = true;
    ordersSection.hidden = true;
    guestBox.hidden = false;
    if (Number.isInteger(freeReg)) {
      guestCopy.textContent = `当前未登录。新注册账号即赠 ${freeReg.toLocaleString("zh-CN")} Tokens 永久免费额度；登录后可在此直接充值月度额度，跨设备同步保存。`;
    }
    return;
  }

  emailEl.textContent = account.email;
  headerLink.textContent = account.email;
  headerLink.href = "/ask";
  headerLink.title = `${account.email} · 返回问道`;
  headerLink.classList.add("signed");
  guestBox.hidden = true;
  actionsRow.hidden = false;

  const billing = account.billing;
  const quota = account.quota;

  badgesEl.replaceChildren();
  if (billing?.badges?.length) {
    for (const item of billing.badges) {
      const pill = node("span", `billing-badge billing-badge-${item.key}`);
      if (item.key === "tip") {
        pill.textContent =
          item.count > 1 ? `🍵 一盏清茶 · 赞赏 ${item.count} 次` : "🍵 一盏清茶 · 感谢赞赏";
      } else {
        pill.textContent = `${item.label}${item.expires_at ? ` · 至 ${formatShanghaiTime(item.expires_at)}` : ""}`;
      }
      badgesEl.append(pill);
    }
    badgesEl.hidden = false;
  } else {
    badgesEl.hidden = true;
  }

  detailEl.replaceChildren();
  if (quota?.limit === null) {
    detailEl.append(
      node("div", "quota-line", ""),
      node("p", "quota-line-note", "此账号不受账号额度限制；全站预算、并发和异常消耗保护仍生效。"),
    );
    detailEl.firstChild.append(
      node("span", "quota-line-label", "账号额度"),
      node("span", "quota-line-value", "不限"),
    );
    detailEl.hidden = false;
  } else if (billing?.quota) {
    const sub = billing.quota.subscription;
    const perm = billing.quota.permanent;
    const totalRow = node("div", "quota-line");
    totalRow.append(
      node("span", "quota-line-label", "当前总可用额度"),
      node("span", "quota-line-value", `${Number(quota?.remaining ?? 0).toLocaleString("zh-CN")} token`),
    );
    detailEl.append(totalRow);

    if (sub && (sub.limit > 0 || sub.upcoming_grants?.length)) {
      const subRow = node("div", "quota-line");
      subRow.append(
        node("span", "quota-line-label", "当月订阅额度"),
        node(
          "span",
          "quota-line-value",
          `${sub.remaining.toLocaleString("zh-CN")} / ${sub.limit.toLocaleString("zh-CN")} token`,
        ),
      );
      detailEl.append(subRow);
      if (sub.earliest_expires_at) {
        const expText =
          sub.latest_expires_at && sub.latest_expires_at !== sub.earliest_expires_at
            ? `最早到期 ${formatShanghaiTime(sub.earliest_expires_at)}（最晚 ${formatShanghaiTime(sub.latest_expires_at)}）；同周期重复订阅已叠加，优先扣减最早到期额度。`
            : `有效期至 ${formatShanghaiTime(sub.earliest_expires_at)}（订阅日起至下月同日），系统优先扣减此额度。`;
        detailEl.append(node("p", "quota-line-note", expText));
      }
      if (sub.upcoming_grants?.length) {
        detailEl.append(
          node(
            "p",
            "quota-line-note",
            `另有 ${sub.upcoming_grants.length} 期后续月度额度将在 ${formatShanghaiTime(sub.upcoming_grants[0].starts_at)} 起依次生效。`,
          ),
        );
      }
    }

    if (perm && perm.limit !== null) {
      const permRow = node("div", "quota-line");
      permRow.append(
        node("span", "quota-line-label", "永久免费 / 赠予额度"),
        node(
          "span",
          "quota-line-value",
          `${perm.remaining.toLocaleString("zh-CN")} / ${perm.limit.toLocaleString("zh-CN")} token`,
        ),
      );
      detailEl.append(permRow);
    }
    detailEl.hidden = false;
  } else {
    detailEl.hidden = true;
  }

  const enabled = Boolean(plansData?.enabled ?? billing?.enabled);
  selfHelp.hidden = !enabled;
  const refreshBtn = $("#billing-refresh-btn");
  if (refreshBtn) refreshBtn.hidden = !enabled;

  const creatorUrl = plansData?.creator_url || billing?.creator_url || "";
  const creatorLink = $("#billing-creator-link");
  if (creatorLink) {
    if (creatorUrl) {
      creatorLink.href = creatorUrl;
      creatorLink.hidden = false;
    } else {
      creatorLink.hidden = true;
    }
  }

  ordersList.replaceChildren();
  if (billing?.orders?.length) {
    for (const order of billing.orders) {
      const li = node("li", "billing-order-item");
      const meta =
        order.status === "tip_recorded"
          ? `纯赞赏 · ¥${order.total_amount}`
          : `+${Number(order.tokens_granted || 0).toLocaleString("zh-CN")} token · ¥${order.total_amount}` +
            (order.expires_at ? ` · 至 ${formatShanghaiTime(order.expires_at)}` : "");
      li.append(
        node(
          "div",
          "billing-order-main",
          `${order.plan_name}${order.month > 1 ? ` × ${order.month} 个月` : ""}`,
        ),
        node("div", "billing-order-meta", `${meta} · ${formatShanghaiTime(order.at)}`),
      );
      ordersList.append(li);
    }
    ordersSection.hidden = false;
  } else {
    ordersSection.hidden = true;
  }
}

async function startCheckout(plan, btn) {
  if (!accountState?.account) {
    location.assign(`/login?tab=account&next=${encodeURIComponent("/billing")}`);
    return;
  }
  btn.disabled = true;
  try {
    const checkout = await api("/api/billing/afdian/checkout", {
      method: "POST",
      body: JSON.stringify({ plan_key: plan.key }),
    });
    const opened = window.open(checkout.pay_url, "_blank", "noopener,noreferrer");
    showCheckoutStatus(plan.name, checkout.pay_url, Boolean(opened));
  } catch (error) {
    toast(error.message);
  } finally {
    btn.disabled = false;
  }
}

function renderPlans() {
  const subWrap = $("#billing-sub-plans");
  const disabledBox = $("#billing-disabled-box");
  const tipSection = $("#billing-tip-section");
  const tipCardWrap = $("#billing-tip-card");
  const rulesList = $("#billing-rules-list");

  const lead = $("#billing-lead");
  if (lead && Number.isInteger(plansData?.free_registration_tokens)) {
    lead.textContent = `新账号注册即赠 ${plansData.free_registration_tokens.toLocaleString("zh-CN")} Tokens 永久免费额度，历法排盘与离线演示不扣额度。需要更多大模型深度解读时，可通过爱发电自助订阅月度额度，支付完成后通常数秒自动到账。`;
  }

  if (plansData?.rules?.length) {
    rulesList.replaceChildren();
    for (const rule of plansData.rules) {
      rulesList.append(node("li", "", rule));
    }
  }

  subWrap.replaceChildren();
  tipCardWrap.replaceChildren();

  if (!plansData?.enabled || !plansData?.plans?.length) {
    disabledBox.hidden = false;
    tipSection.hidden = true;
    return;
  }
  disabledBox.hidden = true;

  const subPlans = plansData.plans.filter((p) => p.key !== "tip");
  const tipPlan = plansData.plans.find((p) => p.key === "tip");

  for (const plan of subPlans) {
    const card = node("article", `billing-tier billing-tier-${plan.key}`);
    const head = node("div", "billing-tier-head");
    const titleWrap = node("div", "billing-tier-title");
    titleWrap.append(node("h3", "", plan.name));
    if (plan.key === "pro") {
      titleWrap.append(node("span", "billing-tier-tag", "推荐 · 高性价比"));
    } else if (plan.key === "plus") {
      titleWrap.append(node("span", "billing-tier-tag", "轻量月度"));
    }
    head.append(titleWrap, node("span", "billing-tier-price", plan.price_display));

    const quotaBox = node("div", "billing-tier-quota");
    quotaBox.append(
      node("strong", "", Number(plan.tokens_per_month || 0).toLocaleString("zh-CN")),
      node("span", "", "Tokens / 月"),
    );

    const desc = node("p", "billing-tier-desc", plan.description);
    const points = node("ul", "billing-tier-points");
    points.append(
      node("li", "", "订阅时刻起至下月同日同时刻有效，按滚动月计算"),
      node("li", "", "系统优先扣减月度额度，永久免费额度保持不动"),
      node("li", "", "同周期重复订阅或从 Plus 升级至 Pro，额度直接叠加"),
    );

    const ctaWrap = node("div", "billing-tier-cta");
    const ctaLabel = accountState?.account
      ? `立即充值 · 订阅 ${plan.name}`
      : `登录后订阅 ${plan.name}`;
    const go = button(ctaLabel, "btn btn-primary");
    go.dataset.planKey = plan.key;
    go.addEventListener("click", () => startCheckout(plan, go));
    ctaWrap.append(go);

    card.append(head, quotaBox, desc, points, ctaWrap);
    subWrap.append(card);
  }

  if (tipPlan) {
    const tipCard = node("div", "billing-tip-card");
    const info = node("div", "billing-tip-info");
    const head = node("div", "billing-tip-head");
    head.append(
      node("strong", "", `🍵 ${tipPlan.name}`),
      node("span", "billing-plan-price", tipPlan.price_display),
    );
    info.append(head, node("p", "billing-plan-desc", tipPlan.description));
    const go = button(
      accountState?.account ? "赞赏一盏清茶" : "登录后赞赏一盏清茶",
      "btn btn-ghost",
    );
    go.dataset.planKey = tipPlan.key;
    go.addEventListener("click", () => startCheckout(tipPlan, go));
    tipCard.append(info, go);
    tipCardWrap.append(tipCard);
    tipSection.hidden = false;
  } else {
    tipSection.hidden = true;
  }
}

async function syncOrders(btn) {
  if (!accountState?.account) return;
  btn.disabled = true;
  try {
    const res = await api("/api/billing/afdian/sync", { method: "POST", body: "{}" });
    if (res.quota) accountState.account.quota = res.quota;
    if (res.billing) accountState.account.billing = res.billing;
    renderAccountSummary();
    const added = (res.sync?.credited || 0) + (res.sync?.tip_recorded || 0);
    toast(added > 0 ? "已同步最新爱发电订单，额度已更新。" : "已完成同步，暂无新的待入账订单。");
  } catch (error) {
    toast(error.message);
  } finally {
    btn.disabled = false;
  }
}

async function load() {
  try {
    const [plans, account] = await Promise.all([
      api("/api/billing/plans"),
      api("/api/account"),
    ]);
    plansData = plans;
    accountState = account;
  } catch (error) {
    toast(error.message || "加载额度与方案信息失败，请刷新重试。");
    return;
  }
  renderAccountSummary();
  renderPlans();
}

$("#billing-refresh-btn")?.addEventListener("click", (event) => syncOrders(event.currentTarget));
$("#billing-sync-btn")?.addEventListener("click", (event) => syncOrders(event.currentTarget));

$("#billing-claim-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#billing-trade-input");
  const submit = $("#billing-claim-submit");
  const tradeNo = input.value.trim();
  if (!tradeNo || !accountState?.account) return;
  submit.disabled = true;
  try {
    const res = await api("/api/billing/afdian/claim", {
      method: "POST",
      body: JSON.stringify({ out_trade_no: tradeNo }),
    });
    if (res.quota) accountState.account.quota = res.quota;
    if (res.billing) accountState.account.billing = res.billing;
    input.value = "";
    renderAccountSummary();
    toast(
      res.order?.process_status === "tip_recorded"
        ? "感谢一盏清茶赞赏！记录已同步到你的账号。"
        : `订单已核验到账（+${Number(res.order?.tokens_granted || 0).toLocaleString("zh-CN")} token）。`,
    );
  } catch (error) {
    toast(error.message);
  } finally {
    submit.disabled = false;
  }
});

load();
