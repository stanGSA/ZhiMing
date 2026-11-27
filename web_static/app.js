"use strict";

/* One script for every consultation page. The shared core handles the session, dialogue,
   reading, birth form and history; PAGES[...] adds what is particular to each page. */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const PAGE = document.body.dataset.page;
const SYSTEM = PAGE === "ask" ? "auto" : PAGE;
const SYSTEM_NAMES = {
  auto: "综合",
  bazi: "八字",
  astro: "星盘",
  tarot: "塔罗",
  name: "姓名",
  dream: "解梦",
  daily: "运势",
};
const SVG_NS = "http://www.w3.org/2000/svg";
const LOCATION_FIELDS = ["country", "province", "city", "district"];
const ELEMENTS = "木火土金水";
const GAN = "甲乙丙丁戊己庚辛壬癸";
const ZHI = "子丑寅卯辰巳午未申酉戌亥";
const GAN_ELEMENT = "木木火火土土金金水水";
const ZHI_ELEMENT = "水土木木土火火土金金土水";
const CN_DIGITS = "〇一二三四五六七八九";
const TIME_PERIODS = [
  ["early_morning", "凌晨"],
  ["morning_early", "早晨"],
  ["forenoon", "上午"],
  ["noon", "中午"],
  ["afternoon", "下午"],
  ["dusk", "傍晚"],
  ["evening", "晚间"],
  ["late_night", "深夜"],
  ["unknown", "完全不记得"],
];
const TIME_PERIOD_LABELS = Object.fromEntries(TIME_PERIODS);

function formatBirthTime(birth) {
  if (!birth) return "完全不记得";
  if (!birth.unknown_time && birth.time) return birth.time;
  return TIME_PERIOD_LABELS[birth.time_period] || "完全不记得";
}

let state = null;
let busy = false;
let currentReading = null;
let followupReadingId = null;
let toastTimer;
let refreshTimer;
let selectedLocation = null;
let locationVersion = 0;
let locationLoading = false;
let locationsReady = Promise.resolve();
let emptyReading = null;
let birthMode = null;
let page = {};
let birthDirty = false;
let formBirthVersion = 0;
let localStateEpoch = 0;
let restoringBirth = 0;
const birthChannel = typeof BroadcastChannel === "function" ? new BroadcastChannel("zhiming-birth") : null;

/* ---------- Small helpers ---------- */

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function svgNode(tag, attributes = {}, text) {
  const element = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attributes))
    element.setAttribute(key, String(value));
  if (text !== undefined) element.textContent = text;
  return element;
}

function button(text, className, type = "button") {
  const element = node("button", className, text);
  element.type = type;
  return element;
}

function cnNumber(value) {
  if (value < 10) return CN_DIGITS[value];
  const tens = Math.floor(value / 10);
  const ones = value % 10;
  return (tens > 1 ? CN_DIGITS[tens] : "") + "十" + (ones ? CN_DIGITS[ones] : "");
}

function elementOf(char) {
  const stem = GAN.indexOf(char);
  if (stem >= 0) return GAN_ELEMENT[stem];
  const branch = ZHI.indexOf(char);
  return branch >= 0 ? ZHI_ELEMENT[branch] : "";
}

function elementTag(element, className = "el") {
  const tag = node("span", className, element || "—");
  if (element) tag.dataset.element = element;
  return tag;
}

function formatDegrees(value) {
  const degrees = Math.floor(value);
  const minutes = Math.floor((value - degrees) * 60);
  return `${String(degrees).padStart(2, "0")}°${String(minutes).padStart(2, "0")}′`;
}

function shanghaiToday() {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" });
}

function chineseDate(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return `${year}年${month}月${day}日`;
}

function toast(message) {
  const box = $("#toast");
  clearTimeout(toastTimer);
  box.textContent = message;
  box.hidden = false;
  toastTimer = setTimeout(() => {
    box.hidden = true;
  }, 4800);
}

const STATUS_TEXT = {
  413: "提交的内容过大，请精简后再试。",
  429: "操作过于频繁，请稍后再试。",
  500: "服务出现意外错误，请稍后重试。",
  502: "服务暂时无法连接，请稍后重试。",
  503: "服务暂时不可用，请稍后重试。",
  504: "服务响应超时，请稍后重试。",
};

async function api(path, options = {}) {
  const scoped = new URL(path, location.origin);
  if (["/api/session", "/api/birth"].includes(scoped.pathname))
    scoped.searchParams.set("system", SYSTEM);
  path = scoped.pathname + scoped.search;
  // A reading may take minutes; everything else should answer well within a minute.
  const controller = new AbortController();
  const timer = scoped.pathname === "/api/chat" ? null : setTimeout(() => controller.abort(), 60000);
  let response;
  try {
    response = await fetch(path, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        "X-Zhiming-Client": "web",
        ...(state ? { "X-Zhiming-Birth-Version": String(birthDirty ? formBirthVersion : state.birth_version ?? 0) } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new Error(
      controller.signal.aborted
        ? "服务响应超时，请稍后重试。刷新页面可查看本轮状态。"
        : navigator.onLine === false
          ? "网络已断开，请连接网络后重试。"
          : "连接暂时中断，请检查本地网页服务。刷新页面可查看本轮状态。",
    );
  } finally {
    clearTimeout(timer);
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    // A proxy error page or an interrupted body is not JSON; the status still explains it.
  }
  if (!response.ok) {
    const detail = data?.detail;
    const error = new Error(
      detail?.message ||
        (typeof detail === "string" ? detail : "") ||
        STATUS_TEXT[response.status] ||
        "请求未能完成，请检查填写的内容后重试。",
    );
    error.code = detail?.code;
    error.status = response.status;
    if (detail?.request_id) error.message += `（错误编号 ${detail.request_id}）`;
    if (error.code === "session_expired") sessionExpired();
    throw error;
  }
  if (data === null) throw new Error("服务返回的内容无法读取，请刷新页面后重试。");
  return data;
}

/* ---------- Account, notices and storage ---------- */

function remembered(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function remember(key, value) {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch {
    // Storage may be disabled; these keys are conveniences only.
  }
}

function takeNotice() {
  try {
    const text = sessionStorage.getItem("zhiming.notice");
    sessionStorage.removeItem("zhiming.notice");
    return text;
  } catch {
    return null;
  }
}

/* A persistent banner for states a toast would let slip by: an expired login, a restart. */
function showNotice(text, actions = []) {
  let box = $("#notice");
  if (!box) {
    box = node("div", "notice");
    box.id = "notice";
    box.setAttribute("role", "alert");
    document.body.prepend(box);
  }
  const row = node("div", "notice-actions");
  for (const [label, action] of actions) {
    const item = button(label, "btn btn-tag");
    item.addEventListener("click", action);
    row.append(item);
  }
  const dismiss = button("知道了", "btn btn-text");
  dismiss.addEventListener("click", () => box.remove());
  row.append(dismiss);
  box.replaceChildren(node("p", "", text), row);
}

function loginUrl() {
  return `/login?tab=account&next=${encodeURIComponent(location.pathname)}`;
}

function sessionExpired() {
  if (state?.account || remembered("zhiming.account")) {
    remember("zhiming.account", null);
    showNotice("登录已过期或已在其他设备退出。记录仍保存在账号中，重新登录即可继续。", [
      ["重新登录", () => location.assign(loginUrl())],
    ]);
  } else {
    showNotice("会话已过期，刷新页面即可重新开始。访客记录无法找回；登录账号可长期保存。", [
      ["刷新页面", () => location.reload()],
    ]);
  }
}

function storageNote() {
  return state?.account
    ? `已保存到账号「${state.account.email}」，换设备登录也能看到。`
    : "只保存在本次浏览器会话中，闲置 12 小时后清除；登录账号可长期保存。";
}

function renderAccount() {
  const chip = $("#account-button");
  if (!chip) return;
  chip.textContent = state?.account ? state.account.email : "登录";
  chip.classList.toggle("signed", Boolean(state?.account));
  chip.title = state?.account ? `${state.account.email} · 账号与云端记录` : "登录或注册，云端保存记录";
  $$("[data-storage-note]").forEach((note) => {
    note.textContent = storageNote();
  });
  const feedback = $("#birth-feedback");
  if (feedback && Object.values(BIRTH_DEFAULTS).includes(feedback.textContent))
    feedback.textContent = birthDefaultText();
}

const BIRTH_DEFAULTS = {
  guest: "确认后保存在本次浏览器会话中。",
  account: "确认后保存到账号，各页与各设备共用。",
};

function birthDefaultText() {
  return state?.account ? BIRTH_DEFAULTS.account : BIRTH_DEFAULTS.guest;
}

function accountField(label, id, autocomplete) {
  const input = node("input");
  input.id = id;
  input.type = "password";
  input.autocomplete = autocomplete;
  input.maxLength = 128;
  input.required = true;
  return labelled(label, input);
}

function openAccount() {
  const dialog = $("#account-dialog");
  const account = state?.account;
  const close = button("关闭", "btn btn-ghost");
  close.addEventListener("click", () => dialog.close());
  const privacy = node("a", "account-link", "隐私说明");
  privacy.href = "/privacy";
  if (!account) {
    const login = node("a", "btn btn-primary", "登录 / 注册");
    login.href = loginUrl();
    const actions = node("div", "btn-row");
    actions.append(login, close);
    dialog.replaceChildren(
      node("h2", "", "访客身份"),
      node(
        "p",
        "",
        "记录只保存在这台电脑的本次浏览器会话中，闲置 12 小时后清除。登录或注册后，生辰档案与解读会保存到账号，换设备也能查看；注册时可以把本次访客记录一并保存。",
      ),
      actions,
      privacy,
    );
    dialog.showModal();
    return;
  }
  const since = new Date(account.created_at);
  const intro = node(
    "p",
    "",
    `${Number.isNaN(since.getTime()) ? "" : `注册于 ${since.toLocaleDateString("zh-CN", { timeZone: "Asia/Shanghai" })} · `}生辰档案与解读记录已保存到账号，可在任意设备登录查看。`,
  );
  const exportLink = node("a", "btn btn-ghost", "导出我的记录");
  exportLink.href = "/api/export";
  exportLink.download = "";
  const logout = button("退出登录", "btn btn-ghost");
  logout.addEventListener("click", async () => {
    logout.disabled = true;
    try {
      await api("/api/account/logout", { method: "POST", body: "{}" });
      remember("zhiming.account", null);
      location.assign("/login");
    } catch (error) {
      logout.disabled = false;
      toast(error.message);
    }
  });
  const actions = node("div", "btn-row");
  actions.append(exportLink, logout, close);

  const password = node("details", "account-section");
  password.append(node("summary", "", "修改密码"));
  const passwordForm = node("form", "account-form");
  const passwordSubmit = button("确认修改", "btn btn-primary", "submit");
  passwordForm.append(
    accountField("当前密码", "current-password", "current-password"),
    accountField("新密码（至少 8 位，含两类字符）", "new-password", "new-password"),
    accountField("再次输入新密码", "repeat-password", "new-password"),
    passwordSubmit,
  );
  passwordForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if ($("#new-password").value !== $("#repeat-password").value) {
      toast("两次输入的新密码不一致。");
      return;
    }
    passwordSubmit.disabled = true;
    try {
      const result = await api("/api/account/password", {
        method: "POST",
        body: JSON.stringify({
          current_password: $("#current-password").value,
          new_password: $("#new-password").value,
        }),
      });
      passwordForm.reset();
      password.open = false;
      toast(result.signed_out_elsewhere
        ? `密码已修改，其他 ${result.signed_out_elsewhere} 处登录已退出。`
        : "密码已修改。");
    } catch (error) {
      toast(error.message);
    } finally {
      passwordSubmit.disabled = false;
    }
  });
  password.append(passwordForm);

  const removal = node("details", "account-section danger");
  removal.append(node("summary", "", "注销账号"));
  const removalForm = node("form", "account-form");
  const removalSubmit = button("永久注销", "btn btn-danger", "submit");
  removalForm.append(
    node("p", "", "将删除账号、生辰档案、全部解读与运行日志，并退出所有设备。此操作无法撤回，可先导出记录。"),
    accountField("输入密码确认", "delete-password", "current-password"),
    removalSubmit,
  );
  removalForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy) {
      toast("正在解读，请等待本轮完成后再注销。");
      return;
    }
    removalSubmit.disabled = true;
    try {
      await api("/api/account/delete", {
        method: "POST",
        body: JSON.stringify({ password: $("#delete-password").value }),
      });
      remember("zhiming.account", null);
      location.assign("/login");
    } catch (error) {
      removalSubmit.disabled = false;
      toast(error.message);
    }
  });
  removal.append(removalForm);
  dialog.replaceChildren(node("h2", "", account.email), intro, actions, password, removal, privacy);
  dialog.showModal();
}

/* Resolves true when the person confirms; one dialog serves every destructive action. */
function askConfirm({ title, text, confirm = "确认", keep = "保留" }) {
  const dialog = $("#confirm-dialog");
  if (dialog.open) return Promise.resolve(false);
  $("h2", dialog).textContent = title;
  $("p", dialog).textContent = text;
  $("button[value=confirm]", dialog).textContent = confirm;
  $("button[value=cancel]", dialog).textContent = keep;
  dialog.returnValue = "";
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), { once: true });
  });
}

function calculations(reading, prefix) {
  return Object.entries(reading?.calculations || {})
    .filter(([key]) => key.startsWith(prefix))
    .map(([, value]) => value);
}

/* ---------- Page chrome: toast, history drawer, confirm dialog ---------- */

function injectChrome() {
  const toastBox = node("div", "toast");
  toastBox.id = "toast";
  toastBox.setAttribute("role", "status");
  toastBox.hidden = true;

  const scrim = node("div", "scrim");
  scrim.id = "scrim";
  scrim.hidden = true;
  scrim.addEventListener("click", closeDrawer);

  const drawer = node("aside", "drawer");
  drawer.id = "history-drawer";
  drawer.hidden = true;
  drawer.tabIndex = -1;
  drawer.setAttribute("aria-labelledby", "history-title");
  const head = node("div", "drawer-head");
  const title = node("h2", "", "问道足迹");
  title.id = "history-title";
  const close = button("关闭", "btn btn-text");
  close.addEventListener("click", closeDrawer);
  head.append(title, close);
  const tools = node("div", "drawer-tools");
  const search = node("input", "underline-input");
  search.id = "history-search";
  search.type = "search";
  search.maxLength = 100;
  search.placeholder = "搜索问题或解读";
  search.setAttribute("aria-label", "搜索足迹");
  const filter = node("select", "drawer-filter");
  filter.id = "history-filter";
  filter.setAttribute("aria-label", "按功能筛选");
  filter.append(new Option("全部", ""));
  for (const [value, name] of Object.entries(SYSTEM_NAMES))
    if (value !== "auto") filter.append(new Option(name, value));
  tools.append(search, filter);
  const count = node("p", "drawer-count");
  count.id = "history-count";
  count.setAttribute("role", "status");
  const list = node("div", "drawer-list");
  list.id = "history-list";
  const more = button("加载更多", "btn btn-tag");
  more.id = "history-more";
  more.hidden = true;
  const foot = node("div", "drawer-foot");
  const exportLink = node("a", "btn btn-text", "导出记录");
  exportLink.id = "history-export";
  exportLink.href = "/api/export";
  exportLink.download = "";
  const clear = button("清空解读记录", "btn btn-text");
  clear.id = "history-clear";
  clear.setAttribute("data-lock", "");
  const note = node("p", "drawer-note");
  note.setAttribute("data-storage-note", "");
  foot.append(exportLink, clear, note);
  drawer.append(head, tools, count, list, more, foot);

  const dialog = node("dialog", "zm-dialog");
  dialog.id = "confirm-dialog";
  const form = node("form");
  form.method = "dialog";
  const actions = node("div", "btn-row");
  const keep = button("保留记录", "btn btn-ghost", "submit");
  keep.value = "cancel";
  const confirm = button("确认清除", "btn btn-danger", "submit");
  confirm.value = "confirm";
  actions.append(keep, confirm);
  form.append(node("h2", "", ""), node("p", "", ""), actions);
  dialog.append(form);

  const account = node("dialog", "zm-dialog account-dialog");
  account.id = "account-dialog";
  account.setAttribute("aria-label", "账号");
  document.body.append(toastBox, scrim, drawer, dialog, account);
  const chip = button("登录", "btn btn-text zm-account");
  chip.id = "account-button";
  chip.setAttribute("aria-haspopup", "dialog");
  chip.addEventListener("click", openAccount);
  $(".zm-tools")?.append(chip);
  if ($("#dialog")) document.body.append(askFab());
}

/* The dialogue window may sit below the fold; a floating button brings it back into view. */
function askFab() {
  const fab = button("", "ask-fab");
  fab.id = "ask-fab";
  fab.hidden = true;
  fab.append(node("span", "ask-fab-seal", "问"), node("span", "", "对话"));
  fab.setAttribute("aria-label", "前往对话窗发问");
  fab.addEventListener("click", () => {
    if (page.onFab?.()) return;
    $("#dialog").scrollIntoView({ behavior: "smooth", block: "center" });
    $("#message")?.focus({ preventScroll: true });
  });
  new IntersectionObserver(([entry]) => {
    fab.hidden = entry.isIntersecting;
  }).observe($("#dialog"));
  return fab;
}

function openDrawer() {
  $("#history-drawer").hidden = false;
  $("#scrim").hidden = false;
  $("#history-drawer").focus();
  if (historyFiltered()) loadHistory(true);
}

function closeDrawer() {
  if ($("#history-drawer").hidden) return;
  $("#history-drawer").hidden = true;
  $("#scrim").hidden = true;
  $("#open-history")?.focus();
}

/* ---------- Busy state and dialogue ---------- */

function setBusy(value) {
  busy = value;
  const locked = value || !state;
  $$(
    "[data-lock], #send, #provider, #new-chat, #forget, .reading-followups button, #messages .welcome button, #birth-form input, #birth-form select, #birth-form button",
  ).forEach((element) => {
    element.disabled = locked;
  });
  if ($("#message")) $("#message").disabled = locked;
  syncTimeControl();
  if ($("#input-hint"))
    $("#input-hint").textContent = value
      ? "正在整理线索，请稍候……"
      : page.hint || "Enter 发送 · Shift + Enter 换行";
  $("#chat-form")?.setAttribute("aria-busy", String(value));
  if ($("#birth-form")) updateLocationDisabled();
  page.onBusy?.(value);
}

function scrollTranscript() {
  const box = $("#messages");
  if (box) box.scrollTop = box.scrollHeight;
}

