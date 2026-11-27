"use strict";

// Entrance: sign in / register an account for model readings, or enter offline demo as a guest.
const $ = (selector) => document.querySelector(selector);
const tabs = Array.from(document.querySelectorAll(".gate-tab"));
const params = new URLSearchParams(location.search);
const NEXT = /^\/(ask|bazi|astro|tarot|name|dream|daily|admin)$/.test(params.get("next") || "")
  ? params.get("next")
  : "/ask";
let mode = "login";
let pending = false;

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

function formatSignedQuota(account) {
  const quota = account?.quota;
  if (!quota) return "";
  if (quota.limit === null) {
    return "账号额度不限；全站预算、并发和异常消耗保护仍生效。";
  }
  const sub = account.billing?.quota?.subscription;
  const perm = account.billing?.quota?.permanent;
  if (sub && sub.limit > 0) {
    const expiry = sub.earliest_expires_at ? `（至 ${formatShanghaiTime(sub.earliest_expires_at)}）` : "";
    const permText =
      perm && perm.limit !== null
        ? `；永久额度剩余 ${perm.remaining.toLocaleString("zh-CN")} token`
        : "";
    return `当前可用 ${quota.remaining.toLocaleString("zh-CN")} token：当月订阅剩余 ${sub.remaining.toLocaleString("zh-CN")} token${expiry}${permText}，优先扣减即将到期额度。`;
  }
  return `免费额度剩余 ${quota.remaining.toLocaleString("zh-CN")} / ${quota.limit.toLocaleString("zh-CN")} token，累计使用，不按月重置。`;
}

