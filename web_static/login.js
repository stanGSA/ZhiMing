"use strict";

// Entrance: enter as a guest, or sign in / register an account whose records are kept.
const $ = (selector) => document.querySelector(selector);
const tabs = Array.from(document.querySelectorAll(".gate-tab"));
const params = new URLSearchParams(location.search);
const NEXT = /^\/(ask|bazi|astro|tarot|name|dream|daily|admin)$/.test(params.get("next") || "")
  ? params.get("next")
  : "/ask";
let mode = "login";
let pending = false;

function select(tab) {
  for (const item of tabs) {
    const active = item === tab;
    item.setAttribute("aria-selected", String(active));
    item.tabIndex = active ? 0 : -1;
    document.getElementById(item.getAttribute("aria-controls")).hidden = !active;
  }
}

tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => select(tab));
  tab.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    const next = tabs[(index + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    select(next);
    next.focus();
  });
});

function setMode(next) {
  mode = next;
  document.querySelectorAll(".gate-mode").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.mode === next));
  });
  document.querySelectorAll("[data-register]").forEach((element) => {
    element.hidden = next !== "register";
  });
  $("#account-password").autocomplete = next === "register" ? "new-password" : "current-password";
  $("#account-submit").textContent = next === "register" ? "注册并登入" : "登　入";
  showError("");
}

function showError(message) {
  $("#account-error").textContent = message;
  $("#account-error").hidden = !message;
}

const STATUS_TEXT = {
  429: "尝试次数过多，请稍后再试。",
  500: "服务出现意外错误，请稍后重试。",
  502: "服务暂时无法连接，请稍后重试。",
  503: "服务暂时不可用，请稍后重试。",
  504: "服务响应超时，请稍后重试。",
};

async function call(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", "X-Zhiming-Client": "web" },
    });
  } catch {
    throw new Error("连接暂时中断，请检查网络或本地网页服务后重试。");
  }
  let data = {};
  try {
    data = await response.json();
  } catch {
    // A proxy or crash page is not JSON; fall back to the status below.
  }
  if (!response.ok)
    throw new Error(data.detail?.message || STATUS_TEXT[response.status] || "请求未能完成，请稍后重试。");
  return data;
}

function validate() {
  const name = $("#account-name").value.trim();
  const password = $("#account-password").value;
  if (!name) return "请填写账号名。";
  if (!password) return "请填写密码。";
  if (mode === "register") {
    if (password.length < 8) return "密码至少需要 8 个字符。";
    if (password !== $("#account-confirm").value) return "两次输入的密码不一致。";
    if (!$("#accept-privacy").checked) return "请先阅读并同意《隐私说明》。";
  }
  return "";
}

async function submit(event) {
  event.preventDefault();
  if (pending) return;
  const problem = validate();
  if (problem) {
    showError(problem);
    return;
  }
  pending = true;
  $("#account-submit").disabled = true;
  showError("");
  const body = {
    username: $("#account-name").value.trim(),
    password: $("#account-password").value,
    keep_guest_records: !$("#keep-guest-row").hidden && $("#keep-guest").checked,
  };
  if (mode === "register") body.accept_privacy = true;
  try {
    const result = await call(`/api/account/${mode}`, { method: "POST", body: JSON.stringify(body) });
    try {
      localStorage.setItem("zhiming.account", result.account.username);
      sessionStorage.setItem(
        "zhiming.notice",
        (mode === "register" ? "账号已创建" : `欢迎回来，${result.account.username}`) +
          (result.moved_readings ? `，${result.moved_readings} 条访客记录已保存到账号。` : "。"),
      );
    } catch {
      // Storage may be disabled; the welcome note is optional.
    }
    location.assign(NEXT);
  } catch (error) {
    showError(error.message);
    $("#account-password").select();
  } finally {
    pending = false;
    $("#account-submit").disabled = false;
  }
}

async function load() {
  let info;
  try {
    info = await call("/api/account");
  } catch {
    return;
  }
  if (info.account) {
    $("#signed-name").textContent = info.account.username;
    if (info.account.quota)
      $("#signed-quota").textContent = `免费额度剩余 ${info.account.quota.remaining.toLocaleString("zh-CN")} / ${info.account.quota.limit.toLocaleString("zh-CN")} token，累计使用，不按月重置。`;
    $("#signed-in").hidden = false;
    $("#account-panel").hidden = true;
    select($("#tab-account"));
  }
  const guest = info.guest;
  if (guest && (guest.readings || guest.birth)) {
    $("#guest-summary").textContent = [
      ...(guest.birth ? ["生辰档案"] : []),
      ...(guest.readings ? [`${guest.readings} 条解读`] : []),
    ].join("、");
    $("#keep-guest-row").hidden = false;
  }
}

document.querySelectorAll(".gate-mode").forEach((button) =>
  button.addEventListener("click", () => setMode(button.dataset.mode)),
);
$("#account-form").addEventListener("submit", submit);
$("#sign-out").addEventListener("click", async () => {
  try {
    await call("/api/account/logout", { method: "POST", body: "{}" });
    try {
      localStorage.removeItem("zhiming.account");
    } catch {
      // Nothing to forget.
    }
    location.reload();
  } catch (error) {
    $("#signed-error").textContent = error.message;
    $("#signed-error").hidden = false;
  }
});

select($(params.get("tab") === "guest" ? "#tab-guest" : "#tab-account"));
if (params.get("mode") === "register") setMode("register");
load();
