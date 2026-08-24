(function () {
  "use strict";

  const THEME_KEY = "market-screener-theme";
  const storedTheme = (() => {
    try {
      return localStorage.getItem(THEME_KEY);
    } catch (error) {
      return null;
    }
  })();
  const initialTheme =
    storedTheme === "light" || storedTheme === "dark"
      ? storedTheme
      : matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
  document.documentElement.setAttribute("data-theme", initialTheme);

  const preferredTheme = () =>
    matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  const activeTheme = () =>
    document.documentElement.getAttribute("data-theme") || preferredTheme();
  const dateFormatter = new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });

  function validIsoDate(value) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      return false;
    }
    const parsed = new Date(`${value}T00:00:00Z`);
    return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
  }

  function setFreshnessGroup(source, value) {
    if (!validIsoDate(value)) return;
    document.querySelectorAll(`[data-freshness="${source}"]`).forEach((element) => {
      element.dateTime = value;
      element.textContent = dateFormatter.format(new Date(`${value}T00:00:00Z`));
    });
  }

  function applyFreshness(values) {
    Object.entries(values).forEach(([source, value]) => {
      setFreshnessGroup(source, value);
    });
    document.querySelectorAll("[data-freshness-group]").forEach((group) => {
      const slots = [...group.querySelectorAll("time[data-freshness]")];
      group.dataset.state = slots.length > 0 && slots.every((slot) => slot.dateTime)
        ? "ready"
        : "unavailable";
    });
  }

  async function fetchJson(url) {
    const response = await fetch(url, {
      cache: "no-store",
      headers: { accept: "application/json" },
    });
    if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
    return response.json();
  }

  async function loadFreshness() {
    const values = {};
    const staticRequest = fetchJson("dashboard-freshness.json");
    const liveRequests = [
      fetchJson("/api/us-trend-bounce?meta=1"),
      fetchJson("/api/tsha-hbcs?meta=1"),
      fetchJson("/api/forward-test?meta=1"),
    ];
    try {
      const manifest = await staticRequest;
      if (manifest?.schema_version === "dashboard-freshness.v1") {
        for (const source of ["india_weekly", "india_daily", "market", "sectors"]) {
          values[source] = manifest.sources?.[source]?.as_of;
        }
      }
      applyFreshness(values);
    } catch (error) {
      // Live API cutoffs can still populate when the static manifest is unavailable.
    }
    const [trend, ht, outcomes] = await Promise.allSettled(liveRequests);
    if (
      trend.status === "fulfilled" &&
      trend.value?.schema_version === "us-trend-bounce.api.v1"
    ) {
      values.us_weekly = trend.value.snapshot?.pages?.weekly?.data_cutoff;
      values.us_daily = trend.value.snapshot?.pages?.daily?.data_cutoff;
    }
    if (ht.status === "fulfilled" && ht.value?.schema_version === "tsha-hbcs.api.v1") {
      values.ht_india = ht.value.snapshot?.data_cutoff?.IN;
      values.ht_us = ht.value.snapshot?.data_cutoff?.US;
    }
    if (
      outcomes.status === "fulfilled" &&
      outcomes.value?.schema_version === "forward-test.api.v1"
    ) {
      values.outcomes = outcomes.value.snapshot?.data_cutoff;
    }
    applyFreshness(values);
  }

  function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch (error) {
      // The visual change remains available when storage is blocked.
    }
    const button = document.getElementById("themeBtn");
    if (button) {
      button.setAttribute(
        "aria-label",
        `Switch to ${theme === "dark" ? "light" : "dark"} theme`,
      );
    }
  }

  function toggleTheme() {
    setTheme(activeTheme() === "dark" ? "light" : "dark");
  }

  const toggleSelectors = [
    ".preset",
    "button[data-view]",
    "button[data-market]",
    "button[data-filter]",
    "button[data-v]",
    "button[data-chart]",
    "button[data-lbchart]",
    "#newOnly",
    "#filtOnly",
    "#filOnly",
    "#crossOnly",
    "#rotOnly",
    "#previewBtn",
    "#allThree",
    "#filteredOnly",
    "#htOnly",
    "#congressOnly",
    "#pbOnly",
    "#mqOnly",
    "#eventOnly",
    "#researchColumns",
  ].join(",");

  function syncPressed(root = document) {
    root.querySelectorAll(toggleSelectors).forEach((button) => {
      if (button.tagName === "BUTTON") {
        button.setAttribute("aria-pressed", String(button.classList.contains("on")));
      }
    });
  }

  function syncSortHeaders(root = document) {
    root.querySelectorAll("th[data-k], th[data-sort]").forEach((header) => {
      if (!header.querySelector(":scope > .sortbtn")) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "sortbtn";
        button.textContent = header.textContent.trim();
        header.textContent = "";
        header.appendChild(button);
      }
      header.setAttribute(
        "aria-sort",
        header.classList.contains("sorted")
          ? header.classList.contains("asc")
            ? "ascending"
            : "descending"
          : "none",
      );
    });
  }

  function init() {
    const themeButton = document.getElementById("themeBtn");
    if (themeButton) themeButton.addEventListener("click", toggleTheme);
    setTheme(activeTheme());
    void loadFreshness();
    syncPressed();
    syncSortHeaders();
    const observer = new MutationObserver((mutations) => {
      if (mutations.some((mutation) => mutation.attributeName === "class")) {
        syncPressed();
        syncSortHeaders();
      }
    });
    observer.observe(document.body, {
      subtree: true,
      attributes: true,
      attributeFilter: ["class"],
    });
  }

  window.DashboardShell = {
    loadFreshness,
    setTheme,
    setFreshnessGroup,
    syncPressed,
    syncSortHeaders,
    toggleTheme,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
