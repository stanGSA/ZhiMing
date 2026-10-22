"use strict";

// Entrance tabs: guest entry works today; the account tab only explains that it is coming.
const tabs = Array.from(document.querySelectorAll(".gate-tab"));

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