function showMessage(message) {
  const item = node(
    "article",
    `msg msg-${message.role}${message.status === "error" ? " msg-error" : ""}`,
  );
  item.append(node("span", "msg-label", message.role === "user" ? "问" : "答"));
  const body = node("div", "msg-body");
  if (message.stale) body.append(node("p", "reading-confidence", "旧生辰记录"));
  body.append(node("p", "msg-text", message.text));
  if (message.role === "assistant" && message.status === "submit_reading" && $("#reading")
    && message.text.length > 140) {
    body.classList.add("msg-long");
    const more = button("展开全文", "msg-more");
    more.setAttribute("aria-expanded", "false");
    more.addEventListener("click", () => {
      const open = body.classList.toggle("msg-open");
      more.textContent = open ? "收起" : "展开全文";
      more.setAttribute("aria-expanded", String(open));
    });
    const jump = button(`完整解读见「${$("#reading-title")?.textContent || "解读"}」`, "msg-more");
    jump.addEventListener("click", () => {
      const responses = $("#reading .reading-responses");
      const isFollowup = Boolean(
        responses
        && currentReading?.responses?.some(
          (item) => item.output?.summary && message.text.includes(item.output.summary),
        ),
      );
      if (isFollowup) {
        responses.open = true;
        responses.scrollIntoView({ behavior: "smooth", block: "start" });
      } else {
        $("#reading").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
    const row = node("div", "msg-more-row");
    row.append(more, jump);
    body.append(row);
  }
  item.append(body);
  $("#messages").append(item);
}

/* The thinking bubble is a 推演轨: six fixed stages; each progress label from the server is
   filed under its stage and kept, so the person sees the path taken, including a fact check
   that sent the draft back. The current label stays in the one span the tests read. */
const TRACK_STAGES = [
  ["ask", "问意"],
  ["calc", "排盘"],
  ["expert", "专家", true],
  ["merge", "合参", true],
  ["check", "核验"],
  ["write", "成文"],
];
let trackClock = null;

function stageOf(label) {
  if (/理解/.test(label)) return "ask";
  if (/专家/.test(label)) return "expert";
  if (/比对|呼应|分歧/.test(label)) return "merge";
  if (/核对|审校|改写/.test(label)) return "check";
  if (/解读已完成/.test(label)) return "write";
  return "calc";
}

function showThinking() {
  $("#thinking")?.remove();
  clearInterval(trackClock);
  const box = $("#messages");
  if (!box) return;
  const item = node("article", "msg msg-assistant");
  item.id = "thinking";
  item.append(node("span", "msg-label", "答"));
  const body = node("div", "thinking");
  const now = node("div", "track-now");
  const clock = node("time", "track-clock", "0.0 s");
  clock.setAttribute("aria-hidden", "true");
  now.append(node("i"), node("span", "", page.thinking || "正在观照你的问题……"), clock);
  const track = node("ol", "track");
  TRACK_STAGES.forEach(([id, name, optional]) => {
    const step = node("li", "pending");
    step.dataset.stage = id;
    if (optional) step.dataset.optional = "";
    const text = node("div", "track-text");
    text.append(node("b", "", name), node("div", "track-lines"));
    step.append(node("i", "track-node"), text);
    track.append(step);
  });
  track.firstElementChild.className = "active";
  body.append(now, track);
  item.append(body);
  box.append(item);
  const start = performance.now();
  trackClock = setInterval(() => {
    if (!clock.isConnected) return clearInterval(trackClock);
    clock.textContent = `${((performance.now() - start) / 1000).toFixed(1)} s`;
  }, 100);
  scrollTranscript();
}

function advanceTrack(label) {
  const text = $("#thinking .thinking span");
  if (!text) return;
  text.textContent = label;
  const steps = $$("#thinking .track li");
  const index = steps.findIndex((step) => step.dataset.stage === stageOf(label));
  if (index < 0) return;
  const redo = /改写/.test(label);
  steps.forEach((step, i) => {
    if (i < index) {
      if (step.classList.contains("active")) step.classList.replace("active", "done");
      else if (step.classList.contains("pending") && !("optional" in step.dataset))
        step.className = "done";
    } else if (i > index && step.classList.contains("active")) {
      step.classList.replace("active", "done");
    }
  });
  const step = steps[index];
  const keep = step.classList.contains("redo");
  step.className = /解读已完成/.test(label) ? "done seen" : "active seen";
  if (redo || keep) step.classList.add("redo");
  const lines = step.querySelector(".track-lines");
  if (lines.lastElementChild?.dataset.label === label) return;
  const line = node("small", redo ? "track-bad" : "", label);
  line.dataset.label = label;
  if (redo) line.append(node("em", "track-stamp", "退"));
  lines.append(line);
  scrollTranscript();
}

function renderTranscript() {
  const box = $("#messages");
  if (!box) return;
  const messages = (state?.messages || []).filter(
    (message) => (message.system || "auto") === SYSTEM,
  );
  box.replaceChildren();
  if (messages.length) messages.forEach(showMessage);
  else if ($("#welcome")) box.append($("#welcome").content.cloneNode(true));
}

function draft(question) {
  if (busy || !state || !$("#message")) return;
  if (page.draft?.(question)) return;
  $("#message").value = question;
  fitComposer();
  $("#message").focus();
  $("#chat-form").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// The dialogue composer grows with its text up to the CSS max-height.
function fitComposer() {
  const box = $(".dialog #message");
  if (!box) return;
  box.style.height = "auto";
  box.style.height = `${box.scrollHeight}px`;
}

async function send({ message, extra = {} }, birth) {
  ++localStateEpoch;
  clearTimeout(refreshTimer);
  if (!state.messages.some((item) => (item.system || "auto") === SYSTEM))
    $("#messages").replaceChildren();
  showMessage({ role: "user", text: message });
  showThinking();
  setBusy(true);
  const unsent = $("#message").value;
  let handled = false;
  $("#message").value = "";
  fitComposer();
  const progressId = crypto.randomUUID();
  const progress = new EventSource(`/api/progress?request_id=${progressId}&system=${SYSTEM}`);
  progress.onmessage = (event) => {
    const label = JSON.parse(event.data).label;
    if (typeof label === "string") advanceTrack(label);
  };
  progress.addEventListener("done", () => progress.close());
  try {
    const next = await api("/api/chat", {
      method: "POST",
      headers: { "X-Zhiming-Progress": progressId },
      body: JSON.stringify({ message, system: SYSTEM, birth, ...extra,
        ...(followupReadingId ? { reading_id: followupReadingId } : {}) }),
    });
    if (["auto", "bazi", "astro", "daily"].includes(SYSTEM) && !followupReadingId
      && next.messages.at(-1)?.status !== "crisis_support")
      acceptBirthVersion(next.birth_version);
    const fresh = next.messages.at(-1)?.status === "submit_reading";
    applyState(next, false, false, fresh);
    // A page may take over what happens next (塔罗 turns the view to its face-down cards).
    handled = fresh && Boolean(page.onAnswered?.());
    if (fresh && !handled) {
      toast("解读已整理好。");
      // The reading spans the page below the dialogue window: bring it into view, and keep it
      // there when the composer takes focus again.
      handled = Boolean($("#reading"));
      $("#reading")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (error) {
    $("#thinking")?.remove();
    clearInterval(trackClock);
    showMessage({ role: "assistant", text: error.message, status: "error" });
    $("#message").value = unsent;
    fitComposer();
    setBusy(false);
    toast(error.message);
    page.onSendFailed?.();
    await handleBirthError(error);
  } finally {
    progress.close();
  }
  if (!busy && window.innerWidth > 760) $("#message").focus({ preventScroll: handled });
}

function initComposer() {
  const form = $("#chat-form");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || !state) return;
    const text = $("#message").value.trim();
    const composed = page.compose ? page.compose(text) : text ? { message: text } : null;
    if (!composed) return;
    if ($("#birth-form") && !validateBirth()) return;
    await send(composed, $("#birth-form") ? birthInfo() : state.birth);
  });
  $("#message").addEventListener("input", fitComposer);
  $("#message").addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.isComposing || event.keyCode === 229) return;
    const newline = form.dataset.enter === "newline";
    if (newline ? event.ctrlKey || event.metaKey : !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  $("#messages")?.addEventListener("click", (event) => {
    const suggestion = event.target.closest("[data-question]");
    if (suggestion) draft(suggestion.dataset.question);
  });
}

/* ---------- Reading ---------- */

function addList(parent, title, values) {
  if (!values?.length) return;
  parent.append(node("h4", "reading-subheading", title));
  const list = node("ol", "reading-list");
  values.forEach((value) => list.append(node("li", "", value)));
  parent.append(list);
}

function renderReading(reading, fresh = false) {
  currentReading = reading;
  page.onReading?.(reading, fresh);
  const content = $("#reading-content");
  if (!content) return;
  delete content.dataset.pendingFresh;
  $("#copy-reading").hidden = !reading;
  if (!reading) {
    content.classList.remove("is-fresh");
    content.replaceChildren(...Array.from(emptyReading.cloneNode(true).childNodes));
    return;
  }
  const output = reading.output;
  const tags = node("div", "reading-tags");
  (output.systems_used || []).forEach((value) =>
    tags.append(node("span", "", SYSTEM_NAMES[value] || value)),
  );
  content.replaceChildren(tags, node("p", "reading-summary", output.summary));
  const veiled = Boolean($("#tarot-lower")?.classList.contains("veiled"));
  const animate = fresh && !REDUCED_MOTION.matches;
  content.classList.toggle("is-fresh", animate && !veiled);
  if (animate && veiled) content.dataset.pendingFresh = "1";
  if (reading.birth_context?.birth) {
    const birth = reading.birth_context.birth;
    content.insertBefore(node("p", "reading-confidence",
      `${reading.stale ? "旧生辰解读" : reading.historical ? "历史解读" : "解读依据"}：公历 ${birth.date || "日期未填"} ${formatBirthTime(birth)} · ${birth.place || "地点未填"}`), tags);
  }
  (output.sections || []).forEach((section, index) => {
    content.append(
      node("h4", "reading-subheading", `${cnNumber(index + 1)}　${section.title}`),
      node("p", "reading-section", section.body),
    );
  });
  addList(content, "可行之事", output.advice);
  addList(
    content,
    "时间线索",
    output.timeline?.map((item) => `${item.period}：${item.note}`),
  );
  addList(content, "彼此呼应", output.resonances);
  addList(
    content,
    "不同视角",
    output.tensions?.map(
      (item) => `${item.theme}：${item.sides.join("；")}。${item.how_to_read}`,
    ),
  );
  if (output.closing) content.append(node("p", "reading-section", output.closing));
  if (output.evidence?.length) {
    const details = node("details", "reading-details");
    details.append(node("summary", "", `查看解读依据（${output.evidence.length} 条）`));
    const list = node("ol", "reading-list");
    output.evidence.forEach((item) => list.append(node("li", "", item.reading)));
    details.append(list);
    content.append(details);
  }
  const confidence = node("p", "reading-confidence");
  confidence.append(
    node(
      "strong",
      "",
      `解读置信度：${{ low: "低", medium: "中", high: "高" }[output.confidence.level] || output.confidence.level}。`,
    ),
    document.createTextNode(output.confidence.reason),
  );
  if (output.safety?.flag && output.safety.note)
    confidence.append(node("span", "", " " + output.safety.note));
  content.append(confidence);
  // Every fact the reading cites was checked by code before it was accepted: say so with a seal.
  if (output.evidence?.length) {
    const seal = node("span", "fact-seal");
    seal.append(node("b", "", "事实"), node("b", "", "已核"));
    seal.title = `引用的 ${output.evidence.length} 条事实均由代码逐项核对`;
    seal.setAttribute("aria-label", seal.title);
    content.prepend(seal);
  }
  if (animate)
    Array.from(content.children).forEach((child, index) =>
      child.style.setProperty("--i", String(Math.min(index, 14))));
  if (output.followups?.length) {
    const followups = node("div", "reading-followups");
    for (const question of output.followups) {
      const chip = button(question, "btn btn-tag");
      chip.disabled = busy;
      chip.addEventListener("click", () => draft(question));
      followups.append(chip);
    }
    content.append(followups);
  }
  if (reading.responses?.length) {
    const details = node("details", "reading-details reading-responses");
    details.append(node("summary", "", `历次追问（${reading.responses.length} 次）`));
    for (const response of reading.responses) {
      details.append(node("h4", "reading-subheading", response.question.split("\n")[0]),
        node("p", "reading-section", response.output.summary));
      for (const section of response.output.sections || [])
        details.append(node("h4", "reading-subheading", section.title), node("p", "reading-section", section.body));
      addList(details, "可行之事", response.output.advice);
      addList(details, "解读依据", response.output.evidence?.map((item) => item.reading));
    }
    content.append(details);
  }
  if ($("#chat-form")) {
    const resume = button(followupReadingId === reading.reading_id ? "正在追问这份解读" : "继续这份解读", "btn btn-tag");
    resume.setAttribute("data-lock", "");
    resume.disabled = busy;
    resume.addEventListener("click", () => {
      followupReadingId = reading.reading_id;
      $("#message").placeholder = "写下关于这份解读的追问……";
      draft("请进一步解释这份解读");
      toast("后续问题已绑定这份解读；开启新对话可结束追问。");
    });
    content.append(resume);
  } else {
    const resume = node("a", "btn btn-tag", "继续这份解读");
    const target = output.systems_used?.[0] || "tarot";
    resume.href = `/${target}?reading_id=${encodeURIComponent(reading.reading_id)}`;
    content.append(resume);
  }
}

async function copyReading() {
  if (!currentReading) return;
  const output = currentReading.output;
  const sections = output.sections || [];
  const text = [
    "知命 · 此间解读",
    output.summary,
    ...sections.map((item, index) => `${index + 1}. ${item.title}\n${item.body}`),
    ...(sections.length ? [] : output.evidence.map((item) => item.reading)),
    "可以考虑：",
    ...output.advice,
    ...(output.closing ? [output.closing] : []),
    ...(sections.length ? ["解读依据：", ...output.evidence.map((item) => item.reading)] : []),
    "仅供参考与自我反思。",
  ].join("\n\n");
  try {
    await navigator.clipboard.writeText(text);
    toast("解读已复制。");
  } catch {
    toast("浏览器未允许复制，你可以选中解读文字手动复制。");
  }
}

/* ---------- History ---------- */

// The drawer lists the session's first page until a search, a filter or 加载更多 asks for more.
const historyView = { system: "", q: "", items: [], total: 0, version: 0 };
let historySearchTimer;

function historyFiltered() {
  return Boolean(historyView.system || historyView.q);
}

function historyLabel(item) {
  const date = new Date(item.created_at);
  const day = Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleDateString("zh-CN", {
        month: "long",
        day: "numeric",
        timeZone: "Asia/Shanghai",
      });
  const systems = (item.systems_used || []).map((value) => SYSTEM_NAMES[value] || value);
  const followups = item.response_count ? `追问 ${item.response_count} 次` : "";
  return [day, systems.join(" + "), followups].filter(Boolean).join(" · ");
}

function historyButton(item, className = "history-item") {
  const entry = button("", className);
  entry.append(
    node("span", "history-meta", historyLabel(item)),
    node("span", "history-question", item.question.split("\n")[0]),
  );
  entry.addEventListener("click", () => openReading(item.reading_id));
  return entry;
}

function historyRow(item) {
  const row = node("div", "history-row");
  const remove = button("删除", "btn btn-text history-delete");
  remove.setAttribute("aria-label", `删除解读：${item.question.split("\n")[0]}`);
  remove.setAttribute("data-lock", "");
  remove.disabled = busy;
  remove.addEventListener("click", () => deleteReading(item));
  row.append(historyButton(item), remove);
  return row;
}

async function openReading(readingId) {
  try {
    renderReading(await api(`/api/readings/${encodeURIComponent(readingId)}`));
    closeDrawer();
    ($("#reading") || $("main")).scrollIntoView({ behavior: "smooth", block: "start" });
    toast("正在查看历史解读；当前对话保持不变。");
  } catch (error) {
    toast(error.message);
  }
}

function renderHistory(history) {
  page.onHistory?.(history);
  if (historyFiltered()) {
    // A search result may have changed too; refresh it while the drawer is open.
    if (!$("#history-drawer").hidden) loadHistory(true);
    return;
  }
  // Keep what 加载更多 already fetched beyond the first page, while there is more to show.
  const total = state?.history_total ?? history.length;
  const extra = historyView.items
    .slice(history.length)
    .filter((item) => !history.some((latest) => latest.reading_id === item.reading_id))
    .slice(0, Math.max(0, total - history.length));
  historyView.items = [...history, ...extra];
  historyView.total = total;
  drawHistory();
}

function drawHistory() {
  const list = $("#history-list");
  const { items, total } = historyView;
  list.replaceChildren();
  if (!items.length)
    list.append(
      node(
        "p",
        "history-empty",
        historyFiltered()
          ? "没有找到符合条件的解读，换个关键词或功能试试。"
          : "每一次发问，都是认识自己的开始。解读完成后会记在这里。",
      ),
    );
  items.forEach((item) => list.append(historyRow(item)));
  $("#history-count").textContent = total
    ? historyFiltered()
      ? `找到 ${total} 份解读`
      : `共 ${total} 份解读`
    : "";
  $("#history-more").hidden = items.length >= total;
  $("#history-clear").hidden = !state?.history_total;
}

async function loadHistory(reset) {
  const version = ++historyView.version;
  const params = new URLSearchParams({
    offset: String(reset ? 0 : historyView.items.length),
    limit: "20",
  });
  if (historyView.system) params.set("system", historyView.system);
  if (historyView.q) params.set("q", historyView.q);
  $("#history-more").disabled = true;
  try {
    const result = await api(`/api/history?${params}`);
    if (version !== historyView.version) return;
    const known = new Set(reset ? [] : historyView.items.map((item) => item.reading_id));
    historyView.items = [
      ...(reset ? [] : historyView.items),
      ...result.items.filter((item) => !known.has(item.reading_id)),
    ];
    historyView.total = result.total;
    drawHistory();
  } catch (error) {
    if (version === historyView.version) toast(error.message);
  } finally {
    $("#history-more").disabled = false;
  }
}

function filterHistory() {
  historyView.q = $("#history-search").value.trim();
  historyView.system = $("#history-filter").value;
  if (historyFiltered()) loadHistory(true);
  else {
    ++historyView.version;
    historyView.items = [];
    renderHistory(state?.history || []);
  }
}

async function deleteReading(item) {
  if (busy || !state) return;
  const confirmed = await askConfirm({
    title: "删除这份解读？",
    text: `「${item.question.split("\n")[0]}」连同它的追问将被删除，无法撤回。各功能当前对话将重新开始，其他已保存的解读保留。`,
    confirm: "删除",
    keep: "保留",
  });
  if (!confirmed || busy) return;
  try {
    await api(`/api/readings/${encodeURIComponent(item.reading_id)}`, { method: "DELETE" });
    if (followupReadingId === item.reading_id) followupReadingId = null;
    if (currentReading?.reading_id === item.reading_id) renderReading(null);
    historyView.items = historyView.items.filter((entry) => entry.reading_id !== item.reading_id);
    historyView.total = Math.max(0, historyView.total - 1);
    drawHistory();
    toast("这份解读已删除。");
    await refresh();
  } catch (error) {
    toast(error.message);
  }
}

async function clearReadings() {
  if (busy || !state) return;
  const confirmed = await askConfirm({
    title: "清空全部解读记录？",
    text: "将删除全部解读与追问，各功能当前对话将重新开始；生辰档案" + (state.account ? "与账号" : "") + "保留。此操作无法撤回，可先导出记录。",
    confirm: "全部删除",
    keep: "保留",
  });
  if (!confirmed || busy) return;
  try {
    const result = await api("/api/readings", { method: "DELETE" });
    followupReadingId = null;
    renderReading(null);
    historyView.items = [];
    historyView.total = 0;
    drawHistory();
    toast(`已删除 ${result.deleted.length} 份解读。`);
    await refresh();
  } catch (error) {
    toast(error.message);
  }
}

/* ---------- Session ---------- */

function applyState(next, first = false, background = false, fresh = false) {
  if (next.system && next.system !== SYSTEM) return;
  // A restarted service numbers its revisions afresh: take its state as a first load.
  const restarted = Boolean(state?.instance && next.instance && state.instance !== next.instance);
  if (restarted) first = true;
  if (!first && state && (next.birth_version ?? 0) < (state.birth_version ?? 0)) return;
  if (!first && state && (next.session_revision ?? 0) < (state.session_revision ?? 0)) return;
  ++localStateEpoch;
  const oldVersion = state?.birth_version;
  const preview = background && currentReading?.historical
    && next.history.some((item) => item.reading_id === currentReading.reading_id)
    && next.reading?.reading_id !== currentReading.reading_id ? currentReading : null;
  const selectedFollowup = followupReadingId;
  state = next;
  if (next.account) remember("zhiming.account", next.account.email);
  renderAccount();
  if (restarted) announceRestart();
  followupReadingId = next.followup_reading_id
    || (preview?.reading_id === selectedFollowup ? selectedFollowup : null);
  if ($("#provider")) $("#provider").value = next.provider;
  const status = $("#connection");
  if (status) {
    status.classList.remove("offline");
    status.classList.add("ready");
    status.textContent = next.provider === "demo" ? "离线演示" : "真实模型";
  }
  $$("[data-live]").forEach((live) => {
    live.textContent = next.provider === "demo" ? "离线演示" : "知命在线";
    live.classList.toggle("demo", next.provider === "demo");
  });
  renderTranscript();
  renderReading(
    preview
      ? {
          ...preview,
          stale: Boolean(preview.birth_context) && preview.birth_context.version !== next.birth_version,
        }
      : next.reading && (next.reading.view || "auto") === SYSTEM
        ? next.reading
        : null,
    fresh && !preview,
  );
  renderHistory(next.history);
  const birthChanged = oldVersion !== next.birth_version;
  if ((first || (birthChanged && !birthDirty)) && $("#birth-form")) {
    acceptBirthVersion(next.birth_version);
    fillBirthForm(next.birth);
  } else if (birthChanged && birthDirty) showBirthConflict();
  if (first) foldBirth(next.birth, !next.birth?.date && PAGE !== "daily");
  else if (birthChanged && !birthDirty)
    foldBirth(next.birth, Boolean($("[data-birth-fold]")?.open));
  page.onState?.(next, first, background);
  setBusy(next.busy);
  if (next.busy) {
    showThinking();
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refresh, 2000);
  }
  scrollTranscript();
  if (oldVersion !== undefined && birthChanged)
    birthChannel?.postMessage({ birth_version: next.birth_version });
}

function announceRestart() {
  if (state.account) toast("服务已重新启动，已从账号恢复生辰与解读记录。");
  else
    showNotice(
      "服务已重新启动，本页已换为新的访客会话，之前的访客记录无法恢复。登录账号可长期保存记录。",
      [["登录 / 注册", () => location.assign(loginUrl())]],
    );
}

async function refresh() {
  const epoch = localStateEpoch;
  try {
    const next = await api("/api/session");
    if (epoch === localStateEpoch) {
      applyState(next, false, true);
      return true;
    }
  } catch (error) {
    if (epoch !== localStateEpoch) return;
    setBusy(false);
    toast(error.message);
  }
}

async function startNew(provider) {
  if (busy && state) return;
  ++localStateEpoch;
  clearTimeout(refreshTimer);
  page.onNewSession?.();
  setBusy(true);
  try {
    applyState(
      await (state
        ? api("/api/new", { method: "POST", body: JSON.stringify({ provider, system: SYSTEM }) })
        : api(`/api/session?provider=${encodeURIComponent(provider)}`)),
    );
    followupReadingId = null;
    if ($("#message")) $("#message").value = "";
    toast(
      provider === "demo"
        ? "已切换离线演示：支持历法排盘、塔罗、五格与流日计算。"
        : "新的对话已开启，旧解读可在「足迹」中回看。",
    );
  } catch (error) {
    if ($("#provider")) $("#provider").value = state?.provider || "configured";
    setBusy(false);
    if ($("#provider")) $("#provider").disabled = false;
    toast(error.message);
  }
}

function wireControls() {
  $("#open-history")?.addEventListener("click", openDrawer);
  $("#new-chat")?.addEventListener("click", () => startNew(state.provider));
  $("#provider")?.addEventListener("change", (event) => startNew(event.target.value));
  $("#forget")?.addEventListener("click", forgetRecords);
  $("#copy-reading")?.addEventListener("click", copyReading);
  $("#history-search").addEventListener("input", () => {
    clearTimeout(historySearchTimer);
    historySearchTimer = setTimeout(filterHistory, 300);
  });
  $("#history-filter").addEventListener("change", filterHistory);
  $("#history-more").addEventListener("click", () => loadHistory(false));
  $("#history-clear").addEventListener("click", clearReadings);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawer();
  });
}

