"use strict";

const $ = (selector) => document.querySelector(selector);
const names = {
  auto: "综合解读",
  bazi: "八字命理",
  astro: "星象观察",
  tarot: "塔罗问心",
};
const welcome = $("#welcome").cloneNode(true);
const emptyReading = $("#reading-content").cloneNode(true);
let state = null;
let system = "auto";
try {
  const savedTheme = sessionStorage.getItem("zhiming-theme");
  if (Object.hasOwn(names, savedTheme)) system = savedTheme;
} catch {
  /* Private browsing can disable browser storage. */
}
let busy = false;
let currentReading = null;
let toastTimer;
let refreshTimer;
let selectedLocation = null;
let locationVersion = 0;
let locationLoading = false;
let spread = "three_card";
const locationFields = ["country", "province", "city", "district"];
const themes = window.ZhimingThemes;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function toast(message) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  toastTimer = setTimeout(() => {
    $("#toast").hidden = true;
  }, 4800);
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-Zhiming-Client": "web",
      },
    });
  } catch {
    throw new Error(
      "连接暂时中断，请检查本地网页服务。刷新页面可查看本轮状态。",
    );
  }
  const data = await response.json();
  if (!response.ok) {
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "请检查出生日期、时刻和问题是否填写正确。",
    );
  }
  return data;
}

function setBusy(value) {
  busy = value;
  document
    .querySelectorAll(
      "#send, #new-chat, #forget, #provider, #birth-form input, #birth-form select, #birth-form button, .nav-item, .suggestions button, .followup-chip, .spread-choice",
    )
    .forEach((element) => {
      element.disabled = value || !state;
    });
  $("#birth-time").disabled = value || $("#unknown-time").checked || !state;
  $("#message").disabled = value || !state;
  $("#input-hint").textContent = value
    ? "正在整理线索，请稍候……"
    : "Enter 发送 · Shift + Enter 换行";
  $("#chat-form").setAttribute("aria-busy", String(value));
  updateLocationDisabled();
}

function showMessage(message) {
  const item = node(
    "div",
    `message ${message.role} ${message.status === "error" ? "error" : ""}`,
  );
  if (message.role === "assistant")
    item.append(node("div", "assistant-mark", "知"));
  const body = node("div", "message-body");
  body.append(
    node(
      "div",
      "message-meta",
      message.role === "user" ? "你 · 此刻的一念" : "知命",
    ),
  );
  body.append(node("div", "message-text", message.text));
  item.append(body);
  $("#messages").append(item);
}

function showThinking() {
  const item = node("div", "message");
  item.id = "thinking";
  item.append(node("div", "assistant-mark", "知"));
  const dots = node("div", "thinking");
  dots.append(
    node("i"),
    node("i"),
    node("i"),
    node("span", "", "正在观照你的问题……"),
  );
  item.append(dots);
  $("#messages").append(item);
  $("#messages").scrollTop = $("#messages").scrollHeight;
}

function renderHistory(history) {
  $("#history").replaceChildren();
  if (!history.length) {
    $("#history").append(
      node("p", "history-empty", "每一次发问，\n都是认识自己的开始。"),
    );
    return;
  }
  for (const reading of history) {
    const question = reading.question.split("\n")[0];
    const button = node("button", "history-item", "·  " + question);
    button.title = question;
    button.addEventListener("click", async () => {
      try {
        renderReading(
          await api(`/api/readings/${encodeURIComponent(reading.reading_id)}`),
        );
        $("#sidebar").classList.remove("open");
        $("#menu-toggle").setAttribute("aria-expanded", "false");
        $("#reading-panel").scrollIntoView({
          behavior: "smooth",
          block: "nearest",
        });
        toast("正在查看历史解读；当前对话保持不变。");
      } catch (error) {
        toast(error.message);
      }
    });
    $("#history").append(button);
  }
}

function addList(parent, title, values) {
  if (!values?.length) return;
  parent.append(node("h3", "reading-subheading", title));
  const list = node("ol", "reading-list");
  values.forEach((value) => list.append(node("li", "", value)));
  parent.append(list);
}

