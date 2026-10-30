"use strict";

// Admin console: site status, monitor checks, usage, cost controls and accounts.
const $ = (selector) => document.querySelector(selector);
const ZONE = "Asia/Shanghai";
const LEVELS = {
  ok: ["✓", "正常"],
  warning: ["!", "警告"],
  critical: ["✕", "严重"],
  unknown: ["?", "未知"],
  info: ["i", "信息"],
};
const SETTINGS = [
  ["daily_token_budget", "全站每日 token 上限", "输入+输出合计，北京时间零点重置；0 表示不限", "int"],
  ["daily_cost_budget", "全站每日估算费用上限", "需同时填写单价；0 表示不限", "float"],
  ["currency", "币种", "例如 CNY、USD", "text"],
  ["input_price_per_mtok", "输入单价 / 百万 token", "按服务商账单填写；0 表示未填写", "float"],
  ["output_price_per_mtok", "输出单价 / 百万 token", "未结算的预留按较高单价估算", "float"],
  ["max_concurrent_calls", "模型并发上限", "全站同时进行的模型请求数；0 表示不限", "int"],
  ["queue_wait_s", "排队等待（秒）", "超过并发后最多等待，之后提示稍后重试", "int"],
  ["burst_window_min", "异常检测窗口（分钟）", "下列两项阈值的统计窗口", "int"],
  ["burst_site_tokens", "窗口内全站 token 阈值", "超过即自动暂停全站模型调用；0 关闭", "int"],
  ["burst_account_tokens", "窗口内单账号 token 阈值", "超过即自动暂停该账号；0 关闭", "int"],
  ["auto_resume_min", "自动暂停后自动恢复（分钟）", "0 表示须管理员手动恢复", "int"],
];
const ACTIONS = {
  update_settings: "修改费用设置",
  reset_settings: "恢复默认设置",
  pause_models: "暂停模型调用",
  resume_models: "恢复模型调用",
  suspend_account: "暂停账号",
  unsuspend_account: "恢复账号",
  grant_tokens: "调整账号额度",
  set_unlimited_quota: "设置账号不限额",
  registration_allowance: "修改新账号默认额度",
  distribute_tokens: "统一发放账号额度",
  probe_interval: "修改模型检测周期",
  probe_model: "立即测试模型",
  revoke_logins: "强制下线",
};
const EVENTS = {
  site_paused_auto: "异常消耗，已自动暂停全站模型调用",
  site_paused: "管理员暂停全站模型调用",
  site_resumed: "管理员恢复模型调用",
  site_resumed_auto: "自动暂停到期，已恢复模型调用",
  account_suspended_auto: "单账号异常消耗，已自动暂停该账号",
  budget_exhausted: "今日全站预算已用完",
};
let data = null;
let accountOffset = 0;
let timer = null;

function node(tag, className = "", text = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== "") element.textContent = text;
  return element;
}

const number = (value) => Number(value || 0).toLocaleString("zh-CN");
const money = (value, currency) =>
  `${Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 4 })} ${currency}`;