async function forgetRecords() {
  if (busy || !state) return;
  const confirmed = await askConfirm({
    title: "清除这段问道足迹？",
    text: state.account
      ? "将删除此账号的生辰档案、全部解读记录、对话与运行日志；账号本身保留。此操作无法撤回。"
      : "将删除当前浏览器会话的生辰资料、解读记录与对话。此操作无法撤回。",
    confirm: "确认清除",
    keep: "保留记录",
  });
  if (!confirmed || busy) return;
  page.onNewSession?.({ forget: true });
  setBusy(true);
  ++localStateEpoch;
  try {
    applyState(await api("/api/session", { method: "DELETE" }), true);
    acceptBirthVersion(state.birth_version);
    followupReadingId = null;
    setBirthFeedback("", false);
    if ($("#message")) $("#message").value = "";
    toast(state.account ? "账号中的生辰、解读和对话已清除。" : "当前会话的生辰、解读和对话已清除。");
  } catch (error) {
    setBusy(false);
    toast(error.message);
  }
}

/* ---------- Birth form ---------- */

const BIRTH_MODES = {
  bazi: { submit: "排出我的八字", gender: true, settings: true },
  astro: { submit: "绘制本命星图", gender: false, settings: false },
  daily: { submit: "确认生辰，查看流日", gender: false, settings: true },
  save: { submit: "保存生辰档案", gender: true, settings: false },
};

function labelled(text, control, className = "field") {
  const label = node("label", className);
  label.append(node("span", "", text), control);
  return label;
}

function selectBox(id, options) {
  const select = node("select");
  select.id = id;
  options.forEach(([value, text]) => select.append(new Option(text, value)));
  return select;
}

function inputBox(id, type) {
  const input = node("input");
  input.id = id;
  input.type = type;
  return input;
}

const SHICHEN_SPECS = [
  ["zi", "子时（23:00–01:00）", "00:00"],
  ["chou", "丑时（01:00–03:00）", "02:00"],
  ["yin", "寅时（03:00–05:00）", "04:00"],
  ["mao", "卯时（05:00–07:00）", "06:00"],
  ["chen", "辰时（07:00–09:00）", "08:00"],
  ["si", "巳时（09:00–11:00）", "10:00"],
  ["wu", "午时（11:00–13:00）", "12:00"],
  ["wei", "未时（13:00–15:00）", "14:00"],
  ["shen", "申时（15:00–17:00）", "16:00"],
  ["you", "酉时（17:00–19:00）", "18:00"],
  ["xu", "戌时（19:00–21:00）", "20:00"],
  ["hai", "亥时（21:00–23:00）", "22:00"],
];
const LUNAR_DAY_LABELS = [
  "",
  "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
  "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
  "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
];
let calendarMode = "solar";
let lunarConverting = false;
let lunarReqVersion = 0;
const lunarYearCache = new Map();

function shichenOfClock(hhmm) {
  if (!hhmm || !/^\d{2}:\d{2}$/.test(hhmm)) return "";
  const hour = Number(hhmm.slice(0, 2));
  const index = Math.floor(((hour + 1) % 24) / 2);
  return SHICHEN_SPECS[index]?.[0] || "";
}

function shichenMidpoint(key) {
  return SHICHEN_SPECS.find(([id]) => id === key)?.[2] || "";
}

function updateBirthProgress() {
  const dots = $("#birth-dots");
  const text = $("#birth-dots-text");
  if (!dots || !text) return;
  const hasDate = Boolean($("#birth-date")?.value);
  const hasTime = Boolean($("#unknown-time")?.checked || $("#birth-time")?.value);
  const hasPlace = Boolean(selectedLocation);
  const done = [hasDate, hasTime, hasPlace].filter(Boolean).length;
  dots.querySelectorAll("i").forEach((bar, idx) => bar.classList.toggle("on", idx < done));
  text.textContent = `${done} / 3 已填`;
  scheduleDraftPreview();
}

function syncGenderSeg(value) {
  const seg = $("#gender-seg");
  if (!seg) return;
  seg.querySelectorAll("button").forEach((btn) => {
    btn.setAttribute("aria-pressed", String((btn.dataset.val || "") === (value || "")));
  });
}

function setCalendarButtons(mode) {
  calendarMode = mode;
  const seg = $("#calendar-seg");
  if (!seg) return;
  seg.querySelectorAll("button").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(btn.dataset.cal === mode));
  });
}

function populateSolarMonths(year, selectedMonth) {
  const mSel = $("#birth-month");
  if (!mSel) return;
  const today = shanghaiToday().split("-").map(Number);
  const maxMonth = year === today[0] ? today[1] : 12;
  mSel.replaceChildren(new Option("月", ""));
  for (let m = 1; m <= maxMonth; m++) mSel.append(new Option(`${m} 月`, String(m)));
  if (selectedMonth && Number(selectedMonth) <= maxMonth) mSel.value = String(selectedMonth);
}

function populateSolarDays(year, month, selectedDay) {
  const dSel = $("#birth-day");
  if (!dSel) return;
  const today = shanghaiToday().split("-").map(Number);
  let maxDay = year && month ? new Date(year, month, 0).getDate() : 31;
  if (year === today[0] && month === today[1]) maxDay = Math.min(maxDay, today[2]);
  dSel.replaceChildren(new Option("日", ""));
  for (let d = 1; d <= maxDay; d++) dSel.append(new Option(`${d} 日`, String(d)));
  if (selectedDay && Number(selectedDay) <= maxDay) dSel.value = String(selectedDay);
}

async function getLunarMonths(year) {
  if (lunarYearCache.has(year)) return lunarYearCache.get(year);
  const data = await api(`/api/calendar/lunar-year?year=${encodeURIComponent(year)}`);
  lunarYearCache.set(year, data.months);
  return data.months;
}

function populateLunarDays(maxDays, selectedDay) {
  const dSel = $("#birth-day");
  if (!dSel) return;
  dSel.replaceChildren(new Option("日", ""));
  for (let d = 1; d <= maxDays; d++) {
    dSel.append(new Option(LUNAR_DAY_LABELS[d] || `${d} 日`, String(d)));
  }
  if (selectedDay && Number(selectedDay) <= maxDays) dSel.value = String(selectedDay);
}

function setLunarHint(text) {
  const hint = $("#lunar-conversion");
  if (!hint) return;
  hint.textContent = text || "";
  hint.hidden = !text;
}

async function syncAskDateFromDropdowns({ markDirty = true } = {}) {
  const ySel = $("#birth-year");
  const mSel = $("#birth-month");
  const dSel = $("#birth-day");
  const dateInput = $("#birth-date");
  if (!ySel || !mSel || !dSel || !dateInput) return;
  const y = Number(ySel.value);
  const m = Number(mSel.value);
  const d = Number(dSel.value);
  if (calendarMode === "solar") {
    setLunarHint("");
    if (y && m && d) {
      dateInput.value = `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    } else {
      dateInput.value = "";
    }
    if (markDirty) {
      birthDirty = true;
      ++restoringBirth;
      setBirthFeedback("资料已修改，确认后生效。", false);
    }
    updateBirthProgress();
    return;
  }
  if (!y || !m || !d) {
    dateInput.value = "";
    setLunarHint("");
    updateBirthProgress();
    return;
  }
  const version = ++lunarReqVersion;
  lunarConverting = true;
  setLunarHint("正在换算公历日期…");
  try {
    const res = await api(
      `/api/calendar/lunar-to-solar?year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}&day=${encodeURIComponent(d)}`,
    );
    if (version !== lunarReqVersion) return;
    dateInput.value = res.solar;
    setLunarHint(`已换算为公历 ${res.solar}（${res.lunar_label}）`);
    if (markDirty) {
      birthDirty = true;
      ++restoringBirth;
      setBirthFeedback("资料已修改，确认后生效。", false);
    }
  } catch (error) {
    if (version !== lunarReqVersion) return;
    dateInput.value = "";
    setLunarHint(error.message || "该农历日期超出有效范围。");
  } finally {
    if (version === lunarReqVersion) {
      lunarConverting = false;
      updateBirthProgress();
    }
  }
}

function syncAskDropdownsFromSolar(iso) {
  const ySel = $("#birth-year");
  const mSel = $("#birth-month");
  const dSel = $("#birth-day");
  if (!ySel || !mSel || !dSel) return;
  setCalendarButtons("solar");
  setLunarHint("");
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    ySel.value = "";
    populateSolarMonths(0, "");
    populateSolarDays(0, 0, "");
    return;
  }
  const [y, m, d] = iso.split("-").map(Number);
  ySel.value = String(y);
  populateSolarMonths(y, m);
  populateSolarDays(y, m, d);
}

async function switchCalendarMode(nextMode) {
  if (calendarMode === nextMode) return;
  const ySel = $("#birth-year");
  const mSel = $("#birth-month");
  const dSel = $("#birth-day");
  const dateInput = $("#birth-date");
  if (!ySel || !mSel || !dSel || !dateInput) return;
  const currentSolar = dateInput.value;
  setCalendarButtons(nextMode);
  if (nextMode === "solar") {
    syncAskDropdownsFromSolar(currentSolar);
    updateBirthProgress();
    return;
  }
  // Switching to lunar: if a valid solar date is present, convert it to lunar first.
  const version = ++lunarReqVersion;
  if (currentSolar && /^\d{4}-\d{2}-\d{2}$/.test(currentSolar)) {
    lunarConverting = true;
    setLunarHint("正在换算为农历…");
    try {
      const res = await api(`/api/calendar/solar-to-lunar?date=${encodeURIComponent(currentSolar)}`);
      if (version !== lunarReqVersion || calendarMode !== "lunar") return;
      const months = await getLunarMonths(res.year);
      if (version !== lunarReqVersion || calendarMode !== "lunar") return;
      ySel.value = String(res.year);
      mSel.replaceChildren(new Option("农历月", ""));
      months.forEach((item) => mSel.append(new Option(item.label, String(item.month))));
      mSel.value = String(res.month);
      const spec = months.find((item) => item.month === res.month);
      populateLunarDays(spec ? spec.days : 30, res.day);
      setLunarHint(`对应公历 ${currentSolar}（${res.lunar_label}）`);
    } catch {
      if (version !== lunarReqVersion) return;
      setLunarHint("请选择农历出生年月日，系统将自动换算公历。");
    } finally {
      if (version === lunarReqVersion) lunarConverting = false;
    }
    return;
  }
  const y = Number(ySel.value);
  mSel.replaceChildren(new Option("农历月", ""));
  populateLunarDays(30, "");
  setLunarHint("请选择农历出生年月日，系统将自动换算公历。");
  if (y) {
    try {
      const months = await getLunarMonths(y);
      if (version !== lunarReqVersion || calendarMode !== "lunar") return;
      months.forEach((item) => mSel.append(new Option(item.label, String(item.month))));
    } catch {
      // Ignore transient errors while browsing empty years.
    }
  }
}

function syncTimeControl() {
  const unknown = Boolean($("#unknown-time")?.checked);
  const locked = busy || !state;
  const time = $("#birth-time");
  const shichen = $("#birth-shichen");
  const knownWrap = $("#birth-time-known");
  const unknownWrap = $("#birth-time-unknown");
  const period = $("#birth-time-period");
  const label = $("#birth-time-label");
  if (label) label.htmlFor = unknown ? "birth-time-period" : "birth-time";
  if (knownWrap) knownWrap.hidden = unknown;
  if (unknownWrap) unknownWrap.hidden = !unknown;
  if (shichen) {
    shichen.disabled = locked || unknown;
    if (unknown) shichen.value = "";
  }
  if (time) {
    if (!knownWrap) time.hidden = unknown;
    time.disabled = locked || unknown;
    if (unknown) time.value = "";
  }
  if (period) {
    if (!unknownWrap) period.hidden = !unknown;
    period.disabled = locked || !unknown;
    if (unknown && !period.value) period.value = "unknown";
  }
  updateBirthProgress();
}

function buildAskBirthForm(host, options) {
  const form = node("form", "birth-form");
  form.id = "birth-form";

  const hiddenDate = inputBox("birth-date", "hidden");
  form.append(hiddenDate);

  // 01 出生日期（公历 / 农历 + 动态联动年月日）
  const g1 = node("fieldset", "b-group");
  const g1Head = node("div", "b-group-head");
  const g1Leg = node("legend");
  g1Leg.append(node("span", "num", "01"), document.createTextNode("出生日期"));
  const calSeg = node("div", "seg");
  calSeg.id = "calendar-seg";
  calSeg.setAttribute("role", "group");
  calSeg.setAttribute("aria-label", "历法");
  const btnSolar = button("公历");
  btnSolar.dataset.cal = "solar";
  btnSolar.setAttribute("aria-pressed", "true");
  const btnLunar = button("农历");
  btnLunar.dataset.cal = "lunar";
  btnLunar.setAttribute("aria-pressed", "false");
  calSeg.append(btnSolar, btnLunar);
  g1Head.append(g1Leg, calSeg);

  const todayYear = Number(shanghaiToday().slice(0, 4));
  const yearOpts = [["", "选择年份"]];
  for (let y = todayYear; y >= 1850; y--) yearOpts.push([String(y), `${y} 年`]);
  const ySel = selectBox("birth-year", yearOpts);
  const mSel = selectBox("birth-month", [["", "月"]]);
  const dSel = selectBox("birth-day", [["", "日"]]);
  const dateRow = node("div", "b-row c3");
  dateRow.append(labelled("年", ySel), labelled("月", mSel), labelled("日", dSel));
  const lunarConv = node("p", "hint lunar-conv", "");
  lunarConv.id = "lunar-conversion";
  lunarConv.setAttribute("role", "status");
  lunarConv.hidden = true;
  g1.append(g1Head, dateRow, lunarConv);

  // 02 出生时间（时辰快选 + 精确时间，或不确定时段）
  const g2 = node("fieldset", "b-group");
  const g2Head = node("div", "b-group-head");
  const g2Leg = node("legend");
  g2Leg.append(node("span", "num", "02"), document.createTextNode("出生时间"));
  const unknown = node("label", "check");
  const unknownBox = inputBox("unknown-time", "checkbox");
  unknown.append(unknownBox, document.createTextNode("不知道具体时间"));
  g2Head.append(g2Leg, unknown);

  const shichen = selectBox("birth-shichen", [
    ["", "选择时辰"],
    ...SHICHEN_SPECS.map(([id, label]) => [id, label]),
  ]);
  const time = inputBox("birth-time", "time");
  const knownWrap = node("div", "b-row c2");
  knownWrap.id = "birth-time-known";
  knownWrap.append(labelled("时辰", shichen), labelled("精确时间（可选，星盘更准）", time));

  const period = selectBox("birth-time-period", TIME_PERIODS);
  period.value = "unknown";
  period.disabled = true;
  const unknownWrap = node("div", "birth-time-unknown");
  unknownWrap.id = "birth-time-unknown";
  unknownWrap.hidden = true;
  unknownWrap.append(labelled("大致出生时段", period));

  const timeHint = node("p", "hint");
  timeHint.append(
    document.createTextNode("选时辰会自动填入该时辰正点，也可微调右侧精确分钟；若只记得大概时段，请勾选"),
    node("b", "", "「不知道具体时间」"),
    document.createTextNode("。"),
  );
  g2.append(g2Head, knownWrap, unknownWrap, timeHint);

  // 03 出生地点（4 级联动 + 新疆时间制）
  const g3 = node("fieldset", "b-group");
  const g3Head = node("div", "b-group-head");
  const g3Leg = node("legend");
  g3Leg.append(node("span", "num", "03"), document.createTextNode("出生地点"));
  g3Head.append(g3Leg, node("span", "hint", "用于真太阳时校正与星盘宫位"));
  const placeRow = node("div", "b-row c4");
  placeRow.append(
    labelled("国家 / 地区", selectBox("birth-country", [["", "正在加载…"]])),
    labelled("省 / 州", selectBox("birth-province", [["", "请先选择国家"]])),
    labelled("城市", selectBox("birth-city", [["", "请先选择省份"]])),
    labelled("县 / 区", selectBox("birth-district", [["", "请先选择城市"]])),
  );
  const locationFeedback = node(
    "p",
    "location-feedback",
    "逐级选择，自动匹配出生地经纬度与时区。",
  );
  locationFeedback.id = "location-feedback";
  locationFeedback.setAttribute("role", "status");
  const clock = labelled(
    "出生钟表时间制",
    selectBox("birth-clock", [
      ["", "请选择时间制"],
      ["Asia/Shanghai", "北京时间（UTC+8）"],
      ["Asia/Urumqi", "新疆时间（UTC+6）"],
    ]),
  );
  clock.id = "clock-settings";
  clock.hidden = true;
  g3.append(g3Head, placeRow, locationFeedback, clock);

  // 04 性别（默认不预选男/女，避免误提交）
  const g4 = node("fieldset", "b-group");
  const g4Head = node("div", "b-group-head");
  const g4Leg = node("span", "b-legend");
  g4Leg.append(
    document.createTextNode("性别"),
    node("span", "b-legend-sub", "（可选，用于八字大运顺逆）"),
  );
  const genderSelect = selectBox("birth-gender", [
    ["", "暂不填写"],
    ["male", "男"],
    ["female", "女"],
  ]);
  genderSelect.hidden = true;
  const genderSeg = node("div", "seg lg");
  genderSeg.id = "gender-seg";
  genderSeg.setAttribute("role", "group");
  genderSeg.setAttribute("aria-label", "性别");
  [
    ["", "暂不填写"],
    ["male", "男"],
    ["female", "女"],
  ].forEach(([val, label]) => {
    const b = button(label);
    b.dataset.val = val;
    b.setAttribute("aria-pressed", String(val === ""));
    b.addEventListener("click", () => {
      if (busy || !state) return;
      genderSelect.value = val;
      syncGenderSeg(val);
      birthDirty = true;
      ++restoringBirth;
      setBirthFeedback("资料已修改，确认后生效。", false);
    });
    genderSeg.append(b);
  });
  g4Head.append(g4Leg, genderSeg, genderSelect);
  g4.append(g4Head);

  // 提交与冲突恢复
  const submit = button(options.submit, "btn btn-primary", "submit");
  const sync = button("载入最新生辰", "btn btn-tag");
  sync.id = "birth-sync";
  sync.hidden = true;
  sync.addEventListener("click", async () => {
    if (!(await refresh())) return;
    acceptBirthVersion(state.birth_version);
    fillBirthForm(state.birth);
    foldBirth(state.birth, true);
  });
  const keep = button("保留本页修改并重新确认", "btn btn-tag");
  keep.id = "birth-keep";
  keep.hidden = true;
  keep.addEventListener("click", () => {
    formBirthVersion = state.birth_version ?? 0;
    sync.hidden = keep.hidden = true;
    setBirthFeedback("已保留本页修改，请核对后再次提交。", false);
  });
  const feedback = node("p", "birth-feedback", birthDefaultText());
  feedback.id = "birth-feedback";
  feedback.setAttribute("role", "status");
  const submitRow = node("div", "submit-row");
  submitRow.append(submit, feedback, sync, keep);

  form.append(g1, g2, g3, g4, submitRow);
  host.replaceChildren(form);
  populateSolarMonths(0, "");
  populateSolarDays(0, 0, "");

  // 历法与年月日动态联动
  calSeg.addEventListener("click", (event) => {
    const b = event.target.closest("button[data-cal]");
    if (!b || busy || !state) return;
    switchCalendarMode(b.dataset.cal);
  });
  ySel.addEventListener("change", async () => {
    const y = Number(ySel.value);
    if (calendarMode === "solar") {
      populateSolarMonths(y, mSel.value);
      populateSolarDays(y, Number(mSel.value), dSel.value);
      await syncAskDateFromDropdowns();
    } else {
      const prevM = mSel.value;
      const prevD = dSel.value;
      mSel.replaceChildren(new Option("农历月", ""));
      if (y) {
        try {
          const months = await getLunarMonths(y);
          if (calendarMode !== "lunar" || Number(ySel.value) !== y) return;
          months.forEach((item) => mSel.append(new Option(item.label, String(item.month))));
          if (months.some((item) => String(item.month) === prevM)) mSel.value = prevM;
          const spec = months.find((item) => String(item.month) === mSel.value);
          populateLunarDays(spec ? spec.days : 30, prevD);
        } catch (error) {
          setLunarHint(error.message || "无法获取该年农历月份。");
        }
      } else {
        populateLunarDays(30, "");
      }
      await syncAskDateFromDropdowns();
    }
  });
  mSel.addEventListener("change", async () => {
    const y = Number(ySel.value);
    const m = Number(mSel.value);
    if (calendarMode === "solar") {
      populateSolarDays(y, m, dSel.value);
    } else if (y && m) {
      const months = lunarYearCache.get(y) || (await getLunarMonths(y).catch(() => []));
      const spec = months.find((item) => item.month === m);
      populateLunarDays(spec ? spec.days : 30, dSel.value);
    }
    await syncAskDateFromDropdowns();
  });
  dSel.addEventListener("change", () => syncAskDateFromDropdowns());

  // 时辰与精确时间双向同步
  shichen.addEventListener("change", () => {
    const mid = shichenMidpoint(shichen.value);
    if (mid) time.value = mid;
    else time.value = "";
    birthDirty = true;
    ++restoringBirth;
    setBirthFeedback("资料已修改，确认后生效。", false);
    updateBirthProgress();
  });
  time.addEventListener("input", () => {
    shichen.value = shichenOfClock(time.value);
    updateBirthProgress();
  });
  unknownBox.addEventListener("change", () => syncTimeControl());
  form.addEventListener("input", () => {
    birthDirty = true;
    ++restoringBirth;
    time.setCustomValidity("");
    setBirthFeedback("资料已修改，确认后生效。", false);
    updateBirthProgress();
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitBirth("save");
  });
  LOCATION_FIELDS.forEach((field, index) =>
    $(`#birth-${field}`).addEventListener("change", () => locationChanged(index)),
  );
  updateBirthProgress();
}