function renderAstrolabe() {
  const host = $("#astrolabe");
  if (!host) return;
  const rad = (d) => (d * Math.PI) / 180;
  const pt = (d, r) => [r * Math.sin(rad(d)), -r * Math.cos(rad(d))];
  const seg = (d, r1, r2, cls) => {
    const [x1, y1] = pt(d, r1);
    const [x2, y2] = pt(d, r2);
    return `<line class="${cls}" x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"/>`;
  };
  const txt = (d, r, s, cls) =>
    `<text class="${cls}" transform="rotate(${d}) translate(0 ${-r})">${s}</text>`;
  const ring = (r1, r2, cls) =>
    `<path class="${cls}" fill-rule="evenodd" d="M0 ${-r2}A${r2} ${r2} 0 1 1 0 ${r2}A${r2} ${r2} 0 1 1 0 ${-r2}ZM0 ${-r1}A${r1} ${r1} 0 1 0 0 ${r1}A${r1} ${r1} 0 1 0 0 ${-r1}Z"/>`;

  // 几何八卦爻画（从内向外三爻：1=阳爻实线，0=阴爻断线）
  const trigram = (deg, r, bits) => {
    let g = `<g transform="rotate(${deg}) translate(0 ${-r})">`;
    bits.forEach((b, i) => {
      const y = (1 - i) * 5;
      if (b) g += `<line class="a-trigram" x1="-10" y1="${y}" x2="10" y2="${y}"/>`;
      else
        g += `<line class="a-trigram" x1="-10" y1="${y}" x2="-2.2" y2="${y}"/><line class="a-trigram" x1="2.2" y1="${y}" x2="10" y2="${y}"/>`;
    });
    return g + "</g>";
  };

  // 矢量月相（0=新月, 1=峨眉月, 2=上弦月, 4=满月, 6=下弦月, 7=残月）
  const moonPhase = (cx, cy, r, phase) => {
    const x = Number(cx.toFixed(1));
    const y = Number(cy.toFixed(1));
    if (phase === 0) {
      return `<circle cx="${x}" cy="${y}" r="${r}" fill="#25324c" stroke="#25324c" stroke-width="0.9"/>`;
    }
    if (phase === 4) {
      return `<circle cx="${x}" cy="${y}" r="${r}" fill="#fbf9f5" stroke="#9b7a43" stroke-width="1"/>`;
    }
    const base = `<circle cx="${x}" cy="${y}" r="${r}" fill="#fbf9f5" stroke="#25324c" stroke-width="0.9"/>`;
    const map = {
      1: `M${x} ${y - r} A${r} ${r} 0 1 0 ${x} ${y + r} A${r * 0.45} ${r} 0 1 1 ${x} ${y - r} Z`,
      2: `M${x} ${y - r} A${r} ${r} 0 1 0 ${x} ${y + r} Z`,
      6: `M${x} ${y - r} A${r} ${r} 0 1 1 ${x} ${y + r} Z`,
      7: `M${x} ${y - r} A${r} ${r} 0 1 1 ${x} ${y + r} A${r * 0.45} ${r} 0 1 0 ${x} ${y - r} Z`,
    };
    return base + `<path d="${map[phase]}" fill="#25324c"/>`;
  };

  // 1) 外圈：西方黄道十二宫
  const romans = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
  const signs = [
    "ARIES",
    "TAURUS",
    "GEMINI",
    "CANCER",
    "LEO",
    "VIRGO",
    "LIBRA",
    "SCORPIO",
    "SAGITTARIUS",
    "CAPRICORN",
    "AQUARIUS",
    "PISCES",
  ];
  let outer =
    ring(244, 294, "a-band-ind") +
    `<circle class="a-ring-ink" r="294"/><circle class="a-ring-thin" r="284"/><circle class="a-ring-bronze" r="244"/>`;
  for (let d = 0; d < 360; d += 2) {
    const major = d % 30 === 0;
    const mid = d % 10 === 0;
    outer += seg(
      d,
      294,
      major ? 281 : mid ? 286 : 289.5,
      major ? "a-tick-b" : mid ? "a-tick-m" : "a-tick",
    );
  }
  romans.forEach((rm, i) => {
    const a = i * 30 + 15;
    outer += seg(i * 30, 244, 294, "a-sep");
    outer += txt(a, 270, rm, "a-roman");
    outer += txt(a, 253, signs[i], "a-zod-name");
  });

  // 2) 中圈：东方十二地支 + 二十四节气
  const zhi = ["午", "未", "申", "酉", "戌", "亥", "子", "丑", "寅", "卯", "辰", "巳"];
  const jieqi = [
    "芒种",
    "夏至",
    "小暑",
    "大暑",
    "立秋",
    "处暑",
    "白露",
    "秋分",
    "寒露",
    "霜降",
    "立冬",
    "小雪",
    "大雪",
    "冬至",
    "小寒",
    "大寒",
    "立春",
    "雨水",
    "惊蛰",
    "春分",
    "清明",
    "谷雨",
    "立夏",
    "小满",
  ];
  let mid =
    ring(176, 232, "a-band") +
    `<circle class="a-ring-thin" r="232"/><circle class="a-ring-thin" r="208"/><circle class="a-ring-bronze" r="176"/>`;
  jieqi.forEach((jq, i) => {
    const a = i * 15;
    mid += txt(a, 220, jq, "a-jieqi");
    mid += seg(a + 7.5, 208, 232, "a-sep");
  });
  zhi.forEach((z, i) => {
    const a = i * 30;
    mid += txt(a, 192, z, "a-zhi");
    mid += seg(a + 15, 176, 208, "a-sep");
  });

  // 3) 内圈：几何八卦（后天方位）
  const gua = [
    ["离", [1, 0, 1]],
    ["坤", [0, 0, 0]],
    ["兑", [1, 1, 0]],
    ["乾", [1, 1, 1]],
    ["坎", [0, 1, 0]],
    ["艮", [0, 0, 1]],
    ["震", [1, 0, 0]],
    ["巽", [0, 1, 1]],
  ];
  let inner = `<circle class="a-ring-thin" r="168"/><circle class="a-ring-ink" r="106"/>`;
  gua.forEach(([name, bits], i) => {
    const a = i * 45;
    inner += trigram(a, 146, bits);
    inner += txt(a, 122, name, "a-gua");
    inner += seg(a + 22.5, 106, 168, "a-sep");
  });

  // 4) 中心八芒星
  let star = "";
  for (let i = 0; i < 8; i++) {
    const [x1, y1] = pt(i * 45, 76);
    const [x2, y2] = pt(i * 45 + 22.5, 28);
    const [x3, y3] = pt(i * 45 + 45, 76);
    star += `M${x1.toFixed(1)} ${y1.toFixed(1)} L${x2.toFixed(1)} ${y2.toFixed(1)} L${x3.toFixed(1)} ${y3.toFixed(1)} `;
  }

  // 5) 顶部 7 态对称月相：新月 → 峨眉 → 上弦 → 满月 → 下弦 → 残月 → 新月
  const moonPhases = [0, 1, 2, 4, 6, 7, 0];
  let moons = "";
  [-48, -32, -16, 0, 16, 32, 48].forEach((deg, idx) => {
    const [mx, my] = pt(deg, 324);
    moons += moonPhase(mx, my, 6.2, moonPhases[idx]);
  });

  // 6) 底部对称天文星点
  let dots = "";
  [-36, -18, 0, 18, 36].forEach((deg) => {
    const [dx, dy] = pt(180 + deg, 320);
    dots += `<circle cx="${dx.toFixed(1)}" cy="${dy.toFixed(1)}" r="${deg === 0 ? 2.4 : 1.4}" fill="${deg === 0 ? "#9b7a43" : "#25324c"}" opacity="0.65"/>`;
  });

  const [arcX1, arcY1] = pt(-56, 324);
  const [arcX2, arcY2] = pt(56, 324);
  host.innerHTML = `<svg viewBox="-355 -355 710 710">
  <rect class="a-frame" x="-306" y="-306" width="612" height="612"/>
  <rect class="a-frame" x="-296" y="-296" width="592" height="592" stroke-dasharray="1 6"/>
  <ellipse class="a-orbit" rx="344" ry="132" transform="rotate(-24)"/>
  <ellipse class="a-orbit-dash" rx="338" ry="118" transform="rotate(28)"/>
  <path class="a-orbit-dash" d="M${arcX1.toFixed(1)} ${arcY1.toFixed(1)} A324 324 0 0 1 ${arcX2.toFixed(1)} ${arcY2.toFixed(1)}"/>
  ${moons}
  ${dots}
  <circle r="294" fill="rgba(255,255,255,0.48)"/>
  <g class="spin-ccw">${outer}</g>
  <g class="spin-cw">${mid}${inner}</g>
  <circle r="96" fill="#fbf9f5" stroke="rgba(22,22,20,0.22)" stroke-width="0.7"/>
  <circle class="a-ring-bronze" r="76"/>
  <path class="a-star-line" d="${star}"/>
  <line class="a-cross" x1="-106" y1="0" x2="106" y2="0"/>
  <line class="a-cross" x1="0" y1="-106" x2="0" y2="106"/>
  <path class="a-needle-n" d="M0 -56 L4.5 0 L-4.5 0 Z"/>
  <path class="a-needle-s" d="M-4.5 0 L4.5 0 L0 56 Z"/>
  <circle r="4" fill="#fbf9f5" stroke="#161614" stroke-width="1.2"/>
</svg>`;
}