function renderReading(reading) {
  currentReading = reading;
  const content = $("#reading-content");
  content.replaceChildren();
  $("#copy-reading").hidden = !reading;
  if (!reading) {
    content.replaceChildren(
      ...Array.from(emptyReading.cloneNode(true).childNodes),
    );
    return;
  }
  const output = reading.output;
  const tags = node("div", "reading-tags");
  output.systems_used.forEach((value) =>
    tags.append(node("span", "", names[value] || value)),
  );
  content.append(tags, node("p", "reading-summary", output.summary));
  if (reading.tarot?.cards?.length) {
    const cards = node("div", "tarot-cards");
    for (const card of reading.tarot.cards) {
      const box = node("div", "tarot-card");
      box.append(
        node("small", "", card.label),
        node("span", "card-symbol", "✧"),
        node("b", "", card.name),
        node("small", "", card.reversed ? "逆位" : "正位"),
      );
      cards.append(box);
    }
    content.append(cards);
  }
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
  if (output.evidence?.length) {
    const details = node("details", "reading-details");
    details.append(node("summary", "", "查看解读依据"));
    const list = node("ul", "reading-list");
    output.evidence.forEach((item) =>
      list.append(node("li", "", item.reading)),
    );
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
  );
  confidence.append(document.createTextNode(output.confidence.reason));
  if (output.safety?.flag && output.safety.note)
    confidence.append(node("p", "", output.safety.note));
  content.append(confidence);
  for (const question of output.followups || []) {
    const button = node("button", "followup-chip", `${question} ↗`);
    button.disabled = busy;
    button.addEventListener("click", () => draft(question));
    content.append(button);
  }
}

function applyState(next, updateForm = false) {
  state = next;
  $("#provider").value = next.provider;
  $("#connection").classList.remove("offline");
  $("#connection").replaceChildren(
    node("i"),
    document.createTextNode(
      next.provider === "demo" ? "离线演示" : "真实模型已配置",
    ),
  );
  renderTranscript();
  renderReading(
    next.reading && (next.reading.view || "auto") === system
      ? next.reading
      : null,
  );
  renderHistory(next.history);
  if (updateForm) {
    $("#birth-date").value = next.birth.date || "";
    $("#birth-time").value = next.birth.time || "";
    $("#birth-gender").value = next.birth.gender || "";
    $("#unknown-time").checked = next.birth.unknown_time;
    $("#solar-time").value = String(next.birth.true_solar_time || false);
    $("#zishi-rule").value = next.birth.zishi_rule || "next_day";
    $("#birth-clock").value = next.birth.clock_tz || "";
    restoreLocation(next.birth.location_id || "").catch((error) =>
      toast(error.message),
    );
    updateBirthContext();
  }
  renderChart(next.chart);
  setBusy(next.busy);
  if (next.busy) {
    showThinking();
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refresh, 2000);
  }
  $("#messages").scrollTop = $("#messages").scrollHeight;
}

async function refresh() {
  try {
    applyState(await api("/api/session"));
  } catch (error) {
    setBusy(false);
    toast(error.message);
  }
}

function birthInfo() {
  return {
    date: $("#birth-date").value || null,
    time: $("#unknown-time").checked ? "" : $("#birth-time").value,
    unknown_time: $("#unknown-time").checked,
    location_id: selectedLocation?.location_id || "",
    place: selectedLocation?.display_name || "",
    gender: $("#birth-gender").value,
    clock_tz:
      selectedLocation?.tz === "Asia/Urumqi" ? $("#birth-clock").value : "",
    true_solar_time: $("#solar-time").value === "true",
    zishi_rule: $("#zishi-rule").value,
  };
}

function validateBirth() {
  if (locationLoading) {
    toast("地点正在加载，请稍候。");
    return false;
  }
  if (system !== "tarot" && $("#birth-province").value && !selectedLocation) {
    toast("请继续选择城市和县区，以确定出生地点。");
    return false;
  }
  $("#birth-time").setCustomValidity(
    $("#birth-time").value &&
      !$("#birth-date").value &&
      !$("#unknown-time").checked
      ? "请先填写出生日期"
      : "",
  );
  return $("#birth-form").reportValidity();
}

function updateBirthContext() {
  if (system === "tarot") {
    $("#birth-context").textContent = "无需出生资料 · 追问沿用原牌面";
    return;
  }
  const birth = birthInfo();
  $("#birth-context").textContent = birth.date
    ? `${birth.date} · ${birth.time || "时辰不详"} · ${birth.place || "地点待补充"}`
    : "出生信息选填 · 塔罗可直接开始";
}