function buildBirthForm(host, mode) {
  const options = BIRTH_MODES[mode] || BIRTH_MODES.save;
  birthMode = mode;
  if (mode === "save") {
    buildAskBirthForm(host, options);
    return;
  }
  const form = node("form", "birth-form");
  form.id = "birth-form";

  const date = inputBox("birth-date", "date");
  date.min = "1850-01-01";
  date.max = shanghaiToday();
  const time = inputBox("birth-time", "time");
  const period = selectBox("birth-time-period", TIME_PERIODS);
  period.value = "unknown";
  period.hidden = true;
  period.disabled = true;
  const timeField = node("div", "field");
  const timeHead = node("div", "birth-time-head");
  const timeLabel = node("label", "field-label", "出生时间");
  timeLabel.id = "birth-time-label";
  timeLabel.htmlFor = "birth-time";
  const unknown = node("label", "check");
  const unknownBox = inputBox("unknown-time", "checkbox");
  unknown.append(unknownBox, document.createTextNode("不知道确切时间"));
  timeHead.append(timeLabel, unknown);
  timeField.append(timeHead, time, period);
  const firstRow = node("div", "birth-row");
  firstRow.append(labelled("出生日期 · 公历", date), timeField);

  const places = node("fieldset", "birth-places");
  places.append(node("legend", "field-label", "出生地点"));
  const placeRow = node("div", "birth-row");
  placeRow.append(
    labelled("国家 / 地区", selectBox("birth-country", [["", "正在加载…"]])),
    labelled("省 / 州", selectBox("birth-province", [["", "请先选择国家"]])),
    labelled("城市", selectBox("birth-city", [["", "请先选择省份"]])),
    labelled("县 / 区", selectBox("birth-district", [["", "请先选择城市"]])),
  );
  const locationFeedback = node(
    "p",
    "location-feedback",
    "逐级选择，自动匹配出生地经纬度与时区。",
  );
  locationFeedback.id = "location-feedback";
  locationFeedback.setAttribute("role", "status");
  places.append(placeRow, locationFeedback);

  const clock = labelled(
    "出生钟表时间制",
    selectBox("birth-clock", [
      ["", "请选择时间制"],
      ["Asia/Shanghai", "北京时间（UTC+8）"],
      ["Asia/Urumqi", "新疆时间（UTC+6）"],
    ]),
  );
  clock.id = "clock-settings";
  clock.hidden = true;
  form.append(firstRow, places, clock);

  if (options.gender)
    form.append(
      labelled(
        "性别 · 用于八字大运",
        selectBox("birth-gender", [
          ["", "暂不填写"],
          ["female", "女"],
          ["male", "男"],
        ]),
      ),
    );
  if (options.settings) {
    const settings = node("details", "birth-settings");
    settings.append(node("summary", "", "八字排盘口径"));
    const row = node("div", "birth-row");
    row.append(
      labelled(
        "日时柱时间口径",
        selectBox("solar-time", [
          ["false", "不用真太阳时（固定 UTC+8）"],
          ["true", "出生地真太阳时"],
        ]),
      ),
      labelled(
        "子时换日",
        selectBox("zishi-rule", [
          ["next_day", "子初换日 · 23:00"],
          ["same_day", "子正换日 · 00:00"],
        ]),
      ),
    );
    settings.append(row, node("p", "birth-feedback", "按所选口径计算；农历生日请先换算为公历。"));
    form.append(settings);
  }
  const submit = button(options.submit, "btn btn-primary", "submit");
  const sync = button("载入最新生辰", "btn btn-tag");
  sync.id = "birth-sync";
  sync.hidden = true;
  sync.addEventListener("click", async () => {
    if (!await refresh()) return;
    acceptBirthVersion(state.birth_version);
    fillBirthForm(state.birth);
    foldBirth(state.birth, true);
  });
  const keep = button("保留本页修改并重新确认", "btn btn-tag");
  keep.id = "birth-keep";
  keep.hidden = true;
  keep.addEventListener("click", () => {
    formBirthVersion = state.birth_version ?? 0;
    sync.hidden = keep.hidden = true;
    setBirthFeedback("已保留本页修改，请核对后再次提交。", false);
  });
  const feedback = node("p", "birth-feedback", birthDefaultText());
  feedback.id = "birth-feedback";
  feedback.setAttribute("role", "status");
  form.append(submit, feedback, sync, keep);
  host.replaceChildren(form);

  unknownBox.addEventListener("change", () => {
    syncTimeControl();
  });
  form.addEventListener("input", () => {
    birthDirty = true;
    ++restoringBirth;
    time.setCustomValidity("");
    setBirthFeedback("资料已修改，确认后生效。", false);
    if (mode === "bazi" || mode === "astro") invalidateChart();
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitBirth(mode);
  });
  LOCATION_FIELDS.forEach((field, index) =>
    $(`#birth-${field}`).addEventListener("change", () => locationChanged(index)),
  );
}

function setBirthFeedback(text, saved) {
  const feedback = $("#birth-feedback");
  if (!feedback) return;
  feedback.textContent = text || birthDefaultText();
  feedback.classList.toggle("saved", saved);
}

function acceptBirthVersion(version) {
  birthDirty = false;
  formBirthVersion = version ?? 0;
  if ($("#birth-sync")) $("#birth-sync").hidden = true;
  if ($("#birth-keep")) $("#birth-keep").hidden = true;
}

function showBirthConflict() {
  setBirthFeedback("其他页面已更新生辰。本页修改已保留，请载入最新资料或确认保留本页修改。", false);
  if ($("#birth-sync")) $("#birth-sync").hidden = false;
  if ($("#birth-keep")) $("#birth-keep").hidden = false;
}

async function handleBirthError(error) {
  if (["birth_version_conflict", "birth_version_required"].includes(error.code)) {
    await refresh();
    if ($("#birth-form")) showBirthConflict();
  }
}

function invalidateChart() {
  if (state) state.chart = null;
  page.onChart?.(null);
}