function when(seconds) {
  if (!seconds) return "—";
  return new Date(seconds * 1000).toLocaleString("zh-CN", { timeZone: ZONE, hour12: false });
}
function ago(seconds) {
  const delta = Math.max(0, Date.now() / 1000 - seconds);
  if (delta < 90) return `${Math.round(delta)} 秒前`;
  if (delta < 5400) return `${Math.round(delta / 60)} 分钟前`;
  if (delta < 129600) return `${Math.round(delta / 3600)} 小时前`;
  return `${Math.round(delta / 86400)} 天前`;
}
function duration(seconds) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${days ? `${days} 天 ` : ""}${hours} 小时 ${minutes} 分钟`;
}
function bytes(value) {
  return `${(value / 1024 ** 3).toFixed(1)} GiB`;
}

function badge(level, text = "") {
  const [icon, fallback] = LEVELS[level] || LEVELS.unknown;
  const label = text || fallback;
  const element = node("span", `adm-badge adm-${LEVELS[level] ? level : "unknown"}`);
  element.append(node("span", "adm-badge-icon", icon), node("span", "", label));
  return element;
}

function showError(message, target = "#error") {
  $(target).textContent = message;
  $(target).hidden = !message;
}

async function call(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", "X-Zhiming-Client": "web" },
    });
  } catch {
    throw new Error("连接中断，请检查网络后重试。");
  }
  let body = {};
  try {
    body = await response.json();
  } catch {
    // Not JSON (proxy or crash page); the status explains it.
  }
  if (response.status === 404 && path.startsWith("/api/admin/overview")) {
    location.href = "/login?next=/admin";
  }
  if (!response.ok) throw new Error(body.detail?.message || `请求失败（${response.status}）`);
  return body;
}

// ---------- status tiles ----------

function tile(title, value, detail, level, meter) {
  const element = node("article", "adm-tile");
  const head = node("div", "adm-tile-head");
  head.append(node("h3", "", title));
  if (level) head.append(badge(level));
  element.append(head, node("p", "adm-tile-value", value));
  if (meter !== undefined && meter !== null) {
    const bar = node("div", "adm-meter");
    bar.setAttribute("role", "meter");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", "100");
    bar.setAttribute("aria-valuenow", String(Math.min(100, meter)));
    bar.setAttribute("aria-label", `${title} ${meter}%`);
    const fill = node("span", meter >= 100 ? "adm-meter-full" : meter >= 80 ? "adm-meter-high" : "");
    fill.style.width = `${Math.min(100, meter)}%`;
    bar.append(fill);
    element.append(bar);
  }
  if (detail) element.append(node("p", "adm-tile-detail", detail));
  return element;
}

function worstMonitorLevel(monitor) {
  if (!monitor?.checks) return "unknown";
  const order = ["ok", "unknown", "warning", "critical"];
  return monitor.checks.reduce(
    (worst, check) => (order.indexOf(check.level) > order.indexOf(worst) ? check.level : worst),
    "ok",
  );
}

function renderTiles() {
  const { site, monitor } = data;
  const today = site.today;
  const tiles = $("#tiles");
  tiles.replaceChildren();
  tiles.append(
    tile(
      "模型服务",
      site.paused ? "已暂停" : "运行中",
      site.paused
        ? `${site.paused.auto ? "自动" : site.paused.by}暂停于 ${when(site.paused.at)}：${site.paused.reason}`
        : `暂停中的账号 ${site.suspended_accounts} 个`,
      site.paused ? "critical" : "ok",
    ),
  );
  const budget = today.token_budget ? ` / ${number(today.token_budget)}` : "（未设上限）";
  const refused = today.budget_refused_at
    ? `${when(today.budget_refused_at)} 起已拒绝新的模型调用；`
    : "";
  tiles.append(
    tile(
      "今日用量",
      `${number(today.tokens)}${budget}`,
      `${refused}调用 ${number(today.calls)} 次，进行中 ${today.pending}；${when(today.resets_at)} 重置`,
      today.budget_refused_at
        ? "critical"
        : today.budget_percent === null
          ? null
          : today.budget_percent >= 100
            ? "critical"
            : today.budget_percent >= 80
              ? "warning"
              : "ok",
      today.budget_percent,
    ),
  );
  tiles.append(
    tile(
      "今日估算费用",
      today.priced ? money(today.cost, today.currency) : "未填写单价",
      today.cost_budget ? `上限 ${money(today.cost_budget, today.currency)}；估算值，以服务商账单为准` : "估算值，以服务商账单为准",
    ),
  );
  const errors = site.errors;
  const rate = Math.round(errors.rate * 1000) / 10;
  tiles.append(
    tile(
      "近 30 分钟模型错误率",
      errors.calls ? `${rate}%` : "无调用",
      `${errors.errors} / ${errors.calls} 次失败` +
        (Object.keys(errors.kinds).length
          ? `：${Object.entries(errors.kinds).map(([k, v]) => `${k} ×${v}`).join("，")}`
          : ""),
      errors.calls < 5 ? null : rate >= 25 ? "critical" : rate >= 10 ? "warning" : "ok",
    ),
  );
  const gate = site.concurrency;
  tiles.append(
    tile(
      "模型并发",
      `${gate.active} / ${gate.limit > 0 ? gate.limit : "不限"}`,
      `排队 ${gate.waiting}；近 1 小时 ${number(site.last_hour.tokens)} token，7 天小时均值 ${number(site.hourly_average_7d)}`,
    ),
  );
  const level = worstMonitorLevel(monitor);
  const age = monitor?.generated_at ? Date.now() / 1000 - monitor.generated_at : null;
  tiles.append(
    tile(
      "服务器监控",
      monitor?.generated_at ? LEVELS[level][1] : "无报告",
      monitor?.generated_at
        ? `上次检查 ${ago(monitor.generated_at)}${age > 900 ? "，已超过 15 分钟，监控可能未运行" : ""}`
        : "未找到监控状态文件，请确认 zhiming-monitor.timer 已启用",
      age === null || age > 900 ? "warning" : level,
    ),
  );
}

// ---------- checks and events ----------

function renderChecks() {
  const { monitor, site } = data;
  const rows = $("#check-rows");
  rows.replaceChildren();
  const checks = monitor?.checks || [];
  for (const check of checks) {
    const row = node("tr");
    const status = node("td");
    status.append(badge(check.level));
    row.append(
      node("td", "", check.label || check.name),
      status,
      node("td", "", check.summary || ""),
      node("td", "", check.level === "ok" ? "—" : when(check.since)),
    );
    rows.append(row);
  }
  if (!checks.length) {
    const row = node("tr");
    const cell = node("td", "adm-empty", "暂无服务器监控报告。");
    cell.colSpan = 4;
    row.append(cell);
    rows.append(row);
  }
  const channels = monitor?.channels?.length ? monitor.channels.join("、") : "未配置告警渠道";
  $("#monitor-meta").textContent = monitor?.generated_at
    ? `由服务器监控每 5 分钟生成 · 告警渠道：${channels}` +
      (monitor.delivery?.last_error ? ` · 最近一次发送失败：${monitor.delivery.last_error}` : "")
    : "";
  const events = $("#events");
  events.replaceChildren();
  for (const event of site.events) {
    const item = node("li");
    item.append(badge(event.level === "critical" ? "critical" : event.level === "warning" ? "warning" : "info"));
    const detail = event.detail?.reason ? `：${event.detail.reason}` : "";
    item.append(node("span", "", ` ${when(event.at)} · ${EVENTS[event.kind] || event.kind}${detail}`));
    events.append(item);
  }
  if (!site.events.length) events.append(node("li", "adm-empty", "近 24 小时没有费用事件。"));
}

// ---------- usage chart ----------

function hourLabel(start) {
  return new Date(start * 1000).toLocaleString("zh-CN", {
    timeZone: ZONE,
    hour: "2-digit",
    hour12: false,
  });
}

function renderUsage() {
  const hours = data.hourly;
  const peak = Math.max(1, ...hours.map((hour) => hour.tokens));
  const chart = $("#chart");
  chart.replaceChildren();
  const plot = node("div", "adm-plot");
  const tooltip = $("#tooltip");
  hours.forEach((hour, index) => {
    const column = node("div", "adm-col");
    const bar = node("div", hour.errors ? "adm-bar adm-bar-errors" : "adm-bar");
    bar.style.height = `${hour.tokens ? Math.max(2, (100 * hour.tokens) / peak) : 0}%`;
    column.tabIndex = 0;
    const text = `${hourLabel(hour.start)}：${number(hour.tokens)} token，调用 ${hour.calls} 次${hour.errors ? `，失败 ${hour.errors} 次` : ""}`;
    column.setAttribute("aria-label", text);
    const show = () => {
      tooltip.textContent = text;
      tooltip.hidden = false;
      const box = column.getBoundingClientRect();
      tooltip.style.left = `${Math.min(window.innerWidth - 220, Math.max(8, box.left + window.scrollX - 80))}px`;
      tooltip.style.top = `${box.top + window.scrollY - 40}px`;
    };
    const hide = () => {
      tooltip.hidden = true;
    };
    column.addEventListener("mouseenter", show);
    column.addEventListener("focus", show);
    column.addEventListener("mouseleave", hide);
    column.addEventListener("blur", hide);
    column.append(bar);
    if (index % 4 === 0 || index === hours.length - 1) column.append(node("span", "adm-tick", hourLabel(hour.start)));
    plot.append(column);
  });
  const axis = node("div", "adm-axis");
  axis.append(node("span", "", number(peak)), node("span", "", "0"));
  chart.append(axis, plot);
  const total = hours.reduce((sum, hour) => sum + hour.tokens, 0);
  $("#usage-meta").textContent = `合计 ${number(total)} token；峰值 ${number(peak)} token/小时；有失败调用的小时以斜纹显示。`;
  const rows = $("#hour-rows");
  rows.replaceChildren();
  for (const hour of [...hours].reverse()) {
    const row = node("tr");
    row.append(
      node("td", "", `${when(hour.start)}`),
      node("td", "adm-num", number(hour.tokens)),
      node("td", "adm-num", number(hour.calls)),
      node("td", "adm-num", number(hour.errors)),
    );
    rows.append(row);
  }
  const top = $("#top-rows");
  top.replaceChildren();
  for (const account of data.top_accounts) {
    const row = node("tr");
    row.append(
      node("td", "", account.username || "（已注销）"),
      node("td", "adm-num", number(account.tokens)),
      node("td", "adm-num", number(account.calls)),
    );
    top.append(row);
  }
  if (!data.top_accounts.length) {
    const row = node("tr");
    const cell = node("td", "adm-empty", "今日暂无模型调用。");
    cell.colSpan = 3;
    row.append(cell);
    top.append(row);
  }
}

// ---------- cost controls ----------

function renderControls(force = false) {
  const { site, settings } = data;
  $("#pause-state").textContent = site.paused
    ? `模型调用已暂停（${site.paused.auto ? "异常消耗自动暂停" : `由 ${site.paused.by} 手动暂停`}，${when(site.paused.at)}）：${site.paused.reason}`
    : "模型调用正常运行。";
  $("#pause-box").classList.toggle("adm-paused", Boolean(site.paused));
  $("#pause").hidden = Boolean(site.paused);
  $("#resume").hidden = !site.paused;
  const fields = $("#settings-fields");
  // Keep what the administrator is typing across auto-refreshes.
  if (fields.childElementCount && !force) return;
  fields.replaceChildren();
  for (const [key, label, hint, kind] of SETTINGS) {
    const field = node("label", "field");
    field.append(node("span", "", label));
    const input = node("input");
    input.name = key;
    input.dataset.kind = kind;
    input.value = settings.effective[key];
    if (kind !== "text") {
      input.inputMode = kind === "int" ? "numeric" : "decimal";
    } else {
      input.maxLength = 8;
    }
    const overridden = key in settings.overrides;
    field.append(input);
    field.append(
      node(
        "small",
        "adm-hint",
        `${hint}${overridden ? ` · 已覆盖，配置默认 ${settings.defaults[key]}` : ""}`,
      ),
    );
    fields.append(field);
  }
}

$("#settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("", "#settings-error");
  const changes = {};
  for (const input of $("#settings-fields").querySelectorAll("input")) {
    const current = data.settings.effective[input.name];
    const raw = input.value.trim();
    if (input.dataset.kind === "text") {
      if (raw !== current) changes[input.name] = raw;
      continue;
    }
    const value = Number(raw);
    if (raw === "" || !Number.isFinite(value)) {
      showError(`「${input.closest("label").firstChild.textContent}」需要填写数字。`, "#settings-error");
      input.focus();
      return;
    }
    if (value !== current) changes[input.name] = value;
  }
  if (!Object.keys(changes).length) {
    showError("没有修改。", "#settings-error");
    return;
  }
  try {
    await call("/api/admin/settings", { method: "PUT", body: JSON.stringify(changes) });
    await load(true);
  } catch (error) {
    showError(error.message, "#settings-error");
  }
});

$("#settings-reset").addEventListener("click", async () => {
  if (!confirm("清除管理台保存的全部覆盖值，恢复为 config.yaml 中的默认设置？")) return;
  try {
    await call("/api/admin/settings/reset", { method: "POST" });
    await load(true);
  } catch (error) {
    showError(error.message, "#settings-error");
  }
});

$("#pause").addEventListener("click", async () => {
  if (!confirm("暂停后，所有账号的真实模型调用都会被拒绝，直到手动恢复。确定暂停？")) return;
  try {
    await call("/api/admin/models/pause", {
      method: "POST",
      body: JSON.stringify({ reason: $("#pause-reason").value.trim() }),
    });
    $("#pause-reason").value = "";
    await load();
  } catch (error) {
    showError(error.message);
  }
});

$("#resume").addEventListener("click", async () => {
  try {
    await call("/api/admin/models/resume", { method: "POST" });
    await load();
  } catch (error) {
    showError(error.message);
  }
});

// ---------- accounts ----------

async function loadAccounts() {
  const query = encodeURIComponent($("#account-query").value.trim());
  const result = await call(`/api/admin/accounts?q=${query}&offset=${accountOffset}&limit=50`);
  const rows = $("#account-rows");
  rows.replaceChildren();
  for (const account of result.items) {
    const row = node("tr");
    const state = node("td");
    state.append(account.suspended ? badge("critical", "已暂停") : badge("ok", "可用"));
    if (account.suspended) state.append(node("small", "adm-hint", ` ${account.suspended.reason}`));
    const actions = node("td", "adm-actions");
    const toggle = node("button", "btn btn-text", account.suspended ? "恢复调用" : "暂停调用");
    toggle.type = "button";
    toggle.addEventListener("click", () => accountAction(account, account.suspended ? "unsuspend" : "suspend"));
    const grant = node("button", "btn btn-text", "调整额度");
    grant.type = "button";
    grant.addEventListener("click", () => accountAction(account, "grant"));
    const logout = node("button", "btn btn-text", "强制下线");
    logout.type = "button";
    logout.disabled = !account.logins;
    logout.addEventListener("click", () => accountAction(account, "logout"));
    actions.append(toggle, grant, logout);
    const quota = account.quota;
    row.append(
      node("td", "", account.username),
      node("td", "", new Date(account.created_at).toLocaleDateString("zh-CN", { timeZone: ZONE })),
      node("td", "adm-num", number(account.tokens_today)),
      node(
        "td",
        "adm-num",
        `${number(quota.used)} / ${quota.limit === null ? "不限额" : number(quota.limit)}${quota.bonus ? `（含追加 ${number(quota.bonus)}）` : ""}`,
      ),
      node("td", "adm-num", String(account.logins)),
      state,
      actions,
    );
    rows.append(row);
  }
  if (!result.items.length) {
    const row = node("tr");
    const cell = node("td", "adm-empty", "没有匹配的账号。");
    cell.colSpan = 7;
    row.append(cell);
    rows.append(row);
  }
  const end = Math.min(result.total, accountOffset + result.items.length);
  $("#accounts-meta").textContent = `共 ${result.total} 个账号，显示 ${result.total ? accountOffset + 1 : 0}–${end}`;
  $("#accounts-prev").disabled = accountOffset === 0;
  $("#accounts-next").disabled = end >= result.total;
}

async function accountAction(account, action) {
  const base = `/api/admin/accounts/${encodeURIComponent(account.user_id)}`;
  let body = {};
  if (action === "suspend") {
    const reason = prompt(`暂停账号「${account.username}」的模型调用。原因（可选）：`, "");
    if (reason === null) return;
    body = { reason };
  } else if (action === "grant") {
    const raw = prompt(
      `为账号「${account.username}」追加额度（token，可为负数以收回追加部分）：`,
      "100000",
    );
    if (raw === null) return;
    const tokens = Number(raw);
    if (!Number.isInteger(tokens) || tokens === 0) {
      showError("额度需要填写非零整数。");
      return;
    }
    body = { tokens };
  } else if (action === "logout") {
    if (!confirm(`结束账号「${account.username}」在所有设备上的登录？`)) return;
  }
  try {
    await call(`${base}/${action}`, { method: "POST", body: JSON.stringify(body) });
    showError("");
    await Promise.all([loadAccounts(), load()]);
  } catch (error) {
    showError(error.message);
  }
}

$("#account-search").addEventListener("submit", (event) => {
  event.preventDefault();
  accountOffset = 0;
  loadAccounts().catch((error) => showError(error.message));
});
$("#accounts-prev").addEventListener("click", () => {
  accountOffset = Math.max(0, accountOffset - 50);
  loadAccounts().catch((error) => showError(error.message));
});
$("#accounts-next").addEventListener("click", () => {
  accountOffset += 50;
  loadAccounts().catch((error) => showError(error.message));
});

// ---------- system ----------

function renderSystem() {
  const system = data.system;
  const facts = [
    ["进程启动", `${when(system.started_at)}（已运行 ${duration(system.uptime_s)}）`],
    ["实例编号", system.instance],
    ["内存中的会话", String(system.live_sessions)],
    ["账号总数", number(system.accounts)],
    ["Python", system.python],
  ];
  if (system.disk) {
    const percent = Math.round((100 * system.disk.free) / system.disk.total);
    facts.push(["数据盘可用", `${bytes(system.disk.free)} / ${bytes(system.disk.total)}（${percent}%）`]);
  }
  if (system.release) {
    const release = system.release;
    facts.push([
      "发布版本",
      release.commit || release.error || JSON.stringify(release).slice(0, 160),
    ]);
    if (release.deployed_at) facts.push(["部署时间", String(release.deployed_at)]);
  }
  const list = $("#system-facts");
  list.replaceChildren();
  for (const [term, value] of facts) {
    const item = node("div");
    item.append(node("dt", "", term), node("dd", "", value));
    list.append(item);
  }
  const rows = $("#audit-rows");
  rows.replaceChildren();
  for (const entry of data.audit) {
    const row = node("tr");
    const detail = Object.entries(entry.detail)
      .map(([key, value]) => `${key}=${value}`)
      .join("，");
    row.append(
      node("td", "", when(entry.at)),
      node("td", "", entry.admin),
      node("td", "", ACTIONS[entry.action] || entry.action),
      node("td", "adm-detail", detail || "—"),
    );
    rows.append(row);
  }
  if (!data.audit.length) {
    const row = node("tr");
    const cell = node("td", "adm-empty", "暂无操作记录。");
    cell.colSpan = 4;
    row.append(cell);
    rows.append(row);
  }
}

async function load(force = false) {
  try {
    data = await call("/api/admin/overview");
  } catch (error) {
    showError(error.message);
    return;
  }
  showError("");
  $("#meta").textContent = `已登录管理员 ${data.admin} · 更新于 ${when(data.site.generated_at)}`;
  renderTiles();
  renderChecks();
  renderUsage();
  renderControls(force);
  renderSystem();
  renderAccountSettings(force);
  renderProbe(force);
}

function renderAccountSettings(force = false) {
  const input = $("#registration-tokens");
  if (force || !input.dataset.dirty) input.value = data.registration_free_tokens;
}

function renderProbe(force = false) {
  const probe = data.model_probe;
  if (!probe) return;
  const input = $("#probe-interval");
  if (force || !input.dataset.dirty) input.value = probe.interval_min;
  const latest = probe.latest;
  const labels = {success: "成功", failure: "失败", skipped: "被全站保护阻止"};
  $("#probe-result").textContent = (probe.running ? "检测进行中… " : "") +
    (latest ? `最近检测 ${when(latest.completed_at)}：${labels[latest.status]} · ${latest.latency_ms} ms${latest.error ? ` · ${latest.error}` : ""}` : "尚未执行检测") +
    (probe.next_at ? `；下次约 ${when(probe.next_at)}` : "；定时检测已关闭");
  const rows = $("#probe-history");
  rows.replaceChildren();
  for (const result of probe.history) {
    const row = node("tr");
    for (const value of [when(result.completed_at), result.model || result.provider, labels[result.status] + (result.error ? `（${result.error}）` : ""), `${result.latency_ms} ms`, result.by === "timer" ? "定时" : result.by]) row.append(node("td", "", value));
    rows.append(row);
  }
}

for (const id of ["#registration-tokens", "#probe-interval"]) $(id).addEventListener("input", () => { $(id).dataset.dirty = "true"; });

$("#registration-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#registration-tokens");
  if (!event.target.reportValidity()) return;
  try {
    await call("/api/admin/registration-allowance", {method: "PUT", body: JSON.stringify({tokens: Number(input.value)})});
    delete input.dataset.dirty;
    $("#allowance-result").textContent = "新账号默认免费额度已保存。";
    await load();
  } catch (error) { showError(error.message); }
});

let distribution = null;
try { distribution = JSON.parse(sessionStorage.getItem("zhiming.pendingDistribution") || "null"); } catch { /* Optional recovery across a page refresh. */ }
$("#distribution-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!event.target.reportValidity()) return;
  const tokens = Number($("#distribution-tokens").value);
  if (!distribution) {
    if (!confirm(`向所有现有有限额账号每人追加 ${number(tokens)} token？不限额账号跳过。`)) return;
    distribution = {tokens, request_id: crypto.randomUUID()};
    try { sessionStorage.setItem("zhiming.pendingDistribution", JSON.stringify(distribution)); } catch { /* Retry in this page still retains the request id. */ }
  } else if (distribution.tokens !== tokens) {
    showError("上次发放结果尚未确认，请先用相同额度重试，避免重复发放。"); return;
  }
  const button = event.target.querySelector("button"); button.disabled = true;
  try {
    const result = await call("/api/admin/accounts/distribute", {method: "POST", body: JSON.stringify(distribution)});
    distribution = null;
    try { sessionStorage.removeItem("zhiming.pendingDistribution"); } catch { /* Optional storage. */ }
    $("#allowance-result").textContent = `已向 ${result.recipients} 个账号每人追加 ${number(result.tokens)} token${result.replayed ? "（已确认先前提交成功，未重复发放）" : ""}。`;
    await Promise.all([load(), loadAccounts()]);
  } catch (error) { showError(`${error.message}；可用相同额度重试，不会重复发放。`); }
  finally { button.disabled = false; }
});

$("#probe-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!event.target.reportValidity()) return;
  try {
    await call("/api/admin/model-probe", {method: "PUT", body: JSON.stringify({minutes: Number($("#probe-interval").value)})});
    delete $("#probe-interval").dataset.dirty;
    await load();
  } catch (error) { showError(error.message); }
});

$("#probe-run").addEventListener("click", async () => {
  const button = $("#probe-run"); button.disabled = true;
  $("#probe-result").textContent = "正在发送小型真实请求，请稍候…";
  try {
    await call("/api/admin/model-probe/run", {method: "POST", body: "{}"});
    await load();
  } catch (error) { showError(error.message); }
  finally { button.disabled = false; }
});

function schedule() {
  clearInterval(timer);
  if ($("#auto-refresh").checked) timer = setInterval(() => load(), 30000);
}

$("#refresh").addEventListener("click", () => {
  load();
  loadAccounts().catch((error) => showError(error.message));
});
$("#auto-refresh").addEventListener("change", schedule);

load(true).then(() => loadAccounts().catch((error) => showError(error.message)));
schedule();