function setMode(next) {
  mode = next;
  document.querySelectorAll("[data-register]").forEach((element) => {
    element.hidden = next !== "register";
  });
  $("#account-name").autocomplete = next === "register" ? "email" : "username";
  $("#account-password").autocomplete = next === "register" ? "new-password" : "current-password";
  $("#account-password").placeholder =
    next === "register" ? "至少 8 位，含两类字符" : "请输入密码";
  $("#account-submit").textContent = next === "register" ? "注册并登入" : "登　入";
  showError("");
}

function select(tab) {
  if (!tab || tab.hidden || tab.disabled) return;
  for (const item of tabs) {
    const active = item === tab;
    item.setAttribute("aria-selected", String(active));
    item.tabIndex = active ? 0 : -1;
  }
  const pane = tab.dataset.pane;
  const isGuest = pane === "guest";
  $("#panel-guest").hidden = !isGuest;
  $("#panel-account").hidden = isGuest;
  if (!isGuest) {
    $("#panel-account").setAttribute("aria-labelledby", tab.id);
    setMode(pane === "register" ? "register" : "login");
  }
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => select(tab));
  tab.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    const enabled = tabs.filter((item) => !item.hidden && !item.disabled);
    const pos = enabled.indexOf(tab);
    if (pos < 0 || enabled.length < 2) return;
    event.preventDefault();
    const next = enabled[(pos + (event.key === "ArrowRight" ? 1 : enabled.length - 1)) % enabled.length];
    select(next);
    next.focus();
  });
});

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
    throw new Error(
      data.detail?.message || STATUS_TEXT[response.status] || "请求未能完成，请稍后重试。",
    );
  return data;
}

function validate() {
  const email = $("#account-name").value.trim();
  const password = $("#account-password").value;
  if (!email) return "请填写邮箱。";
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
    email: $("#account-name").value.trim(),
    password: $("#account-password").value,
    keep_guest_records: !$("#keep-guest-row").hidden && $("#keep-guest").checked,
  };
  if (mode === "register") body.accept_privacy = true;
  try {
    const result = await call(`/api/account/${mode}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    try {
      localStorage.setItem("zhiming.account", result.account.email);
      sessionStorage.setItem(
        "zhiming.notice",
        (mode === "register" ? "账号已创建" : `欢迎回来，${result.account.email}`) +
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
  if (Number.isInteger(info.registration_free_tokens) && $("#registration-allowance")) {
    $("#registration-allowance").textContent =
      info.registration_free_tokens.toLocaleString("zh-CN");
  }
  if (info.account) {
    $("#signed-name").textContent = info.account.email;
    if ($("#signed-quota")) {
      const quotaText = formatSignedQuota(info.account);
      $("#signed-quota").textContent = quotaText;
      $("#signed-quota").hidden = !quotaText;
    }
    $("#signed-in").hidden = false;
    $("#account-panel").hidden = true;
    const regTab = $("#tab-register");
    if (regTab) {
      regTab.hidden = true;
      regTab.disabled = true;
    }
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

renderAstrolabe();
if (params.get("mode") === "register") select($("#tab-register"));
else if (params.get("tab") === "guest") select($("#tab-guest"));
else select($("#tab-account"));
load();