function draft(question) {
  if (busy || !state) return;
  $("#message").value = question;
  $("#message").focus();
  $("#chat-form").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

$("#messages").addEventListener("click", (event) => {
  const button = event.target.closest("[data-question]");
  if (button) draft(button.dataset.question);
});

document.querySelectorAll("[data-system]").forEach((button) => {
  button.addEventListener("click", () => {
    if (busy) return;
    system = button.dataset.system;
    try {
      sessionStorage.setItem("zhiming-theme", system);
    } catch {
      /* Optional preference. */
    }
    document.querySelectorAll("[data-system]").forEach((item) => {
      item.classList.toggle("active", item === button);
      item.setAttribute("aria-pressed", String(item === button));
    });
    $("#page-title").textContent = system === "auto" ? "问道" : names[system];
    $("#chat-title").textContent =
      system === "auto" ? "与知命对话" : names[system];
    $("#method-label").textContent = "◈ " + names[system];
    $("#message").placeholder = {
      auto: "写下你的困惑，让思绪慢慢展开……",
      bazi: "关于性格、事业与人生节奏，你想了解什么？",
      astro: "借星象的线索，聊聊你此刻的困惑……",
      tarot: "静下心，写下一个具体的问题……",
    }[system];
    applyTheme();
    $("#sidebar").classList.remove("open");
    $("#menu-toggle").setAttribute("aria-expanded", "false");
  });
});

$("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || !state || !validateBirth()) return;
  const message = $("#message").value.trim();
  if (!message) return;
  const birth = birthInfo();
  if (!state.messages.some((message) => (message.system || "auto") === system))
    $("#messages").replaceChildren();
  showMessage({ role: "user", text: message });
  showThinking();
  setBusy(true);
  $("#message").value = "";
  try {
    const next = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, system, birth, spread }),
    });
    applyState(next);
    updateBirthContext();
    if (next.messages.at(-1)?.status === "submit_reading") {
      toast("解读已整理，可在「此间解读」中查看。");
    }
  } catch (error) {
    $("#thinking")?.remove();
    showMessage({ role: "assistant", text: error.message, status: "error" });
    $("#message").value = message;
    setBusy(false);
    toast(error.message);
  }
  if (!busy && window.innerWidth > 760) $("#message").focus();
});

$("#message").addEventListener("keydown", (event) => {
  if (
    event.key === "Enter" &&
    !event.shiftKey &&
    !event.isComposing &&
    event.keyCode !== 229
  ) {
    event.preventDefault();
    $("#chat-form").requestSubmit();
  }
});

$("#unknown-time").addEventListener("change", () => {
  $("#birth-time").disabled = $("#unknown-time").checked;
  if ($("#unknown-time").checked) $("#birth-time").value = "";
});
$("#birth-form").addEventListener("input", () => {
  $("#birth-time").setCustomValidity("");
  $("#birth-feedback").textContent = "资料已修改，将随下一条问题一起发送。";
  $("#birth-feedback").classList.remove("saved");
  if (state) state.chart = null;
  renderChart(null);
});
$("#birth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!validateBirth()) return;
  updateBirthContext();
  $("#birth-feedback").textContent = "已确认，将随下一条问题交给知命。";
  $("#birth-feedback").classList.add("saved");
  if (["bazi", "astro"].includes(system)) {
    setBusy(true);
    try {
      const result = await api("/api/chart", {
        method: "POST",
        body: JSON.stringify({ system, birth: birthInfo() }),
      });
      state.chart = result.chart;
      state.birth = birthInfo();
      renderChart(result.chart);
      if (result.chart)
        $("#chart-panel").scrollIntoView({
          behavior: "smooth",
          block: "nearest",
        });
      $("#birth-feedback").textContent =
        result.question || "命盘已计算，可直接查看或继续提问。";
      toast(result.question || "排盘完成，结果已展示。你可以继续询问解读。");
    } catch (error) {
      toast(error.message);
    } finally {
      setBusy(false);
    }
    return;
  }
  toast("出生信息已就绪。写下你的问题，即可开始。");
});