async function submitBirth(mode) {
  if (busy || !state || !validateBirth()) return;
  ++localStateEpoch;
  clearTimeout(refreshTimer);
  setBusy(true);
  try {
    const birth = birthInfo();
    if (mode === "bazi" || mode === "astro") {
      const result = await api("/api/chart", {
        method: "POST",
        body: JSON.stringify({ system: mode, birth }),
      });
      if (result.code !== "safety_confirmation_required") acceptBirthVersion(result.birth_version);
      applyState(result);
      setBirthFeedback(result.question || "已排盘，可以就此发问。", !result.question);
      toast(result.question || (mode === "bazi" ? "四柱已排出。" : "本命星图已绘出。"));
      if (!result.question) {
        foldBirth(result.birth, false);
        $(".band-work")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } else {
      const result = await api("/api/birth", { method: "PUT", body: JSON.stringify(birth) });
      acceptBirthVersion(result.birth_version);
      applyState(result);
      setBirthFeedback("生辰已保存，八字、星盘与运势页都会用到。", true);
      toast("生辰已保存。");
      foldBirth(result.birth, false);
      await page.onBirthSaved?.(result.birth);
    }
  } catch (error) {
    toast(error.message);
    await handleBirthError(error);
  } finally {
    setBusy(false);
  }
}

function birthInfo() {
  const saved = state?.birth || {};
  const unknown = $("#unknown-time").checked;
  return {
    date: $("#birth-date").value || null,
    time: unknown ? "" : $("#birth-time").value,
    unknown_time: unknown,
    time_period: unknown ? ($("#birth-time-period")?.value || "unknown") : "",
    location_id: selectedLocation?.location_id || "",
    place: selectedLocation?.display_name || "",
    gender: $("#birth-gender") ? $("#birth-gender").value : saved.gender || "",
    clock_tz: selectedLocation?.tz === "Asia/Urumqi" ? $("#birth-clock").value : "",
    true_solar_time: $("#solar-time")
      ? $("#solar-time").value === "true"
      : Boolean(saved.true_solar_time),
    zishi_rule: $("#zishi-rule") ? $("#zishi-rule").value : saved.zishi_rule || "next_day",
  };
}

function validateBirth() {
  if (locationLoading) {
    toast("地点正在加载，请稍候。");
    return false;
  }
  if (lunarConverting) {
    toast("农历日期正在换算，请稍候。");
    return false;
  }
  if ($("#birth-year")) {
    const partial = [$("#birth-year").value, $("#birth-month").value, $("#birth-day").value].filter(Boolean).length;
    if (partial > 0 && !$("#birth-date").value) {
      toast(calendarMode === "lunar" ? "请选齐有效的农历年、月、日。" : "请选齐出生年、月、日。");
      return false;
    }
  }
  if ($("#birth-province").value && !selectedLocation) {
    toast("请继续选择城市和县区，以确定出生地点。");
    return false;
  }
  const time = $("#birth-time");
  time.setCustomValidity(
    time.value && !$("#birth-date").value && !$("#unknown-time").checked
      ? "请先填写出生日期"
      : "",
  );
  // A folded form cannot show its validation message; open it first.
  if (!$("#birth-form").checkValidity()) openBirthFold();
  return $("#birth-form").reportValidity();
}

/* The birth form lives in a <details> fold under the page heading on 八字, 星盘 and 运势. */
function foldBirth(birth, open) {
  const fold = $("[data-birth-fold]");
  if (!fold) return;
  const summary = $("[data-birth-summary]", fold);
  summary.dataset.empty ??= summary.textContent;
  const filled = Boolean(birth?.date);
  summary.classList.toggle("filled", filled);
  summary.textContent = filled
    ? [
        `公历 ${birth.date} ${formatBirthTime(birth)}`,
        birth.place || "地点待补充",
        ...(birth.gender ? [birth.gender === "female" ? "女" : "男"] : []),
      ].join(" · ")
    : summary.dataset.empty;
  fold.open = open;
}

function openBirthFold() {
  const fold = $("[data-birth-fold]");
  if (!fold) return;
  fold.open = true;
  fold.scrollIntoView({ behavior: "smooth", block: "start" });
}

// The birth bar's action submits the folded form; an unfinished one is opened instead.
function submitBirthFromBar() {
  if (busy || !state) return;
  if (!$("#birth-date").value || !selectedLocation) {
    openBirthFold();
    toast("请先填写出生日期与出生地点。");
    return;
  }
  if (!validateBirth()) return;
  $("#birth-form").requestSubmit();
}

function fillBirthForm(birth) {
  $("#birth-date").value = birth.date || "";
  if ($("#birth-year")) syncAskDropdownsFromSolar(birth.date || "");
  $("#birth-time").value = birth.time || "";
  if ($("#birth-shichen")) $("#birth-shichen").value = shichenOfClock(birth.time || "");
  $("#unknown-time").checked = Boolean(birth.unknown_time);
  if ($("#birth-time-period")) $("#birth-time-period").value = birth.time_period || "unknown";
  syncTimeControl();
  if ($("#birth-gender")) $("#birth-gender").value = birth.gender || "";
  syncGenderSeg(birth.gender || "");
  if ($("#solar-time")) $("#solar-time").value = String(birth.true_solar_time || false);
  if ($("#zishi-rule")) $("#zishi-rule").value = birth.zishi_rule || "next_day";
  $("#birth-clock").value = birth.clock_tz || "";
  if (birth.date) setBirthFeedback("已载入保存的生辰。", true);
  if (selectedLocation?.location_id !== birth.location_id)
    restoreLocation(birth.location_id || "").catch((error) => toast(error.message));
  updateBirthProgress();
}

function updateLocationDisabled() {
  LOCATION_FIELDS.forEach((field, index) => {
    const select = $(`#birth-${field}`);
    select.disabled =
      busy ||
      !state ||
      locationLoading ||
      (index > 0 && !$(`#birth-${LOCATION_FIELDS[index - 1]}`).value) ||
      select.options.length < 2;
    // A single city-centroid option is displayed read-only, but remains selected.
  });
}

function fillOptions(field, options, placeholder) {
  const select = $(`#birth-${field}`);
  select.replaceChildren(new Option(placeholder, ""));
  for (const item of options) select.append(new Option(item.name, item.id));
}

function resetLocationBelow(index) {
  selectedLocation = null;
  for (let i = index + 1; i < LOCATION_FIELDS.length; i++)
    fillOptions(LOCATION_FIELDS[i], [], "请先选择上一级");
  $("#clock-settings").hidden = true;
  $("#birth-clock").value = "";
  $("#location-feedback").textContent = "逐级选择，自动匹配出生地经纬度与时区。";
  if (birthMode === "bazi" || birthMode === "astro") invalidateChart();
  updateBirthProgress();
}

async function acceptLocation(identity, version) {
  const location = await api(`/api/locations/${encodeURIComponent(identity)}`);
  if (version !== locationVersion) return;
  selectedLocation = location;
  $("#clock-settings").hidden = location.tz !== "Asia/Urumqi";
  $("#location-feedback").textContent = `${location.display_name} · ${location.tz}。${
    location.precision === "city centroid"
      ? "当前采用城市中心；该地区未收录区县层级。"
      : "采用所选行政区中心坐标。"
  }`;
  updateBirthProgress();
}

async function locationChanged(index) {
  const version = ++locationVersion;
  resetLocationBelow(index);
  const identity = $(`#birth-${LOCATION_FIELDS[index]}`).value;
  if (!identity) {
    updateLocationDisabled();
    return;
  }
  locationLoading = true;
  updateLocationDisabled();
  try {
    if (index === 3) {
      await acceptLocation(identity, version);
      return;
    }
    const data = await api(`/api/locations?parent=${encodeURIComponent(identity)}`);
    if (version !== locationVersion) return;
    if (index === 2 && !data.options.length) {
      fillOptions("district", [{ id: identity, name: "市级地点（未收录区县）" }], "请选择地点精度");
      $("#birth-district").value = identity;
      await acceptLocation(identity, version);
    } else {
      fillOptions(
        LOCATION_FIELDS[index + 1],
        data.options,
        ["", "请选择省 / 州", "请选择城市", "请选择县 / 区"][index + 1],
      );
    }
  } catch (error) {
    if (version === locationVersion) toast(error.message);
  } finally {
    if (version === locationVersion) {
      locationLoading = false;
      updateLocationDisabled();
    }
  }
}

async function initLocations() {
  const data = await api("/api/locations");
  fillOptions("country", data.options, "请选择国家 / 地区");
  $("#birth-country").value = "CN";
  await locationChanged(0);
}

async function restoreLocation(identity) {
  const restore = ++restoringBirth;
  const restoredChart = state?.chart;
  await locationsReady;
  if (restore !== restoringBirth) return;
  if (!identity) {
    $("#birth-country").value = "CN";
    await locationChanged(0);
    return;
  }
  const location = await api(`/api/locations/${encodeURIComponent(identity)}`);
  if (restore !== restoringBirth) return;
  for (const item of location.path) {
    if (restore !== restoringBirth) return;
    const index = LOCATION_FIELDS.indexOf(item.level);
    if (index < 0) continue;
    $(`#birth-${item.level}`).value = item.id;
    await locationChanged(index);
  }
  if (restore !== restoringBirth) return;
  selectedLocation = location;
  // Restoring a saved path must not discard the server's matching chart or clock choice.
  if (state?.birth.clock_tz) $("#birth-clock").value = state.birth.clock_tz;
  if (state && restoredChart && restoredChart.birth_version === state.birth_version) {
    state.chart = restoredChart;
    page.onChart?.(restoredChart, true);
  }
}

/* ---------- 问道 · 首页 ---------- */

function spreadAngles(items, minGap = 13) {
  if (items.length <= 1) return items.map((item) => ({ ...item, drawLon: item.lon }));
  const sorted = items
    .map((item, idx) => ({ ...item, idx, drawLon: ((item.lon % 360) + 360) % 360 }))
    .sort((a, b) => a.drawLon - b.drawLon);
  for (let pass = 0; pass < 8; pass++) {
    for (let i = 0; i < sorted.length; i++) {
      const a = sorted[i];
      const b = sorted[(i + 1) % sorted.length];
      const diff = (b.drawLon - a.drawLon + 360) % 360;
      if (diff < minGap) {
        const push = (minGap - diff) / 2;
        a.drawLon = (a.drawLon - push + 360) % 360;
        b.drawLon = (b.drawLon + push) % 360;
      }
    }
  }
  return sorted.sort((a, b) => a.idx - b.idx);
}

function renderMiniChart(astro) {
  const mini = $("#mini-chart");
  if (!mini) return;
  const filled = Boolean(astro && astro.planets?.length);
  const asc = filled ? Number(astro.asc_lon) || 0 : 0;
  const pointAt = (lon, r) => {
    const rad = ((180 - (lon - asc)) * Math.PI) / 180;
    return [r * Math.cos(rad), r * Math.sin(rad)];
  };

  // 1) 纯白铜版表盘底 + 极细外环与刻度
  let m = `<circle r="48" fill="#ffffff" stroke="rgba(22,22,20,.14)" stroke-width="0.7"/>`;
  m += `<path fill="rgba(37,50,76,.035)" fill-rule="evenodd" d="M0 -48A48 48 0 1 1 0 48A48 48 0 1 1 0 -48ZM0 -40A40 40 0 1 0 0 40A40 40 0 1 0 0 -40Z"/>`;
  m += `<circle r="48" fill="none" stroke="rgba(155,122,67,.48)" stroke-width="0.7"/>`;
  m += `<circle r="40" fill="none" stroke="rgba(22,22,20,.16)" stroke-width="0.55"/>`;

  // 36 格黄道精密刻度（按真实上升点旋转）
  for (let deg = 0; deg < 360; deg += 10) {
    const major = deg % 30 === 0;
    const [x1, y1] = pointAt(deg, 48);
    const [x2, y2] = pointAt(deg, major ? 40 : 45.2);
    m += `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${major ? "rgba(155,122,67,.52)" : "rgba(22,22,20,.16)"}" stroke-width="${major ? 0.65 : 0.45}"/>`;
  }

  // 十二宫极细分隔线与地平/子午轴
  for (let i = 0; i < 12; i++) {
    const rad = (i * 30 * Math.PI) / 180;
    const axis = i % 3 === 0;
    const x1 = (24.5 * Math.cos(rad)).toFixed(1);
    const y1 = (24.5 * Math.sin(rad)).toFixed(1);
    const x2 = (40 * Math.cos(rad)).toFixed(1);
    const y2 = (40 * Math.sin(rad)).toFixed(1);
    m += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${axis ? "rgba(155,122,67,.42)" : "rgba(22,22,20,.09)"}" stroke-width="${axis ? 0.6 : 0.45}"/>`;
  }

  // 内相位盘（留白通透，不放遮挡文字的大圆）
  m += `<circle r="24.5" fill="#fbf9f5" stroke="rgba(155,122,67,.42)" stroke-width="0.65"/>`;

  if (!filled) {
    m += `<path d="M0 -21 L18.2 10.5 L-18.2 10.5 Z" fill="none" stroke="rgba(155,122,67,.45)" stroke-width="0.65" stroke-dasharray="1.8 2"/>`;
    m += `<text text-anchor="middle" dominant-baseline="central" font-family="Noto Serif SC,serif" font-size="11" fill="rgba(22,22,20,.24)">？</text>`;
    mini.innerHTML = m;
    return;
  }

  // 真实地平线微标（左侧上升点 ASC 菱形指针）
  m += `<line x1="-48" y1="0" x2="-40" y2="0" stroke="#a83228" stroke-width="0.9"/>`;
  m += `<polygon points="-48,0 -45.5,-1.8 -43,0 -45.5,1.8" fill="#a83228"/>`;

  // 相位几何网（过滤掉合相短桩，取最精确的 6 条主相位，精准落在内环 r=24.5 上）
  const byBody = new Map(astro.planets.map((p) => [p.body, p]));
  const chordAspects = (astro.aspects || [])
    .filter((asp) => asp.type !== "conjunction")
    .slice(0, 6);
  const aspectStroke = (type) => {
    if (type === "square" || type === "opposition") return "rgba(168,50,40,.48)";
    return "rgba(37,50,76,.44)";
  };
  chordAspects.forEach((asp) => {
    const pa = byBody.get(asp.a);
    const pb = byBody.get(asp.b);
    if (!pa || !pb) return;
    const [x1, y1] = pointAt(pa.lon, 24.2);
    const [x2, y2] = pointAt(pb.lon, 24.2);
    m += `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${aspectStroke(asp.type)}" stroke-width="0.7" stroke-linecap="round"/>`;
  });
  m += `<circle r="1.4" fill="#fbf9f5" stroke="rgba(155,122,67,.6)" stroke-width="0.55"/>`;

  // 行星精准刻度指针 + 避让散开后的星点（太阳双环☉、月亮弯月☽、其余精雕微点）
  const spread = spreadAngles(astro.planets, 13);
  spread.forEach((p) => {
    const [tx1, ty1] = pointAt(p.lon, 24.5);
    const [tx2, ty2] = pointAt(p.lon, 27.6);
    m += `<line x1="${tx1.toFixed(1)}" y1="${ty1.toFixed(1)}" x2="${tx2.toFixed(1)}" y2="${ty2.toFixed(1)}" stroke="rgba(22,22,20,.28)" stroke-width="0.5"/>`;

    const [x, y] = pointAt(p.drawLon, 33.2);
    const cx = x.toFixed(1);
    const cy = y.toFixed(1);
    if (p.body === "Sun") {
      m += `<circle cx="${cx}" cy="${cy}" r="3.1" fill="#ffffff" stroke="#a83228" stroke-width="0.9"/>`;
      m += `<circle cx="${cx}" cy="${cy}" r="1.15" fill="#a83228"/>`;
    } else if (p.body === "Moon") {
      m += `<circle cx="${cx}" cy="${cy}" r="2.7" fill="#25324c" stroke="#ffffff" stroke-width="0.6"/>`;
      m += `<circle cx="${(x + 1.05).toFixed(1)}" cy="${(y - 0.35).toFixed(1)}" r="1.75" fill="#ffffff"/>`;
    } else {
      const inner = ["Mercury", "Venus", "Mars"].includes(p.body);
      m += `<circle cx="${cx}" cy="${cy}" r="${inner ? 1.85 : 1.55}" fill="${inner ? "#25324c" : "#9b7a43"}" stroke="#ffffff" stroke-width="0.65"/>`;
    }
  });

  mini.innerHTML = m;
}

function renderBirthPreview(preview) {
  const pillarsEl = $("#mini-pillars");
  const labelEl = $("#preview-label");
  const capBazi = $("#preview-cap-bazi");
  const capAstro = $("#preview-cap-astro");
  if (!pillarsEl) return;
  const bazi = preview?.bazi;
  const astro = preview?.astro;
  const hasBazi = Boolean(bazi?.pillars?.year && bazi?.pillars?.day);
  pillarsEl.classList.toggle("filled", hasBazi);
  if (labelEl) {
    labelEl.textContent = hasBazi ? "— 你的命盘预览 —" : "— 填好后你将看到 —";
  }
  const keys = ["year", "month", "day", "time"];
  keys.forEach((key) => {
    const box = pillarsEl.querySelector(`[data-pillar="${key}"]`);
    if (!box) return;
    const bs = box.querySelectorAll("b");
    const gz = hasBazi ? bazi.pillars[key] || "" : "";
    box.classList.toggle("is-uncertain", Boolean(hasBazi && key === "time" && bazi.unknown_time));
    if (bs.length >= 2) {
      bs[0].textContent = gz.length >= 1 ? gz[0] : "？";
      bs[1].textContent = gz.length >= 2 ? gz[1] : "？";
    }
  });
  if (capBazi) {
    capBazi.textContent = hasBazi
      ? `日主 ${bazi.day_master || "—"} · 四柱已排`
      : "四柱八字 · 五行 · 大运";
  }
  renderMiniChart(astro);
  if (capAstro) {
    if (astro?.sun_sign_zh) {
      capAstro.textContent = astro.asc_sign_zh
        ? `日${astro.sun_sign_zh.replace("座", "")} · 升${astro.asc_sign_zh.replace("座", "")}`
        : `太阳${astro.sun_sign_zh}`;
    } else {
      capAstro.textContent = "本命星盘";
    }
  }
}

let draftPreviewTimer = null;

function scheduleDraftPreview() {
  if (PAGE !== "ask" || !state || !$("#birth-form")) return;
  clearTimeout(draftPreviewTimer);
  const draft = birthInfo();
  if (!draft.date || !draft.location_id) {
    if (!state.birth?.date) renderBirthPreview(null);
    return;
  }
  draftPreviewTimer = setTimeout(() => {
    if (!state || busy) return;
    const current = birthInfo();
    if (current.date && current.location_id) {
      refreshAskAlmanac(current);
    }
  }, 260);
}

function renderAskVisuals() {
  const horizon = $("#horizon");
  if (horizon) {
    const W = 1440;
    const H = 250;
    const curve = (pts, close) => {
      let d = close ? `M0 ${H} L${pts[0][0]} ${pts[0][1]}` : `M${pts[0][0]} ${pts[0][1]}`;
      for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[i - 1] || pts[i];
        const p1 = pts[i];
        const p2 = pts[i + 1];
        const p3 = pts[i + 2] || p2;
        const t = 0.22;
        const c1 = [p1[0] + (p2[0] - p0[0]) * t, p1[1] + (p2[1] - p0[1]) * t];
        const c2 = [p2[0] - (p3[0] - p1[0]) * t, p2[1] - (p3[1] - p1[1]) * t];
        d += ` C${c1[0].toFixed(1)} ${c1[1].toFixed(1)} ${c2[0].toFixed(1)} ${c2[1].toFixed(1)} ${p2[0]} ${p2[1]}`;
      }
      return close ? `${d} L${W} ${H} Z` : d;
    };
    const far = [
      [0, 126], [140, 96], [300, 114], [490, 74], [690, 108],
      [890, 66], [1080, 98], [1260, 72], [1440, 102],
    ];
    const near = [
      [0, 168], [180, 134], [380, 158], [600, 124],
      [820, 152], [1040, 118], [1260, 146], [1440, 130],
    ];
    let ticks = "";
    const cx = 720;
    const cy = 860;
    const R = 805;
    for (let a = -38; a <= 38; a += 2) {
      const rad = (a * Math.PI) / 180;
      const major = a % 10 === 0;
      const r1 = R;
      const r2 = R - (major ? 10 : 5);
      ticks += `<line x1="${(cx + r1 * Math.sin(rad)).toFixed(1)}" y1="${(cy - r1 * Math.cos(rad)).toFixed(1)}" x2="${(cx + r2 * Math.sin(rad)).toFixed(1)}" y2="${(cy - r2 * Math.cos(rad)).toFixed(1)}" stroke="rgba(155,122,67,${major ? 0.34 : 0.16})" stroke-width="${major ? 0.9 : 0.6}"/>`;
    }
    horizon.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMax slice">
  <defs>
    <linearGradient id="wash-far" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ded8ca" stop-opacity=".8"/>
      <stop offset=".75" stop-color="#eae5d9" stop-opacity=".42"/>
      <stop offset="1" stop-color="#f6f3ec" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="wash-near" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#d2cab9" stop-opacity=".72"/>
      <stop offset=".68" stop-color="#e5dfd1" stop-opacity=".35"/>
      <stop offset="1" stop-color="#f6f3ec" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="mist" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#f6f3ec" stop-opacity="0"/>
      <stop offset="1" stop-color="#f6f3ec" stop-opacity="1"/>
    </linearGradient>
  </defs>
  <circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="rgba(155,122,67,0.3)" stroke-width="0.8"/>
  <circle cx="${cx}" cy="${cy}" r="${R - 14}" fill="none" stroke="rgba(37,50,76,0.18)" stroke-width="0.65" stroke-dasharray="2 6"/>
  ${ticks}
  <path d="${curve(far, true)}" fill="url(#wash-far)"/>
  <path d="${curve(far, false)}" fill="none" stroke="rgba(155,122,67,0.28)" stroke-width="0.8"/>
  <path d="${curve(near, true)}" fill="url(#wash-near)"/>
  <path d="${curve(near, false)}" fill="none" stroke="rgba(22,22,20,0.16)" stroke-width="0.8"/>
  <rect x="0" y="${H - 76}" width="${W}" height="76" fill="url(#mist)"/>
</svg>`;
  }

  const wm = $("#wm");
  if (wm) {
    const romans = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
    let s = `<g fill="none" stroke="#9b7a43" stroke-width="0.9"><circle r="150"/><circle r="122"/><circle r="86"/><circle r="48"/></g>`;
    romans.forEach((rm, i) => {
      const a = i * 30;
      s += `<line x1="0" y1="-122" x2="0" y2="-150" stroke="#9b7a43" stroke-width="0.7" transform="rotate(${a + 15})"/>`;
      s += `<text transform="rotate(${a}) translate(0 -136)" text-anchor="middle" dominant-baseline="central" font-family="Garamond,Georgia,serif" font-size="14" fill="#9b7a43">${rm}</text>`;
    });
    wm.innerHTML = s;
  }

  renderMiniChart(null);
}

let lastAlmanacKey = null;

function refreshAskAlmanac(birth, force = false) {
  const hasBirth = Boolean(birth?.date && birth?.location_id);
  const key = hasBirth ? JSON.stringify(birth) : "plain";
  if (!force && key === lastAlmanacKey) return;
  lastAlmanacKey = key;
  const payload = hasBirth ? { birth } : {};
  api("/api/almanac", { method: "POST", body: JSON.stringify(payload) })
    .then((day) => {
      $("#today-line").textContent =
        `${day.year_pillar}年 · ${day.lunar_date} · ${day.current_term}`;
      if ($("#today-gregorian")) {
        $("#today-gregorian").textContent = (day.date || "").replaceAll("-", " · ");
      }
      if ($("#today-year-pillar")) $("#today-year-pillar").textContent = day.year_pillar || "——";
      if ($("#today-month-pillar")) $("#today-month-pillar").textContent = day.month_pillar || "——";
      if ($("#today-day-pillar")) $("#today-day-pillar").textContent = day.day_pillar || "——";
      if ($("#today-term")) $("#today-term").textContent = day.current_term || "—";
      if ($("#today-moon-phase")) {
        $("#today-moon-phase").textContent = day.sky?.moon_phase_zh || "—";
      }
      if ($("#today-sun-sign")) $("#today-sun-sign").textContent = day.sky?.sun_sign_zh || "—";
      if ($("#today-mercury")) $("#today-mercury").textContent = day.sky?.mercury_status || "—";
      renderBirthPreview(day.birth_preview || null);
      const foot = $("#today-foot");
      if (foot) {
        foot.replaceChildren();
        if (day.ten_god && day.day_master) {
          foot.classList.add("personal");
          foot.append(
            document.createTextNode(`今日流日天干于你日主（${day.day_master}）为「`),
            node("strong", "", day.ten_god),
            document.createTextNode("」。"),
          );
        } else if (day.question) {
          foot.classList.remove("personal");
          foot.textContent = day.question;
        } else {
          foot.classList.remove("personal");
          foot.textContent = "录入生辰后，这里会显示与你日主相关的流日十神。";
        }
      }
    })
    .catch(() => {
      $("#today-line").textContent = "今日";
    });
}

/* The 生辰档案 panel leads the page: an empty profile shows its form straight away, a saved one
   its summary, with the form behind 修改生辰. */
function renderProfile(birth, editing = false) {
  const filled = Boolean(birth?.date);
  $("#enroll").classList.toggle("filled", filled);
  $("#profile-status").textContent = filled ? "已保存" : "未填写";
  $("#hero-enroll").textContent = filled ? "查看生辰档案" : "录入生辰档案";
  $("#enroll-saved").hidden = !filled;
  $("#birth-details").hidden = filled && !editing;
  if ($("#birth-dots")) $("#birth-dots").hidden = filled && !editing;
  $("#edit-birth").textContent = filled && editing ? "收起" : "修改生辰";
  const list = $("#profile-list");
  list.replaceChildren();
  if (!filled) return;
  const rows = [
    ["公历", `${birth.date} ${formatBirthTime(birth)}`],
    ["出生地", birth.place || "地点待补充"],
  ];
  if (birth.gender) rows.push(["性别", birth.gender === "female" ? "女" : "男"]);
  const dl = node("dl", "profile-dl");
  rows.forEach(([key, value]) => dl.append(node("dt", "", key), node("dd", "", value)));
  list.append(dl);
}

function renderRecent(history) {
  const list = $("#recent-list");
  if (!list) return;
  list.replaceChildren();
  if (!history.length) {
    const empty = node("div", "empty");
    empty.innerHTML =
      '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M6 4h14l6 6v18H6z" /><path d="M20 4v6h6M10.5 15h11M10.5 19.5h11M10.5 24h6.5" /></svg>';
    empty.append(
      node("span", "", "还没有提问记录。录入生辰后，从任意一门进入发问，解读会留在这里。"),
    );
    list.append(empty);
    return;
  }
  history.slice(0, 5).forEach((item) => list.append(historyButton(item, "recent-item")));
}

/* ---------- 八字 ---------- */

const PILLARS = [
  ["year", "年柱"],
  ["month", "月柱"],
  ["day", "日柱"],
  ["time", "时柱"],
];

const REDUCED_MOTION = matchMedia("(prefers-reduced-motion: reduce)");
REDUCED_MOTION.addEventListener?.("change", () => {
  if (!REDUCED_MOTION.matches) return;
  $("#name-board")?.classList.remove("is-revealing");
  $("#wuge")?.classList.remove("is-counting");
});

// Re-adding a class restarts its CSS animation even when the element already has it.
function replay(element, className) {
  if (!element || REDUCED_MOTION.matches) return;
  element.classList.remove(className);
  void element.offsetWidth;
  element.classList.add(className);
}

const chartKeys = {};
function freshChart(name, key, silent = false) {
  const before = chartKeys[name];
  chartKeys[name] = key;
  return !silent && !REDUCED_MOTION.matches && before !== undefined && before !== key && key !== "null";
}

function renderBazi(chart, silent = false) {
  const result = chart?.system === "bazi" ? chart.result : null;
  $("#bazi-empty").hidden = Boolean(result);
  const pillars = $("#pillars");
  pillars.replaceChildren();
  for (const [key, label] of PILLARS) {
    const value = result?.pillars?.[key];
    const isDay = key === "day";
    const plaque = node("article", `plaque${isDay ? " plaque-day" : ""}${value ? "" : " plaque-empty"}`);
    plaque.setAttribute("aria-label", `${label}${value ? "：" + value : "：未知"}`);
    plaque.append(
      node("div", "plaque-band", label),
      node("span", "plaque-god", isDay ? "日主" : result?.ten_gods_stems?.[key] || "　"),
      node("span", "plaque-char plaque-stem", value ? value[0] : "—"),
      elementTag(value ? elementOf(value[0]) : ""),
      node("span", "plaque-rule"),
      node("span", "plaque-char plaque-branch", value ? value[1] : "—"),
      elementTag(value ? elementOf(value[1]) : ""),
    );
    const facts = node("dl", "plaque-facts");
    facts.append(
      node("dt", "", "藏干"),
      node("dd", "", result?.hidden_stems?.[key]?.join(" ") || (result ? "时辰不详" : "—")),
      node("dt", "", "纳音"),
      node("dd", "", result?.nayin?.[key] || "—"),
    );
    plaque.append(facts);
    plaque.style.setProperty("--i", String(pillars.childElementCount));
    pillars.append(plaque);
  }

  const wuxing = $("#wuxing");
  wuxing.replaceChildren();
  for (const element of ELEMENTS) {
    const count = result?.wuxing_count?.[element] ?? 0;
    const beads = node("span", "beads");
    beads.setAttribute("aria-hidden", "true");
    for (let i = 0; i < 8; i++) {
      const bead = node("i", i < count ? "bead on" : "bead");
      bead.dataset.element = element;
      if (i < count) bead.style.setProperty("--b", String(wuxing.querySelectorAll(".bead.on").length + beads.querySelectorAll(".on").length));
      beads.append(bead);
    }
    const row = node("div", "wuxing-row");
    row.setAttribute("aria-label", `${element} ${result ? count : "未排盘"}`);
    row.append(elementTag(element, "el-badge"), beads, node("span", "wuxing-count", result ? String(count) : "—"));
    wuxing.append(row);
  }

  const revealing = freshChart(
    "bazi",
    JSON.stringify(result ? [result.pillars, result.dayun?.start_solar ?? null] : null),
    silent,
  );
  for (const box of [pillars, wuxing, $("#dayun")])
    box?.classList.toggle("is-revealing", revealing);
  if (revealing) replay($(".dm-panel"), "is-revealing");
  else $(".dm-panel")?.classList.remove("is-revealing");

  const master = result?.day_master;
  $("#dm-name").textContent = master || "—";
  if (master) {
    const yin = GAN.indexOf(master[0]) % 2 ? "阴" : "阳";
    $("#dm-detail").textContent = `${yin}${master[1]} · 生于${result.pillars.month[1]}月`;
  } else $("#dm-detail").textContent = "排盘后显示";

  const meta = $("#bazi-meta");
  if (result) {
    const gender = { female: "坤造", male: "乾造" }[chart.birth.gender] || "未填性别";
    const displayDate = chart.birth?.date || (result.input?.birth_local || "").slice(0, 10);
    meta.textContent = `${gender} · 公历 ${displayDate} ${formatBirthTime(chart.birth)} · ${chart.location.display_name} · 农历${result.lunar_date}`;
  } else meta.textContent = "填写公历生辰与出生地，排出属于你的四柱。";

  const dayun = $("#dayun");
  dayun.replaceChildren();
  const sequence = result?.dayun?.sequence || [];
  const year = Number(shanghaiToday().slice(0, 4));
  sequence.forEach((item, index) => {
    const current = item.start_year <= year && (sequence[index + 1]?.start_year ?? Infinity) > year;
    const step = node("li", current ? "dayun-step current" : "dayun-step");
    if (current) step.setAttribute("aria-current", "true");
    step.append(
      node("span", "dayun-age", `${item.start_age} 岁${current ? " · 当前" : ""}`),
      node("span", "dayun-gz", item.ganzhi),
      node("span", "dayun-years", `${item.start_year}–${item.start_year + 9}`),
    );
    step.style.setProperty("--i", String(index));
    dayun.append(step);
  });
  $("#dayun-start").textContent = result?.dayun
    ? `起运：${result.dayun.start_solar}（出生后 ${result.dayun.start_after}）· ${result.dayun.forward ? "顺行" : "逆行"}`
    : result
      ? "填写性别后即可排出十年大运。"
      : "排盘并填写性别后显示十年大运。";

  const notes = $("#bazi-notes");
  notes.replaceChildren();
  if (result) {
    notes.append(
      node(
        "p",
        "",
        `${chart.birth.true_solar_time ? "出生地真太阳时" : "固定 UTC+8（不用真太阳时）"} · ${chart.birth.zishi_rule === "same_day" ? "0 点换日" : "23 点换日"} · 立春换年 / 节气换月 · 五行按天干与地支主气计数，不等同于旺衰判断`,
      ),
    );
    (result.uncertainty || []).forEach((note) => notes.append(node("p", "", note)));
  }
}

/* ---------- 星盘 ---------- */

const PLANET_MARK = {
  Sun: "日",
  Moon: "月",
  Mercury: "水",
  Venus: "金",
  Mars: "火",
  Jupiter: "木",
  Saturn: "土",
  Uranus: "天",
  Neptune: "海",
  Pluto: "冥",
};
const SIGNS = "白羊 金牛 双子 巨蟹 狮子 处女 天秤 天蝎 射手 摩羯 水瓶 双鱼".split(" ");
const ASPECT_NAMES = {
  conjunction: "合",
  sextile: "六合",
  square: "刑",
  trine: "拱",
  opposition: "冲",
};

function natalWheel(result) {
  const c = 320;
  const asc = result?.axes?.asc ?? 0;
  const point = (longitude, radius) => {
    const theta = ((180 + longitude - asc) * Math.PI) / 180;
    return [c + radius * Math.cos(theta), c - radius * Math.sin(theta)];
  };
  const line = (from, to, className) =>
    svgNode("line", { x1: from[0].toFixed(1), y1: from[1].toFixed(1), x2: to[0].toFixed(1), y2: to[1].toFixed(1), class: className });
  const svg = svgNode("svg", {
    viewBox: "-36 -36 712 712",
    class: "natal-wheel",
    role: "img",
    "aria-label": result
      ? `本命星图：${result.asc ? "上升" + result.asc.sign_zh + "，" : ""}${result.planets
          .slice(0, 2)
          .map((p) => p.body_zh + p.sign_zh)
          .join("，")}`
      : "本命星图（待绘制）",
  });
  svg.append(
    svgNode("circle", { cx: c, cy: c, r: 300, class: "nw-ring-o" }),
    svgNode("circle", { cx: c, cy: c, r: 252, class: "nw-ring" }),
    svgNode("circle", { cx: c, cy: c, r: 236, class: "nw-ring" }),
  );
  for (let degree = 0; degree < 360; degree += 5) {
    const outer = degree % 30 === 0 ? 300 : degree % 10 === 0 ? 264 : 258;
    svg.append(line(point(degree, 252), point(degree, outer), degree % 30 === 0 ? "nw-sign-sep" : "nw-tick"));
  }
  SIGNS.forEach((sign, index) => {
    const [x, y] = point(index * 30 + 15, 278);
    svg.append(svgNode("text", { x: x.toFixed(1), y: (y + 4).toFixed(1), class: "nw-sign" }, sign));
  });
  const cusps = result?.cusps ? Object.values(result.cusps) : [];
  cusps.forEach((cusp, index) => {
    const axis = index % 3 === 0;
    svg.append(line(point(cusp, 120), point(cusp, axis && (index === 0 || index === 9) ? 312 : 252), axis ? "nw-axis" : "nw-cusp"));
    const next = cusps[(index + 1) % 12];
    const [x, y] = point(cusp + ((next - cusp + 360) % 360) / 2, 134);
    svg.append(svgNode("text", { x: x.toFixed(1), y: (y + 3).toFixed(1), class: "nw-house" }, String(index + 1)));
  });
  svg.append(svgNode("circle", { cx: c, cy: c, r: 120, class: "nw-core" }));
  if (!result) {
    svg.append(svgNode("text", { x: c, y: c + 6, class: "nw-empty" }, "待绘制"));
    svg.classList.add("is-idle");
    return svg;
  }
  const planets = result.planets;
  const position = Object.fromEntries(planets.map((p) => [p.body, p.lon]));
  for (const aspect of result.aspects || []) {
    if (!(aspect.a in position) || !(aspect.b in position) || aspect.type === "conjunction") continue;
    const soft = aspect.type === "sextile" || aspect.type === "trine";
    svg.append(line(point(position[aspect.a], 118), point(position[aspect.b], 118), soft ? "nw-asp-soft" : "nw-asp-hard"));
  }
  // Spread crowded labels apart; the tick on the ring keeps the exact longitude.
  const shown = Object.fromEntries(planets.map((p) => [p.body, p.lon]));
  for (let round = 0; round < 60; round++) {
    const ordered = Object.entries(shown).sort((a, b) => a[1] - b[1]);
    ordered.forEach(([body, lon], index) => {
      const [nextBody, nextLon] = ordered[(index + 1) % ordered.length];
      const gap = (nextLon - lon + 360) % 360;
      if (gap < 9) {
        shown[body] = (shown[body] - (9 - gap) / 2 + 360) % 360;
        shown[nextBody] = (shown[nextBody] + (9 - gap) / 2) % 360;
      }
    });
  }
  for (const planet of planets) {
    svg.append(line(point(planet.lon, 252), point(planet.lon, 238), "nw-pmark"));
    const [x, y] = point(shown[planet.body], 212);
    svg.append(
      svgNode("circle", { cx: x.toFixed(1), cy: y.toFixed(1), r: 13, class: "nw-pdot" }),
      svgNode("text", { x: x.toFixed(1), y: (y + 4.5).toFixed(1), class: "nw-planet" }, PLANET_MARK[planet.body] || planet.body_zh[0]),
    );
  }
  if (result.axes) {
    const [ax, ay] = point(result.axes.asc, 318);
    svg.append(svgNode("text", { x: (ax - 34).toFixed(1), y: (ay + 4).toFixed(1), class: "nw-axislbl" }, "ASC"));
    const [mx, my] = point(result.axes.mc, 318);
    svg.append(svgNode("text", { x: (mx - 10).toFixed(1), y: (my - 4).toFixed(1), class: "nw-axislbl" }, "MC"));
  }
  return svg;
}

function renderAstro(chart, silent = false) {
  const result = chart?.system === "astro" ? chart.result : null;
  $("#astro-empty").hidden = Boolean(result);
  const wheel = natalWheel(result);
  $("#astro-wheel").replaceChildren(wheel);
  if (freshChart("astro", JSON.stringify(result?.planets?.map((p) => p.lon) ?? null), silent)) {
    wheel.querySelectorAll(".nw-asp-soft, .nw-asp-hard").forEach((item, index) =>
      item.style.setProperty("--i", String(index)));
    const marks = [".nw-pdot", ".nw-planet", ".nw-pmark"].map((name) => wheel.querySelectorAll(name));
    marks.forEach((list) => list.forEach((item, index) => item.style.setProperty("--i", String(index))));
    wheel.querySelectorAll(".nw-ring-o, .nw-ring, .nw-axis, .nw-asp-soft, .nw-asp-hard").forEach((item) =>
      item.style.setProperty("--len", String(Math.ceil(item.getTotalLength?.() || 2000))));
    wheel.classList.add("is-revealing");
  }
  const astroDate = chart?.birth?.date || (result?.input?.birth_local || "").slice(0, 10);
  $("#astro-meta").textContent = result
    ? `公历 ${astroDate} ${formatBirthTime(chart.birth)} · ${chart.location.display_name} · ${result.house_system ? result.house_system + " 宫制" : "不分宫"} · 回归黄道`
    : "填写出生时空，绘出你的本命星图。";

  const trio = $("#astro-trio");
  trio.replaceChildren();
  const sun = result?.planets.find((p) => p.body === "Sun");
  const moon = result?.planets.find((p) => p.body === "Moon");
  for (const [label, sign, degree] of [
    ["太阳", sun?.sign_zh, sun?.deg_in_sign],
    ["月亮", moon?.sign_zh, moon?.deg_in_sign],
    ["上升", result?.asc?.sign_zh, result?.asc ? result.asc.lon % 30 : undefined],
  ]) {
    const cell = node("div", "trio-cell");
    cell.append(
      node("span", "trio-label", label),
      node("span", "trio-sign", sign || (result ? "时刻不详" : "—")),
      node("span", "trio-degree", degree === undefined ? "　" : formatDegrees(degree)),
    );
    trio.append(cell);
  }

  const rows = $("#planet-rows");
  rows.replaceChildren();
  (result?.planets || []).forEach((planet) => {
    const row = node("tr");
    row.append(
      node("td", "", planet.body_zh + (planet.retrograde ? " ℞" : "")),
      node("td", "", planet.sign_zh),
      node("td", "mono", formatDegrees(planet.deg_in_sign)),
      node("td", "mono num", planet.house ? String(planet.house) : "—"),
    );
    rows.append(row);
  });
  if (!result) {
    const row = node("tr");
    const cell = node("td", "table-empty", "绘制星图后列出十颗行星的位置。");
    cell.colSpan = 4;
    row.append(cell);
    rows.append(row);
  }

  const aspects = $("#aspect-list");
  aspects.replaceChildren();
  const names = Object.fromEntries((result?.planets || []).map((p) => [p.body, p.body_zh]));
  (result?.aspects || [])
    .filter((aspect) => aspect.a in names && aspect.b in names)
    .sort((a, b) => a.orb - b.orb)
    .slice(0, 8)
    .forEach((aspect) => {
      const item = node("li", `aspect aspect-${aspect.type}`);
      item.append(
        document.createTextNode(`${names[aspect.a]} `),
        node("b", "", ASPECT_NAMES[aspect.type] || aspect.type),
        document.createTextNode(` ${names[aspect.b]} `),
        node("span", "mono", formatDegrees(aspect.orb)),
      );
      aspects.append(item);
    });
  const notes = $("#astro-notes");
  notes.replaceChildren();
  (result?.uncertainty || []).forEach((note) => notes.append(node("p", "", note)));
}

/* ---------- 塔罗 ---------- */

const MAJORS = [
  ["the_fool", "THE FOOL"],
  ["the_magician", "THE MAGICIAN"],
  ["the_high_priestess", "THE HIGH PRIESTESS"],
  ["the_empress", "THE EMPRESS"],
  ["the_emperor", "THE EMPEROR"],
  ["the_hierophant", "THE HIEROPHANT"],
  ["the_lovers", "THE LOVERS"],
  ["the_chariot", "THE CHARIOT"],
  ["strength", "STRENGTH"],
  ["the_hermit", "THE HERMIT"],
  ["wheel_of_fortune", "WHEEL OF FORTUNE"],
  ["justice", "JUSTICE"],
  ["the_hanged_man", "THE HANGED MAN"],
  ["death", "DEATH"],
  ["temperance", "TEMPERANCE"],
  ["the_devil", "THE DEVIL"],
  ["the_tower", "THE TOWER"],
  ["the_star", "THE STAR"],
  ["the_moon", "THE MOON"],
  ["the_sun", "THE SUN"],
  ["judgement", "JUDGEMENT"],
  ["the_world", "THE WORLD"],
];
const ROMAN = ["0", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI"];
const RANKS = {
  ace: ["I", "ACE"],
  two: ["II", "TWO"],
  three: ["III", "THREE"],
  four: ["IV", "FOUR"],
  five: ["V", "FIVE"],
  six: ["VI", "SIX"],
  seven: ["VII", "SEVEN"],
  eight: ["VIII", "EIGHT"],
  nine: ["IX", "NINE"],
  ten: ["X", "TEN"],
  page: ["", "PAGE"],
  knight: ["", "KNIGHT"],
  queen: ["", "QUEEN"],
  king: ["", "KING"],
};
const SUITS = { wands: "WANDS", cups: "CUPS", swords: "SWORDS", pentacles: "PENTACLES" };
const SPREAD_POSITIONS = {
  single: ["当下提示"],
  three_card: ["过去", "现在", "未来"],
  decision: ["现状", "选 A", "选 B"],
};
const STAR = "60,24 63.8,44.8 81.2,32.8 69.2,50.2 90,54 69.2,57.8 81.2,75.2 63.8,63.2 60,84 56.2,63.2 38.8,75.2 50.8,57.8 30,54 50.8,50.2 38.8,32.8 56.2,44.8";
const EMBLEMS = {
  major: [
    ["polygon", { points: STAR, class: "tr-gold" }],
    ["polygon", { points: STAR, class: "tr-ink" }],
    ["path", { d: "M18 22 L22 26 M102 22 L98 26 M18 92 L22 88 M102 92 L98 88", class: "tr-goldline" }],
    ["path", { d: "M14 104 Q26 98 38 104 T62 104 T86 104 T110 104", class: "tr-ink" }],
  ],
  wands: [
    ["path", { d: "M60 14 L60 106", class: "tr-ink" }],
    ["path", { d: "M60 34 C70 30 75 24 77 16 M60 52 C50 48 45 42 43 34 M60 70 C70 66 75 60 77 52", class: "tr-goldline" }],
    ["circle", { cx: 60, cy: 12, r: 4, class: "tr-gold" }],
  ],
  cups: [
    ["path", { d: "M36 28 L84 28 C84 58 73 68 60 68 C47 68 36 58 36 28 Z", class: "tr-ink" }],
    ["path", { d: "M60 68 L60 94 M44 100 L76 100 M50 94 L70 94", class: "tr-ink" }],
    ["path", { d: "M44 40 C52 46 68 46 76 40", class: "tr-goldline" }],
  ],
  swords: [
    ["path", { d: "M60 10 L67 24 L67 82 L53 82 L53 24 Z", class: "tr-ink" }],
    ["path", { d: "M38 84 L82 84", class: "tr-goldline" }],
    ["path", { d: "M60 86 L60 104", class: "tr-ink" }],
    ["circle", { cx: 60, cy: 108, r: 4, class: "tr-gold" }],
  ],
  pentacles: [
    ["circle", { cx: 60, cy: 58, r: 36, class: "tr-ink" }],
    ["polygon", { points: "60,26 69.4,47.1 92,49.9 75.2,65.4 79.8,87.8 60,76.4 40.2,87.8 44.8,65.4 28,49.9 50.6,47.1", class: "tr-gold" }],
  ],
};

function cardFace(card) {
  const major = MAJORS.findIndex(([id]) => id === card.card_id);
  let numeral = ROMAN[major] || "";
  let english = MAJORS[major]?.[1] || "";
  let suit = "major";
  if (major < 0) {
    const [suitKey, rankKey] = card.card_id.split("_");
    suit = SUITS[suitKey] ? suitKey : "major";
    [numeral, english] = RANKS[rankKey] || ["", ""];
    english = `${english} OF ${SUITS[suitKey] || ""}`.trim();
  }
  const face = node("span", "card-face");
  face.append(node("span", "card-numeral", numeral || "·"));
  const emblem = svgNode("svg", { viewBox: "0 0 120 120", class: card.reversed ? "card-emblem reversed" : "card-emblem", "aria-hidden": "true" });
  EMBLEMS[suit].forEach(([tag, attributes]) => emblem.append(svgNode(tag, attributes)));
  face.append(emblem, node("span", "card-rule"), node("span", "card-name", card.name), node("span", "card-english", english));
  if (card.reversed) face.append(node("span", "card-reversed", "逆位"));
  return face;
}

function cardBack() {
  const back = node("span", "card-face card-back");
  const pattern = svgNode("svg", { viewBox: "0 0 120 200", class: "card-pattern", "aria-hidden": "true" });
  pattern.append(
    svgNode("circle", { cx: 60, cy: 100, r: 44, class: "tr-backline" }),
    svgNode("circle", { cx: 60, cy: 100, r: 30, class: "tr-backline" }),
    svgNode("polygon", { points: STAR, class: "tr-backstar", transform: "translate(30 46) scale(.5)" }),
    svgNode("path", { d: "M60 18 L60 46 M60 154 L60 182 M14 100 L22 100 M98 100 L106 100", class: "tr-backline" }),
  );
  back.append(pattern);
  return back;
}

let spread = "three_card";
/* idle → picking (fan out the deck) → waiting (request sent) → reveal (tap to flip) → done.
   A reply without cards (a clarifying question, an error) leaves the round open: question,
   spread and chosen positions stay, and the next message in the dialogue continues it. */
let tarotPhase = "idle";
let picked = [];
let flipped = new Set();
let drawnKey = "";
let tarotRound = 0; // bumped by every reset; a stale animation callback compares against it
let flights = new Set();
let pendingDraw = null; // { message, spread, picks }, fixed when the last card is chosen
let questionDraft = null; // an unsent question set aside while a saved record is shown
const DECK_SIZE = 78;
const SPREAD_HINTS = {
  idle: "选择牌阵，写下一个具体的问题，再点「洗牌抽牌」。",
  picking: "",
  waiting: "牌已选定，正在静候牌意……",
  open: "这一轮还没抽出牌。请在对话窗回复知命，所选的牌会沿用；想换牌请点「重新起问」。",
  reveal: "轻触牌面逐张翻开，或点「全部翻开」。",
  done: "追问请在对话窗；想换一组牌，请点「重新起问」。",
};

function drawnCards() {
  return currentReading?.tarot?.cards || [];
}

function updateTarot() {
  const size = SPREAD_POSITIONS[spread].length;
  const step = { idle: 2, picking: 3, waiting: 4, open: 4, reveal: 4, done: 5 }[tarotPhase];
  $$("#tarot-steps li").forEach((item) => {
    const index = Number(item.dataset.step);
    item.classList.toggle("done", index < step);
    item.classList.toggle("current", index === step);
  });
  $$("[data-spread]").forEach((choice) => {
    choice.setAttribute("aria-pressed", String(choice.dataset.spread === spread));
  });
  $("#tarot-question").readOnly = tarotPhase !== "idle";
  $("#tarot-begin").hidden = tarotPhase !== "idle";
  $("#tarot-deck").hidden = tarotPhase !== "picking";
  $("#spread-hint").textContent = SPREAD_HINTS[tarotPhase];
  const hint = $("#deck-hint");
  hint.replaceChildren(
    document.createTextNode(`默念你的问题，凭直觉从牌堆中选出 ${size} 张 · 已选 `),
    node("b", "", `${picked.length} / ${size}`),
  );
  const unturned = tarotPhase === "reveal" && flipped.size < drawnCards().length;
  $("#flip-all").hidden = !unturned;
  $("#tarot-lower").classList.toggle("veiled", unturned);
  $("#reading-veil").hidden = !unturned;
  $("#reading-content").toggleAttribute("aria-hidden", unturned);
  $("#message").placeholder =
    tarotPhase === "open"
      ? "在这里回复知命，所选的牌会沿用"
      : drawnCards().length
        ? "就这组牌继续追问，比如：这张牌在提醒我什么？"
        : "抽牌之后，可在这里就这组牌追问";
}

function buildDeck() {
  const fan = $("#deck-fan");
  fan.setAttribute("aria-label", `${DECK_SIZE} 张背面朝上的牌`);
  fan.replaceChildren();
  for (let index = 0; index < DECK_SIZE; index++) {
    const card = button("", "deck-card");
    card.style.setProperty("--i", String(index));
    card.setAttribute("aria-label", `第 ${index + 1} 张`);
    card.addEventListener("click", () => pickCard(index, card));
    fan.append(card);
  }
  // Gather the deck in the middle, then let it fan out: a short shuffle.
  fan.classList.add("gathered");
  requestAnimationFrame(() => requestAnimationFrame(() => fan.classList.remove("gathered")));
}

function beginPicking() {
  if (busy || !state || tarotPhase !== "idle") return;
  if (!$("#tarot-question").value.trim()) {
    toast("先写下一个具体的问题。");
    $("#tarot-question").focus();
    return;
  }
  tarotPhase = "picking";
  picked = [];
  buildDeck();
  renderSpread(null);
  $("#tarot-deck").scrollIntoView({ behavior: "smooth", block: "center" });
}

function pickCard(index, card) {
  const size = SPREAD_POSITIONS[spread].length;
  if (busy || tarotPhase !== "picking" || picked.length >= size) return;
  picked.push(index);
  // Fixed now, not when the animation ends: quick taps must not send the draw twice, and a
  // round reset during the flight must neither send nor read the next round's state.
  const draw =
    picked.length === size
      ? { message: $("#tarot-question").value.trim(), spread, picks: [...picked] }
      : null;
  const round = tarotRound;
  const target = $$("#tarot-spread .card-face")[picked.length - 1];
  const from = card.getBoundingClientRect();
  card.classList.add("taken");
  card.disabled = true;
  const done = () => {
    if (round !== tarotRound) return;
    renderSpread(null);
    if (draw) drawCards(draw);
  };
  if (!target || matchMedia("(prefers-reduced-motion: reduce)").matches) return done();
  // Fly a copy of the chosen card down into its slot.
  const to = target.getBoundingClientRect();
  const flyer = node("span", "deck-card deck-flyer");
  flyer.style.left = `${from.left}px`;
  flyer.style.top = `${from.top}px`;
  flyer.style.width = `${from.width}px`;
  flyer.style.height = `${from.height}px`;
  document.body.append(flyer);
  const flight = flyer.animate(
    [
      { transform: "translate(0, 0) scale(1)", opacity: 1 },
      {
        transform: `translate(${to.left - from.left}px, ${to.top - from.top}px) scale(${to.width / from.width}, ${to.height / from.height})`,
        opacity: 1,
      },
    ],
    { duration: 520, easing: "cubic-bezier(.2,.8,.2,1)" },
  );
  flights.add(flight);
  flight.finished
    .then(done, () => {}) // a cancelled flight belongs to a round that was reset
    .finally(() => {
      flights.delete(flight);
      flyer.remove();
    });
  updateTarot();
}

function drawCards(draw) {
  pendingDraw = draw;
  tarotPhase = "waiting";
  renderSpread(null);
  // The server shuffles the deck face down; these positions decide which cards are dealt.
  return send(
    { message: draw.message, extra: { spread: draw.spread, picks: draw.picks } },
    state.birth,
  );
}

function resetTarot() {
  tarotRound += 1;
  flights.forEach((flight) => flight.cancel());
  flights.clear();
  tarotPhase = "idle";
  picked = [];
  flipped = new Set();
  drawnKey = "";
  pendingDraw = null;
  $("#deck-fan").replaceChildren();
}

// Every way to a new session (重新起问, 开启新对话, switching mode, clearing records) ends the
// round before the request, so nothing from it can still be sent. An unsent question set aside
// while looking at a record comes back, unless the records themselves are being cleared.
function newTarotSession({ forget = false } = {}) {
  resetTarot();
  $("#tarot-question").value = forget ? "" : questionDraft || "";
  questionDraft = null;
  updateTarot(); // the slots follow when the new session's state arrives
}

// The reply came back without cards: keep the round so the next message continues it.
function openRound() {
  tarotPhase = "open";
  renderSpread(null);
  if (state?.messages?.at(-1)?.status === "ask_user")
    toast("知命想先确认一些信息，请在对话窗回复；所选的牌会沿用。");
}

// After a reload the round lives only on the server: take its question, spread and positions
// back, waiting if the reply is still being written, open otherwise.
function restoreRound(round, waiting) {
  resetTarot();
  spread = round.spread;
  picked = [...round.picks];
  pendingDraw = { message: round.question, spread: round.spread, picks: [...round.picks] };
  $("#tarot-question").value = round.question;
  tarotPhase = waiting ? "waiting" : "open";
  renderSpread(null);
}

function flipCard(index) {
  const flip = $$("#tarot-spread .flip-card")[index];
  if (!flip || flipped.has(index)) return;
  const card = drawnCards()[index];
  flipped.add(index);
  flip.classList.add("is-flipped");
  flip.disabled = true;
  flip.setAttribute("aria-label", `${card.label}：${card.name}，${card.reversed ? "逆位" : "正位"}`);
  $$("#tarot-spread .tarot-orientation")[index].textContent = card.reversed ? "逆位" : "正位";
  if (flipped.size === drawnCards().length) {
    tarotPhase = "done";
    toast("牌面已全部翻开，牌意整理在下方。");
    const round = tarotRound;
    setTimeout(() => {
      if (round === tarotRound && tarotPhase === "done") linkSpread();
    }, 280);
  }
  updateTarot();
  const content = $("#reading-content");
  if (tarotPhase === "done" && content?.dataset.pendingFresh) {
    delete content.dataset.pendingFresh;
    replay(content, "is-fresh");
  }
}

// The spread is joined by gold lines once every card is face up: a moment, not a fixture.
function linkSpread() {
  const box = $("#tarot-spread");
  const cards = $$("#tarot-spread .flip-card");
  if (!box || cards.length < 2 || REDUCED_MOTION.matches) return;
  $("#spread-links")?.remove();
  const frame = box.getBoundingClientRect();
  // Knots sit just above each arched frame; arcs rise between them, so no card face is crossed.
  const points = cards.map((card) => {
    const r = card.getBoundingClientRect();
    return [r.left - frame.left + r.width / 2, r.top - frame.top - 8];
  });
  const svg = svgNode("svg", {
    id: "spread-links",
    class: "spread-links",
    viewBox: `0 0 ${frame.width.toFixed(0)} ${frame.height.toFixed(0)}`,
    "aria-hidden": "true",
  });
  let arcIndex = 0;
  points.slice(1).forEach(([x, y], index) => {
    const [x0, y0] = points[index];
    // On narrow screens where cards wrap to another row, skip cross-row arcs so no card face is crossed.
    if (Math.abs(y - y0) > 24) return;
    const lift = Math.min(22, Math.abs(x - x0) * 0.12);
    const arc = svgNode("path", {
      class: "spread-arc",
      d: `M${x0.toFixed(1)} ${y0.toFixed(1)} Q${((x0 + x) / 2).toFixed(1)} ${(Math.min(y0, y) - lift).toFixed(1)} ${x.toFixed(1)} ${y.toFixed(1)}`,
    });
    arc.style.setProperty("--i", String(arcIndex++));
    svg.append(arc);
  });
  points.forEach(([x, y], index) => {
    const knot = svgNode("path", {
      class: "spread-knot",
      d: `M${x} ${y - 6} L${x + 6} ${y} L${x} ${y + 6} L${x - 6} ${y} Z`,
    });
    knot.style.setProperty("--i", String(index));
    svg.append(knot);
  });
  box.append(svg);
  svg.querySelectorAll(".spread-arc").forEach((arc) =>
    arc.style.setProperty("--len", String(Math.ceil(arc.getTotalLength()))));
  setTimeout(() => svg.remove(), 4200);
}

// Called on every render of the reading: this round's draw waits face down; a record shown
// from 足迹 or restored on load is face up, with its own question.
function onTarotReading(reading) {
  const cards = reading?.tarot?.cards || [];
  if (cards.length) {
    const key = `${reading.tarot.seed}:${cards.map((card) => card.card_id).join(",")}`;
    if (key !== drawnKey) {
      if (tarotPhase === "waiting" && reading.reading_id === state?.reading?.reading_id) {
        // The answer to this round: the question typed above is the one these cards answer.
        tarotPhase = "reveal";
        flipped = new Set();
      } else {
        const typed = $("#tarot-question").value.trim();
        if (tarotPhase !== "reveal" && tarotPhase !== "done" && typed && questionDraft === null)
          questionDraft = typed;
        resetTarot();
        tarotPhase = "done";
        flipped = new Set(cards.map((_, index) => index));
        // The same text the 足迹 list shows for this record.
        $("#tarot-question").value = (reading.question || reading.tarot.question || "").split("\n")[0];
      }
      drawnKey = key;
      spread = reading.tarot.spread || spread;
    }
  }
  renderSpread(reading);
}

function renderSpread(reading) {
  const cards = reading?.tarot?.cards || drawnCards();
  const box = $("#tarot-spread");
  box.replaceChildren();
  const positions = cards.length ? cards.map((card) => card.label) : SPREAD_POSITIONS[spread];
  positions.forEach((position, index) => {
    const card = cards[index];
    const slot = node("article", "tarot-slot");
    let status = "静待抽牌";
    if (card) {
      const open = flipped.has(index);
      const flip = button("", open ? "flip-card is-flipped" : "flip-card");
      const inner = node("span", "flip-inner");
      const back = cardBack();
      back.append(node("span", "tarot-tap", "轻触翻牌"));
      inner.append(back, cardFace(card));
      flip.append(inner);
      flip.disabled = open;
      flip.setAttribute(
        "aria-label",
        open ? `${position}：${card.name}，${card.reversed ? "逆位" : "正位"}` : `翻开第 ${index + 1} 张：${position}`,
      );
      flip.addEventListener("click", () => flipCard(index));
      slot.append(flip);
      status = open ? (card.reversed ? "逆位" : "正位") : "未翻开";
    } else if (index < picked.length) {
      slot.classList.add(tarotPhase === "waiting" ? "is-waiting" : "is-picked");
      slot.append(cardBack());
      status = tarotPhase === "waiting" ? "牌意正在浮现" : "已选";
    } else {
      if (tarotPhase === "picking" && index === picked.length) slot.classList.add("is-next");
      slot.append(node("span", "card-face card-empty"));
      status = tarotPhase === "picking" ? (index === picked.length ? "下一张落在这里" : "待选") : "静待抽牌";
    }
    slot.setAttribute("aria-label", `${position}：${status}`);
    const caption = node("div", "tarot-caption");
    caption.append(
      node("span", "tarot-position", `${ROMAN[index + 1]} · ${position}`),
      node("span", "tarot-orientation", status),
    );
    slot.append(caption);
    box.append(slot);
  });
  updateTarot();
}

/* ---------- 姓名 ---------- */

let nameResult = null;
let nameForms = {};
let nameChoices = [];
let nameRevealTimer = null;

function restoreName(saved) {
  nameForms = saved?.forms || {};
  nameChoices = saved?.choices || [];
  $("#name-surname").value = saved?.result.surname || "";
  $("#name-given").value = saved?.result.given || "";
  $("#name-feedback").textContent = saved
    ? `“${saved.result.full_name}”已按康熙笔画推演。`
    : "复姓请把两个字都填在“姓”里。";
  renderName(saved?.result || null);
}

function elementOfNumber(number) {
  return ELEMENTS[Math.floor(((number - 1) % 10) / 2)];
}

function pairText(first, second, relation) {
  return (
    {
      生: `${first}生${second}`,
      被生: `${second}生${first}`,
      克: `${first}克${second}`,
      被克: `${second}克${first}`,
      同: `${first}${second}比和`,
    }[relation] || ""
  );
}

function bracketLabel(grid, number) {
  const label = node("div", "wuge-label");
  label.append(node("span", "wuge-name", grid), node("span", "wuge-number", String(number)), elementTag(elementOfNumber(number)));
  return label;
}

function placeInGrid(element, rows, columns) {
  element.style.gridRow = rows;
  element.style.gridColumn = columns;
  return element;
}

function renderWuge(result) {
  const box = $("#wuge");
  box.replaceChildren();
  const surname = result.chars.filter((c) => c.role === "surname");
  const given = result.chars.filter((c) => c.role === "given");
  const cells = [
    ...(surname.length === 1 ? [null] : []),
    ...surname,
    ...given,
    ...(given.length === 1 ? [null] : []),
  ];
  box.style.gridTemplateRows = `repeat(${cells.length * 2}, 50px) auto`;
  cells.forEach((cell, index) => {
    const tile = node("div", cell ? "wuge-cell" : "wuge-cell wuge-fake");
    if (cell) tile.append(node("span", "wuge-char", cell.form), node("span", "wuge-strokes", String(cell.strokes)));
    else tile.append(node("span", "wuge-char", "一"), node("span", "wuge-strokes", "假数"));
    box.append(placeInGrid(tile, `${index * 2 + 1} / ${index * 2 + 3}`, "4"));
  });
  const center = (k) => 2 * k; // grid line through the middle of the k-th (1-based) cell
  const lastSurname = cells.indexOf(surname.at(-1)) + 1;
  const spans = [
    ["天格", 1, 2, "3", "wuge-bracket left"],
    ["人格", lastSurname, lastSurname + 1, "2 / 4", "wuge-bracket left"],
    ["地格", lastSurname + 1, cells.length, "3", "wuge-bracket left"],
  ];
  for (const [grid, from, to, columns, className] of spans) {
    const rows = `${center(from)} / ${center(to)}`;
    box.append(placeInGrid(node("div", className), rows, columns));
    box.append(placeInGrid(bracketLabel(grid, result.grids[grid]), rows, "1"));
  }
  const outer = `${center(1)} / ${center(cells.length)}`;
  box.append(placeInGrid(node("div", "wuge-bracket right"), outer, "5"));
  const outerLabel = bracketLabel("外格", result.grids["外格"]);
  outerLabel.classList.add("right");
  outerLabel.append(node("span", "wuge-formula", "天格 ＋ 地格 − 人格"));
  box.append(placeInGrid(outerLabel, outer, "6"));
  const total = node("div", "wuge-total");
  total.append(
    node("span", "wuge-name", "总格"),
    node("span", "wuge-number", String(result.grids["总格"])),
    elementTag(elementOfNumber(result.grids["总格"])),
    node("span", "wuge-formula", result.chars.map((c) => c.strokes).join(" ＋ ")),
  );
  box.append(placeInGrid(total, String(cells.length * 2 + 1), "1 / -1"));
}

function renderName(result, fresh = false) {
  nameResult = result;
  $("#name-empty").hidden = Boolean(result);
  $("#name-board").hidden = !result;
  if (!result) return;
  const chars = $("#name-chars");
  chars.replaceChildren();
  for (const char of result.chars) {
    const tile = node("article", "stele");
    const glyph = node("div", "stele-glyph", char.form);
    glyph.setAttribute("aria-hidden", "true");
    const info = node("div", "stele-info");
    info.append(
      node("span", "stele-role", `${char.role === "surname" ? "姓" : "名"} · ${char.char}`),
      node("span", "stele-strokes", `${cnNumber(char.strokes)}画`),
      node("span", "stele-rule", char.rules?.join("；") || (char.form === char.char ? "康熙字形与常用字形相同" : `按繁体“${char.form}”计`)),
    );
    tile.setAttribute("aria-label", `${char.char}，康熙字形${char.form}，${char.strokes}画`);
    tile.append(glyph, info);
    chars.append(tile);
  }
  renderWuge(result);
  const sancai = result.sancai;
  const [heaven, person, earth] = ["天格", "人格", "地格"].map((grid) => sancai.elements[grid]);
  const flow = $("#sancai-flow");
  flow.replaceChildren();
  [
    ["天", heaven],
    null,
    ["人", person],
    null,
    ["地", earth],
  ].forEach((item, index) => {
    if (item) {
      const talent = node("div", "talent");
      talent.append(elementTag(item[1], "talent-element"), node("span", "talent-name", item[0]));
      flow.append(talent);
    } else {
      const link = node("div", "talent-link");
      link.append(
        node("span", "", index === 1 ? pairText(heaven, person, sancai.heaven_to_person) : pairText(person, earth, sancai.person_to_earth)),
      );
      flow.append(link);
    }
  });
  $("#sancai-note").textContent = result.conventions?.school || "";
  renderNameChoices();
  clearTimeout(nameRevealTimer);
  const board = $("#name-board");
  const wuge = $("#wuge");
  if (fresh && !REDUCED_MOTION.matches) {
    $$("#name-chars .stele").forEach((stele, index) => stele.style.setProperty("--i", String(index)));
    // The count-up is drawn by CSS over the real number, which never changes in the DOM.
    const canCount = typeof CSS !== "undefined" && typeof CSS.registerProperty === "function";
    wuge.classList.toggle("is-counting", canCount);
    if (canCount) {
      $$("#wuge .wuge-number").forEach((number, index) => {
        number.style.setProperty("--target", number.textContent);
        number.style.setProperty("--i", String(index));
      });
    }
    $$("#sancai-flow > *").forEach((item, index) => item.style.setProperty("--i", String(index)));
    replay(board, "is-revealing");
    nameRevealTimer = setTimeout(() => {
      board.classList.remove("is-revealing");
      wuge.classList.remove("is-counting");
    }, 2500);
  } else {
    board.classList.remove("is-revealing");
    wuge.classList.remove("is-counting");
  }
}

function renderNameChoices() {
  const box = $("#name-forms");
  box.replaceChildren();
  box.hidden = !nameChoices.length;
  for (const choice of nameChoices) {
    const fieldset = node("fieldset", "form-choice");
    fieldset.append(node("legend", "", `“${choice.char}”有多种写法，请按你的实际写法选择`));
    const chosen = nameForms[choice.char] || choice.default.form;
    for (const option of [{ ...choice.default, default: true }, ...choice.alternatives]) {
      const label = node("label", "check");
      const radio = node("input");
      radio.type = "radio";
      radio.name = `form-${choice.char}`;
      radio.value = option.form;
      radio.checked = option.form === chosen;
      radio.dataset.lock = "";
      radio.addEventListener("change", () => {
        if (option.form === choice.default.form) delete nameForms[choice.char];
        else nameForms[choice.char] = option.form;
        runName(false);
      });
      label.append(radio, document.createTextNode(`${option.form}（${option.strokes} 画${option.default ? "，默认" : ""}）`));
      fieldset.append(label);
    }
    box.append(fieldset);
  }
}

async function runName(fresh = true) {
  const surname = $("#name-surname").value.trim();
  const given = $("#name-given").value.trim();
  if (!surname || !given) {
    toast("请分别填写姓和名。");
    return;
  }
  if (fresh) {
    nameForms = {};
    nameChoices = [];
  }
  try {
    const data = await api("/api/name", {
      method: "POST",
      body: JSON.stringify({ surname, given, forms: nameForms }),
    });
    if (!data.result) {
      $("#name-feedback").textContent = data.question;
      toast(data.question);
      return;
    }
    if (fresh) nameChoices = data.result.ambiguities;
    state.name_analysis = { result: data.result, forms: { ...nameForms }, choices: nameChoices };
    $("#name-feedback").textContent = `“${surname}${given}”已按康熙笔画推演。`;
    renderName(data.result, true);
  } catch (error) {
    $("#name-feedback").textContent = error.message;
    toast(error.message);
  }
}

/* ---------- 解梦 ---------- */

function renderDream(reading, fresh = false) {
  const results = calculations(reading, "dream_result:");
  const list = $("#dream-symbols");
  list.replaceChildren();
  const hits = results.flatMap((result) => result.hits || []);
  const meanings = results.flatMap((result) => result.interpretations || []);
  const misses = [...new Set(results.flatMap((result) => result.misses || []))];
  $("#dream-count").textContent = results.length ? `识别到 ${meanings.length} 个` : "";
  if (!results.length) {
    list.append(node("p", "symbols-empty", "解梦之后，这里会列出梦中被识别的意象，以及它们通常映照的心绪。"));
    return;
  }
  for (const meaning of meanings) {
    const hit = hits.find((item) => item.key === meaning.key);
    const item = node("article", "symbol");
    const glyph = node("span", "symbol-glyph", meaning.key.slice(-1));
    glyph.setAttribute("aria-hidden", "true");
    const body = node("div", "symbol-body");
    const head = node("div", "symbol-head");
    head.append(node("h3", "", meaning.key));
    if (meaning.meaning?.keywords?.length) head.append(node("span", "symbol-tag", meaning.meaning.keywords.slice(0, 3).join(" · ")));
    if (hit?.phrase) head.append(node("span", "symbol-source", `原文「${hit.phrase}」`));
    body.append(head, node("p", "", meaning.meaning?.text || ""));
    item.append(glyph, body);
    list.append(item);
  }
  if (misses.length)
    list.append(node("p", "symbols-miss", `未收录的意象：${misses.join("、")}。词典外的内容不作解读。`));
  if (fresh) {
    $$("#dream-symbols .symbol").forEach((item, index) => item.style.setProperty("--i", String(index)));
    replay(list, "is-arriving");
    replay($(".butterfly"), "is-beating");
  }
}

function renderDiary(history) {
  const list = $("#dream-diary");
  list.replaceChildren();
  const dreams = history.filter((item) => (item.systems_used || []).includes("dream"));
  if (!dreams.length) {
    list.append(node("p", "diary-empty", "解过的梦会按日期留在这里，方便日后回看。"));
    return;
  }
  dreams.slice(0, 6).forEach((item) => list.append(historyButton(item, "diary-item")));
}

/* ---------- 运势 ---------- */

let almanacDay = null;
let almanacBirthVersion = null;
let almanacRequest = 0;
const BODY_ZH = {
  Sun: "太阳",
  Moon: "月亮",
  Mercury: "水星",
  Venus: "金星",
  Mars: "火星",
  Jupiter: "木星",
  Saturn: "土星",
  Uranus: "天王星",
  Neptune: "海王星",
  Pluto: "冥王星",
};

function birthForAlmanac() {
  return $("#birth-form") && state ? birthInfo() : state?.birth || {};
}

async function loadAlmanac(date, birth = birthForAlmanac()) {
  const request = ++almanacRequest;
  const version = state?.birth_version;
  try {
    const data = await api("/api/almanac", {
      method: "POST",
      body: JSON.stringify({ date: date || null, birth }),
    });
    if (request === almanacRequest && version === state?.birth_version) renderAlmanac(data);
  } catch (error) {
    if (request === almanacRequest && version === state?.birth_version) toast(error.message);
  }
}

function renderAlmanac(data) {
  const turning = almanacDay !== null && almanacDay !== data.date;
  // Not on the first render of the page: only a new day, or a ten god that just became known.
  const stamping = Boolean(data.ten_god) && almanacDay !== null
    && (turning || $("#day-god").textContent !== data.ten_god);
  almanacDay = data.date;
  const [year, month, day] = data.date.split("-").map(Number);
  $("#day-num").textContent = String(day);
  $("#day-month").textContent = `${year} · ${month} 月`;
  $("#day-weekday").textContent = `星期${data.weekday}${data.date === shanghaiToday() ? " · 今日" : ""}`;
  $("#day-pillars").textContent = `${data.year_pillar}年 ${data.month_pillar}月 ${data.day_pillar}日`;
  $("#day-lunar").textContent = `农历${data.lunar_date}`;
  $("#day-term").textContent = `${data.hou} · ${data.wuhou}${data.term ? ` · 今日${data.term}` : ` · ${data.next_term.date.slice(5).replace("-", "月")}日${data.next_term.name}`}`;
  $("#day-pick").value = data.date;
  $("#day-god").textContent = data.ten_god || "—";
  $("#day-god-note").textContent = data.ten_god
    ? `${data.day_pillar[0]}${elementOf(data.day_pillar[0])}对日主${data.day_master}`
    : data.question || "确认出生日期与地点后，按你的日主推算";
  $("#day-element").textContent = `${data.day_element}`;
  $("#day-element").dataset.element = data.day_element;
  $("#day-element-note").textContent = data.day_element_note || "";
  const week = $("#week");
  week.replaceChildren();
  for (const item of data.week) {
    const cell = button("", "week-day");
    if (item.date === data.date) cell.setAttribute("aria-current", "date");
    cell.dataset.lock = "";
    cell.disabled = busy;
    cell.append(
      node("span", "week-label", `${item.weekday}${item.term ? " · " + item.term : ""}`),
      node("span", "week-num", String(Number(item.date.slice(8)))),
      node("span", "week-gz", item.day_pillar),
      node("span", "week-god", item.ten_god || "　"),
    );
    cell.addEventListener("click", () => loadAlmanac(item.date));
    week.append(cell);
  }
  if (turning) replay($(".almanac-center"), "is-turning");
  if (stamping) replay($("#day-god"), "is-stamped");
}

function renderDaily(reading) {
  const result = reading?.calculations?.daily_result;
  const card = $("#day-card");
  const transits = $("#day-transits");
  card.replaceChildren();
  transits.replaceChildren();
  if (!result) {
    card.append(node("span", "cell-value muted", "看今日详解后显示"), node("span", "cell-note", "每日一牌按日期固定，同一天不会变"));
    transits.append(node("span", "cell-value muted", "看今日详解后显示"), node("span", "cell-note", "月亮与快行星对本命的精确相位"));
    return;
  }
  card.append(
    node("span", "cell-value", `${result.card.name} · ${result.card.reversed ? "逆位" : "正位"}`),
    node("span", "cell-note", `${result.date} 的每日一牌`),
  );
  if (!result.events?.length) transits.append(node("span", "cell-value", "当日无精确相位"));
  for (const event of (result.events || []).slice(0, 3)) {
    const time = new Date(event.exact_utc).toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: result.tz,
    });
    const line = node("span", "cell-value");
    line.append(
      document.createTextNode(`${BODY_ZH[event.transit_body] || event.transit_body} `),
      node("b", "", ASPECT_NAMES[event.aspect] || event.aspect),
      document.createTextNode(` 本命${BODY_ZH[event.natal_body] || event.natal_body}`),
    );
    transits.append(line, node("span", "cell-note", `约 ${time} 精确`));
  }
}

/* ---------- Page modules ---------- */

const PAGES = {
  ask: {
    onState(next, first) {
      renderProfile(next.birth, !first && !$("#birth-details").hidden);
      refreshAskAlmanac(next.birth, first);
    },
    onHistory: renderRecent,
    onBirthSaved(birth) {
      renderProfile(birth, false);
      refreshAskAlmanac(birth, true);
    },
    // There is no dialogue here: a reading shows only when a record is opened from 足迹.
    onReading(reading) {
      $("#reading").hidden = !reading;
    },
    init() {
      renderAskVisuals();
      $("#hero-enroll").addEventListener("click", (event) => {
        event.preventDefault();
        $("#enroll").scrollIntoView({ behavior: "smooth", block: "start" });
        if (!$("#birth-details").hidden) {
          ($("#birth-year") || $("#birth-date"))?.focus({ preventScroll: true });
        }
      });
      $("#edit-birth").addEventListener("click", () => {
        const editing = $("#birth-details").hidden;
        renderProfile(state.birth, editing);
        if (editing) ($("#birth-year") || $("#birth-date"))?.focus();
      });
      $("#close-reading").addEventListener("click", () => renderReading(null));
    },
  },
  bazi: {
    thinking: "正在依四柱推演……",
    onState(next, first, background) {
      renderBazi(next.chart, first || background);
    },
    onChart(chart, silent = false) {
      renderBazi(chart, silent);
    },
    init() {
      renderBazi(null, true);
    },
  },
  astro: {
    thinking: "正在仰观星图……",
    onState(next, first, background) {
      renderAstro(next.chart, first || background);
    },
    onChart(chart, silent = false) {
      renderAstro(chart, silent);
    },
    init() {
      renderAstro(null, true);
    },
  },
  tarot: {
    thinking: "正在洗牌、静候牌意……",
    hint: "Enter 发送 · 塔罗不需要出生资料",
    init() {
      $$("[data-spread]").forEach((choice) =>
        choice.addEventListener("click", () => {
          if (tarotPhase !== "idle") {
            toast("这一轮已经开始抽牌。想换牌阵，请先点「重新起问」。");
            return;
          }
          spread = choice.dataset.spread;
          renderSpread(null);
        }),
      );
      $("#tarot-form").addEventListener("submit", (event) => {
        event.preventDefault();
        beginPicking();
      });
      $("#flip-all").addEventListener("click", () =>
        drawnCards().forEach((_, index) => setTimeout(() => flipCard(index), index * 260)),
      );
      $("#new-question").addEventListener("click", () => startNew(state.provider));
      renderSpread(null);
    },
    onNewSession: newTarotSession,
    // Before a draw, the dialogue box and the suggestions feed the question above the deck.
    compose(text) {
      if (tarotPhase === "open") {
        if (!text) return null;
        // Continue the same round: the reply goes as is, with the spread and positions chosen.
        tarotPhase = "waiting";
        renderSpread(null);
        return { message: text, extra: { spread: pendingDraw.spread, picks: pendingDraw.picks } };
      }
      if (drawnCards().length) return text ? { message: text } : null;
      if (tarotPhase !== "idle") {
        toast("请先从牌堆中选完牌。");
        return null;
      }
      if (text) $("#tarot-question").value = text;
      $("#message").value = "";
      fitComposer();
      beginPicking();
      return null;
    },
    draft(question) {
      if (drawnCards().length || tarotPhase === "open") return false;
      if (tarotPhase === "idle") $("#tarot-question").value = question;
      $("#tarot-form").scrollIntoView({ behavior: "smooth", block: "center" });
      $("#tarot-question").focus({ preventScroll: true });
      return true;
    },
    onFab() {
      if (drawnCards().length || tarotPhase === "open") return false;
      $(tarotPhase === "picking" ? "#tarot-deck" : "#tarot-form").scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
      if (tarotPhase === "idle") $("#tarot-question").focus({ preventScroll: true });
      return true;
    },
    onAnswered() {
      if (tarotPhase !== "reveal") return false;
      toast("牌已就位，轻触牌面逐张翻开。");
      $("#tarot-spread").scrollIntoView({ behavior: "smooth", block: "center" });
      return true;
    },
    onSendFailed() {
      if (tarotPhase === "waiting") openRound();
    },
    onState(next, first) {
      if (drawnCards().length) return;
      if (first && next.tarot_round) restoreRound(next.tarot_round, next.busy);
      else if (tarotPhase === "waiting" && !next.busy) openRound();
    },
    onReading: onTarotReading,
  },
  name: {
    hint: "Enter 发送 · 会连同上方姓名一起解读",
    onState(next, first) {
      if (first && next.name_analysis) restoreName(next.name_analysis);
      else if (!next.name_analysis && !next.reading) restoreName(null);
    },
    init() {
      $("#name-form").addEventListener("submit", (event) => {
        event.preventDefault();
        runName();
      });
      renderName(null);
    },
    compose(text) {
      if (!nameResult) {
        toast("请先填写姓名并点「推演」。");
        return null;
      }
      const { surname, given } = nameResult;
      const forms = Object.entries(nameForms).map(([char, form]) =>
        form === char ? `“${char}”按原字计算。` : `“${char}”写作“${form}”。`,
      );
      return {
        message: [
          `我的姓名是“${surname}${given}”：姓“${surname}”${surname.length === 2 ? "（复姓）" : "（单姓）"}，名“${given}”。${forms.join("")}`,
          text || "请解读这个名字的五格数理与三才。",
        ].join("\n"),
      };
    },
    onReading(reading) {
      const saved = calculations(reading, "name_result:").find((item) => item.status === "ok");
      if (saved && !nameResult) {
        $("#name-surname").value = saved.surname;
        $("#name-given").value = saved.given;
        renderName(saved);
      }
    },
  },
  dream: {
    thinking: "正在细读梦里的意象……",
    hint: "Ctrl + Enter 发送 · Enter 换行",
    init() {
      $("#paper-date").textContent = new Date().toLocaleDateString("en-US", {
        month: "short",
        day: "2-digit",
        timeZone: "Asia/Shanghai",
      });
    },
    compose(text) {
      if (!text) {
        toast("先写下还记得的梦境画面。");
        return null;
      }
      const mood = $("input[name='mood']:checked")?.value;
      return { message: mood ? `${text}\n醒来时的感受：${mood}` : text };
    },
    onReading: renderDream,
    onHistory: renderDiary,
  },
  daily: {
    thinking: "正在推算流日……",
    hint: "Enter 发送 · 问题按上方所选日期解读",
    init() {
      $("#day-prev").addEventListener("click", () => shiftDay(-1));
      $("#day-next").addEventListener("click", () => shiftDay(1));
      $("#day-pick").addEventListener("change", (event) => {
        if (event.target.value) loadAlmanac(event.target.value);
      });
      $("#daily-ask").addEventListener("click", () => {
        if (busy || !state || !validateBirth()) return;
        const birth = birthInfo();
        if (!birth.date || !birth.location_id) {
          toast("请先在上方「生辰」中填写出生日期与出生地点。");
          openBirthFold();
          return;
        }
        const label = almanacDay === shanghaiToday() ? `今天（${chineseDate(almanacDay)}）` : chineseDate(almanacDay);
        send({ message: `请看看我${label}的运势。` }, birth);
      });
      renderDaily(null);
    },
    onState(next, first) {
      // The form's location is still being restored on first load; use the saved profile.
      if (first || next.birth_version !== almanacBirthVersion) {
        almanacBirthVersion = next.birth_version;
        loadAlmanac(first ? null : almanacDay, next.birth);
      }
    },
    compose(text) {
      if (!text) return null;
      return { message: `${text}\n咨询日期：${chineseDate(almanacDay || shanghaiToday())}` };
    },
    onReading: renderDaily,
  },
};

function shiftDay(offset) {
  if (!almanacDay) return;
  const date = new Date(`${almanacDay}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  loadAlmanac(date.toISOString().slice(0, 10));
}

/* ---------- Start ---------- */

function init() {
  page = PAGES[PAGE] || {};
  injectChrome();
  emptyReading = $("#reading-content")?.cloneNode(true) || null;
  const host = $("[data-birth]");
  if (host) buildBirthForm(host, host.dataset.birth);
  $("[data-birth-submit]")?.addEventListener("click", submitBirthFromBar);
  wireControls();
  window.addEventListener("focus", () => { if (state && !busy) refresh(); });
  // Last line of defence: an unexpected script error still tells the person what to do.
  window.addEventListener("error", (event) => {
    if (event.error) toast("页面出现意外错误，请刷新后重试。");
  });
  window.addEventListener("unhandledrejection", (event) => {
    // Errors raised by api() already read as plain Chinese; anything else stays generic.
    const reason = event.reason;
    toast(reason?.status ? reason.message : "页面出现意外错误，请刷新后重试。");
  });
  window.addEventListener("offline", () => toast("网络已断开，恢复连接后再继续。"));
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && state && !busy) refresh();
  });
  if (birthChannel) birthChannel.onmessage = (event) => {
    if (state && !busy && event.data?.birth_version !== state.birth_version) refresh();
  };
  initComposer();
  $$('a[href^="#"]').forEach((link) => {
    if (document.getElementById(link.hash.slice(1))?.matches("[data-birth-fold]"))
      link.addEventListener("click", (event) => {
        event.preventDefault();
        openBirthFold();
      });
  });
  page.init?.();
  setBusy(true);
  if (host) locationsReady = initLocations().catch((error) => toast(error.message));
  const params = new URLSearchParams(location.search);
  const wanted = params.get("provider");
  if (wanted) history.replaceState(null, "", location.pathname + location.hash);
  api(`/api/session?provider=${wanted === "demo" ? "demo" : "configured"}`)
    .then(async (next) => {
      applyState(next, true);
      const notice = takeNotice();
      if (notice) toast(notice);
      else if (!next.account && remembered("zhiming.account")) sessionExpired();
      if ((wanted === "demo" || wanted === "configured") && next.provider !== wanted)
        startNew(wanted);
      if (params.get("reading_id") && $("#chat-form")) {
        const reading = await api(`/api/readings/${encodeURIComponent(params.get("reading_id"))}`);
        followupReadingId = reading.reading_id;
        renderReading(reading);
        toast("后续问题已绑定所选历史解读。");
      }
    })
    .catch((error) => {
      const status = $("#connection");
      if (status) {
        status.textContent = "连接未就绪";
        status.classList.add("offline");
      }
      $$("[data-live]").forEach((live) => {
        live.textContent = "连接未就绪";
      });
      if ($("#input-hint")) $("#input-hint").textContent = "服务未就绪，可切换离线演示或刷新重试";
      if ($("#provider")) $("#provider").disabled = false;
      toast(error.message);
    });
}

init();