async function startNew(provider) {
  if (busy && state) return;
  setBusy(true);
  try {
    applyState(
      await (state
        ? api("/api/new", {
            method: "POST",
            body: JSON.stringify({ provider }),
          })
        : api(`/api/session?provider=${encodeURIComponent(provider)}`)),
    );
    $("#message").value = "";
    $("#sidebar").classList.remove("open");
    $("#menu-toggle").setAttribute("aria-expanded", "false");
    toast(
      provider === "demo"
        ? "已开启离线模式：支持历法排盘与塔罗演示。"
        : "新的问道已开启，旧解读可在左侧回看。",
    );
  } catch (error) {
    $("#provider").value = state?.provider || "configured";
    setBusy(false);
    $("#provider").disabled = false;
    toast(error.message);
  }
}
$("#new-chat").addEventListener("click", () => startNew(state.provider));
$("#provider").addEventListener("change", (event) =>
  startNew(event.target.value),
);
$("#forget").addEventListener("click", () => $("#confirm-dialog").showModal());
$("#confirm-dialog").addEventListener("close", async () => {
  if ($("#confirm-dialog").returnValue !== "confirm" || busy) return;
  setBusy(true);
  try {
    applyState(await api("/api/session", { method: "DELETE" }), true);
    $("#birth-feedback").textContent = "确认后，将随下一条问题一起发送。";
    $("#birth-feedback").classList.remove("saved");
    $("#message").value = "";
    toast("当前会话的画像、解读和对话已清除。");
  } catch (error) {
    setBusy(false);
    toast(error.message);
  }
});
$("#copy-reading").addEventListener("click", async () => {
  if (!currentReading) return;
  const output = currentReading.output;
  const text = [
    "知命 · 此间解读",
    output.summary,
    ...output.evidence.map((item) => item.reading),
    "可以考虑：",
    ...output.advice,
    "仅供参考与自我反思。",
  ].join("\n\n");
  try {
    await navigator.clipboard.writeText(text);
    toast("解读已复制。");
  } catch {
    toast("浏览器未允许复制，你可以选中解读文字手动复制。");
  }
});
$("#menu-toggle").addEventListener("click", () => {
  const opened = $("#sidebar").classList.toggle("open");
  $("#menu-toggle").setAttribute("aria-expanded", String(opened));
});
document.addEventListener("click", (event) => {
  if (!event.target.closest("#sidebar, #menu-toggle")) {
    $("#sidebar").classList.remove("open");
    $("#menu-toggle").setAttribute("aria-expanded", "false");
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    $("#sidebar").classList.remove("open");
    $("#menu-toggle").setAttribute("aria-expanded", "false");
  }
});

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const use = document.createElementNS(svg.namespaceURI, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

function renderWelcome() {
  const content = welcome.cloneNode(true);
  const theme = themes[system];
  content.querySelector("h3").textContent = theme.greeting;
  content.querySelector(".welcome-content > p").textContent =
    theme.introduction;
  content.querySelector(".welcome-muted").textContent =
    system === "tarot"
      ? "选择一个牌阵，再从此刻最想问的事开始。"
      : "你可以直接提问，或从下面的一念开始。";
  const suggestions = content.querySelector(".suggestions");
  suggestions.replaceChildren();
  for (const [symbol, title, subtitle, question] of theme.suggestions) {
    const button = node("button");
    button.dataset.question = question;
    const label = node("span");
    label.append(node("b", "", title), node("small", "", subtitle));
    button.append(icon(symbol), label, node("span", "suggestion-arrow", "↗"));
    suggestions.append(button);
  }
  $("#messages").replaceChildren(content);
}

function renderTranscript() {
  const messages = (state?.messages || []).filter(
    (message) => (message.system || "auto") === system,
  );
  $("#messages").replaceChildren();
  if (messages.length) messages.forEach(showMessage);
  else renderWelcome();
}

function renderStage() {
  const visual = $("#stage-visual");
  visual.replaceChildren();
  if (system === "bazi") {
    visual.className = "stage-pillars";
    for (const [key, label] of [
      ["year", "年柱"],
      ["month", "月柱"],
      ["day", "日柱"],
      ["time", "时柱"],
    ]) {
      const box = node("div", "stage-pillar");
      const value =
        state?.chart?.system === "bazi"
          ? state.chart.result.pillars[key] || "未知"
          : "—";
      box.append(node("span", "", value), node("small", "", label));
      visual.append(box);
    }
  } else if (system === "astro") {
    visual.className = "stage-signs";
    for (const [symbol, label] of [
      ["☉", "太阳"],
      ["☽", "月亮"],
      ["↑", "上升"],
    ]) {
      const box = node("span", "", symbol);
      box.append(node("small", "", label));
      visual.append(box);
    }
  } else if (system === "tarot") {
    visual.className = "spread-options";
    for (const [value, label, symbol] of [
      ["single", "单张启示", "▯"],
      ["three_card", "三张牌阵", "▯▯▯"],
      ["decision", "二选一", "A · B"],
    ]) {
      const button = node("button", "spread-choice");
      button.dataset.spread = value;
      button.setAttribute("aria-pressed", String(spread === value));
      button.append(node("span", "", symbol), document.createTextNode(label));
      button.disabled = busy;
      button.addEventListener("click", () => {
        spread = value;
        renderStage();
      });
      visual.append(button);
    }
  }
}

function applyTheme() {
  const theme = themes[system];
  document.body.dataset.theme = system;
  updateBirthContext();
  $(".birth-panel .tag").textContent = ["bazi", "astro"].includes(system)
    ? "排盘资料"
    : "选填";
  $("#page-title").textContent = system === "auto" ? "问道" : names[system];
  $("#chat-title").textContent =
    system === "auto" ? "与知命对话" : names[system];
  $("#method-label").textContent = "◈ " + names[system];
  document.querySelectorAll("[data-system]").forEach((item) => {
    item.classList.toggle("active", item.dataset.system === system);
    item.setAttribute("aria-pressed", String(item.dataset.system === system));
  });
  const seal = node("span", "small-seal");
  seal.append(
    document.createTextNode(theme.seal[0]),
    node("br"),
    document.createTextNode(theme.seal[1]),
  );
  $("#hero-title").replaceChildren(
    document.createTextNode(theme.title[0]),
    node("span", "", theme.title[1]),
    seal,
  );
  $("#theme-eyebrow").textContent = theme.eyebrow;
  $("#theme-description").textContent = theme.description;
  $("#theme-stage").hidden = system === "auto";
  $("#stage-kicker").textContent = theme.kicker || "";
  $("#stage-title").textContent = theme.stageTitle || "";
  $("#stage-description").textContent = theme.stageDescription || "";
  $("#chart-settings").hidden = system !== "bazi";
  $(".save-birth").replaceChildren(
    document.createTextNode(
      system === "bazi"
        ? "排出我的八字"
        : system === "astro"
          ? "绘制本命星图"
          : "确认出生信息",
    ),
    icon("chevron"),
  );
  $(".birth-panel .section-description").textContent =
    system === "astro"
      ? "精确的出生时空，定位你的行星与宫位。"
      : system === "bazi"
        ? "公历生辰与出生地，落定四柱与五行。"
        : "以出生的时空为起点，了解独一无二的你。";
  renderTranscript();
  renderReading(
    state?.reading && (state.reading.view || "auto") === system
      ? state.reading
      : null,
  );
  renderStage();
  renderChart(state?.chart);
  if (!currentReading) {
    $(".reading-empty h3").textContent =
      system === "tarot"
        ? "静心一问，等待翻牌"
        : system === "astro"
          ? "星图有迹，解读待启"
          : system === "bazi"
            ? "四柱既定，方知其意"
            : "一念起，万象生";
    $(".empty-orbit span").textContent =
      system === "tarot" ? "☾" : system === "astro" ? "✧" : "☯";
  }
}

function updateLocationDisabled() {
  for (let i = 0; i < locationFields.length; i++) {
    const select = $(`#birth-${locationFields[i]}`);
    select.disabled =
      busy ||
      !state ||
      locationLoading ||
      (i > 0 && !$(`#birth-${locationFields[i - 1]}`).value) ||
      select.options.length < 2;
    // A single city-centroid option is displayed read-only, but remains selected.
  }
}

function fillOptions(field, options, placeholder) {
  const select = $(`#birth-${field}`);
  select.replaceChildren(new Option(placeholder, ""));
  for (const item of options) select.append(new Option(item.name, item.id));
}

function resetLocationBelow(index) {
  selectedLocation = null;
  for (let i = index + 1; i < locationFields.length; i++)
    fillOptions(locationFields[i], [], "请先选择上一级");
  $("#clock-settings").hidden = true;
  $("#birth-clock").value = "";
  $("#location-feedback").textContent =
    "逐级选择，自动匹配出生地经纬度与时区。";
  if (state) state.chart = null;
  renderChart(null);
  updateBirthContext();
}

async function acceptLocation(identity, version) {
  const location = await api(`/api/locations/${encodeURIComponent(identity)}`);
  if (version !== locationVersion) return;
  selectedLocation = location;
  $("#clock-settings").hidden = location.tz !== "Asia/Urumqi";
  $("#location-feedback").textContent =
    `${location.display_name} · ${location.tz}。${location.precision === "city centroid" ? "当前采用城市中心；该地区未收录区县层级。" : "采用所选行政区中心坐标。"}`;
  updateBirthContext();
}

async function locationChanged(index) {
  const version = ++locationVersion;
  resetLocationBelow(index);
  const identity = $(`#birth-${locationFields[index]}`).value;
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
    const data = await api(
      `/api/locations?parent=${encodeURIComponent(identity)}`,
    );
    if (version !== locationVersion) return;
    if (index === 2 && !data.options.length) {
      fillOptions(
        "district",
        [{ id: identity, name: "市级地点（未收录区县）" }],
        "请选择地点精度",
      );
      $("#birth-district").value = identity;
      await acceptLocation(identity, version);
    } else {
      fillOptions(
        locationFields[index + 1],
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
  const restoredChart = state?.chart;
  await locationsReady;
  if (!identity) {
    $("#birth-country").value = "CN";
    await locationChanged(0);
    return;
  }
  const location = await api(`/api/locations/${encodeURIComponent(identity)}`);
  for (let i = 0; i < location.path.length; i++) {
    const item = location.path[i];
    const index = locationFields.indexOf(item.level);
    if (index < 0) continue;
    $(`#birth-${item.level}`).value = item.id;
    await locationChanged(index);
  }
  selectedLocation = location;
  // Restoring a selected path must not discard the server's matching chart or clock choice.
  if (state?.birth.clock_tz) $("#birth-clock").value = state.birth.clock_tz;
  if (state && restoredChart) {
    state.chart = restoredChart;
    renderChart(restoredChart);
  }
  updateBirthContext();
}
locationFields.forEach((field, index) =>
  $(`#birth-${field}`).addEventListener("change", () => locationChanged(index)),
);

function renderChart(chart) {
  const panel = $("#chart-panel");
  panel.hidden = !chart || chart.system !== system;
  if (panel.hidden) {
    renderStage();
    return;
  }
  const result = chart.result;
  const content = $("#chart-content");
  content.replaceChildren(
    node(
      "p",
      "chart-location",
      `${chart.location.display_name} · ${result.input.birth_local.replace("T", " ")}`,
    ),
  );
  $("#chart-title").textContent =
    chart.system === "bazi" ? "你的四柱命盘" : "你的本命星图";
  panel.querySelector(".tag").textContent =
    chart.system === "bazi" ? "历法计算" : "星历计算";
  if (chart.system === "bazi") {
    const grid = node("div", "pillars-grid");
    for (const [key, label] of [
      ["year", "年柱"],
      ["month", "月柱"],
      ["day", "日柱"],
      ["time", "时柱"],
    ]) {
      const box = node("div", "pillar");
      box.append(
        node("small", "", label),
        node("strong", "", result.pillars[key] || "—"),
        node("em", "", result.nayin?.[key] || "时辰未知"),
      );
      grid.append(box);
    }
    content.append(
      grid,
      node("p", "chart-fact", `日主 · ${result.day_master}`),
    );
    if (result.wuxing_count) {
      const elements = node("div", "elements");
      for (const [name, value] of Object.entries(result.wuxing_count)) {
        const row = node("div", "element-row");
        const bar = node("progress");
        bar.max = 8;
        bar.value = value;
        bar.setAttribute("aria-label", `${name} ${value}`);
        row.append(
          node("span", "", name),
          bar,
          node("span", "", String(value)),
        );
        elements.append(row);
      }
      content.append(
        elements,
        node(
          "p",
          "chart-note",
          "五行按天干与地支主五行计数，不等同于旺衰或喜用神判断。",
        ),
      );
    }
    if (result.dayun) {
      content.append(
        node(
          "p",
          "chart-fact",
          `起运 · ${result.dayun.start_solar}（出生后 ${result.dayun.start_after}）`,
        ),
      );
      const row = node("div", "dayun-row");
      result.dayun.sequence.forEach((item) => {
        const box = node("div", "dayun-item", item.ganzhi);
        box.append(node("small", "", `${item.start_year} 年起`));
        row.append(box);
      });
      content.append(row);
    }
    content.append(
      node(
        "p",
        "chart-note",
        `${chart.birth.true_solar_time ? "出生地真太阳时" : "固定 UTC+8（不用真太阳时）"} · ${chart.birth.zishi_rule === "same_day" ? "0点换日" : "23点换日"} · 立春换年 / 节气换月`,
      ),
    );
  } else {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 260 260");
    svg.setAttribute("class", "natal-wheel");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "本命行星黄道经度示意图");
    function shape(tag, attributes, text) {
      const e = document.createElementNS(svg.namespaceURI, tag);
      Object.entries(attributes).forEach(([k, v]) => e.setAttribute(k, v));
      if (text !== undefined) e.textContent = text;
      svg.append(e);
      return e;
    }
    [116, 96, 63].forEach((r) => shape("circle", { cx: 130, cy: 130, r }));
    const signs = [
      "♈",
      "♉",
      "♊",
      "♋",
      "♌",
      "♍",
      "♎",
      "♏",
      "♐",
      "♑",
      "♒",
      "♓",
    ];
    signs.forEach((sign, i) => {
      const a = ((i * 30 - 75) * Math.PI) / 180;
      shape(
        "text",
        {
          x: 130 + 106 * Math.cos(a),
          y: 135 + 106 * Math.sin(a),
          "text-anchor": "middle",
          class: "zodiac-glyph",
        },
        sign + "\uFE0E",
      );
      const b = ((i * 30 - 90) * Math.PI) / 180;
      shape("line", {
        x1: 130 + 96 * Math.cos(b),
        y1: 130 + 96 * Math.sin(b),
        x2: 130 + 116 * Math.cos(b),
        y2: 130 + 116 * Math.sin(b),
      });
    });
    const symbols = {
      Sun: "☉",
      Moon: "☽",
      Mercury: "☿",
      Venus: "♀",
      Mars: "♂",
      Jupiter: "♃",
      Saturn: "♄",
      Uranus: "♅",
      Neptune: "♆",
      Pluto: "♇",
    };
    result.planets.forEach((p, i) => {
      const a = ((p.lon - 90) * Math.PI) / 180,
        r = 72 + (i % 3) * 8;
      shape("circle", {
        cx: 130 + r * Math.cos(a),
        cy: 130 + r * Math.sin(a),
        r: 2,
        class: "planet-dot",
      });
      shape(
        "text",
        {
          x: 130 + (r - 10) * Math.cos(a),
          y: 134 + (r - 10) * Math.sin(a),
          "text-anchor": "middle",
        },
        symbols[p.body],
      );
    });
    content.append(
      svg,
      node("p", "chart-note", "黄道经度示意 · 白羊座 0° 起点"),
    );
    if (result.asc)
      content.append(
        node(
          "p",
          "chart-fact",
          `上升 · ${result.asc.sign_zh}座　天顶 · ${result.mc.sign_zh}座`,
        ),
      );
    const list = node("div", "planet-list");
    result.planets.forEach((p) => {
      const item = node("div", "planet-item", `${p.body_zh} · ${p.sign_zh}座`);
      item.append(
        node(
          "small",
          "",
          `${p.deg_in_sign.toFixed(2)}°${p.house ? ` · 第${p.house}宫` : ""}${p.retrograde ? " · 逆行" : ""}`,
        ),
      );
      list.append(item);
    });
    content.append(list);
  }
  (result.uncertainty || []).forEach((note) =>
    content.append(node("p", "chart-note", note)),
  );
  renderStage();
}

$("#birth-date").max = new Date().toLocaleDateString("sv-SE", {
  timeZone: "Asia/Shanghai",
});
setBusy(true);
applyTheme();
const locationsReady = initLocations().catch((error) => {
  toast(error.message);
});
api("/api/session")
  .then((next) => applyState(next, true))
  .catch((error) => {
    $("#connection").textContent = "连接未就绪";
    $("#connection").classList.add("offline");
    $("#input-hint").textContent = "服务未就绪，可切换离线演示或刷新重试";
    $("#provider").disabled = false;
    toast(error.message);
  });
