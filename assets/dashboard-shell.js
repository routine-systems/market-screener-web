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

  const freshnessState = {};
  const asOf = (value) =>
    value && typeof value === "object" ? value.as_of || value.date || null : value || null;
  const statusOf = (value) =>
    value && typeof value === "object" ? String(value.status || "").toLowerCase() : "";
  const compact = (value) => value || "—";

  function setFreshnessGroup(key, value, status = "") {
    freshnessState[key] = { value, status };
    const chip = document.querySelector(`[data-freshness="${key}"]`);
    if (!chip) return;
    chip.classList.remove("pending", "stale");
    if (!value || value.includes("—")) chip.classList.add("pending");
    if (status === "stale") chip.classList.add("stale");
    const output = chip.querySelector(".freshness-value");
    if (output) output.textContent = value || "—";
  }

  function applyStaticFreshness(payload) {
    const sources = payload && payload.sources ? payload.sources : {};
    setFreshnessGroup(
      "india",
      `W ${compact(asOf(sources.india_weekly))} · D ${compact(asOf(sources.india_daily))}`,
      [statusOf(sources.india_weekly), statusOf(sources.india_daily)].includes("stale")
        ? "stale"
        : "",
    );
    setFreshnessGroup(
      "context",
      `M ${compact(asOf(sources.market))} · S ${compact(asOf(sources.sectors))}`,
      [statusOf(sources.market), statusOf(sources.sectors)].includes("stale")
        ? "stale"
        : "",
    );
    setFreshnessGroup(
      "outcomes",
      compact(asOf(sources.outcomes)),
      statusOf(sources.outcomes),
    );
    const usWeekly = asOf(sources.us_weekly);
    const usDaily = asOf(sources.us_daily);
    if (usWeekly || usDaily) {
      setFreshnessGroup("us", `W ${compact(usWeekly)} · D ${compact(usDaily)}`);
    }
    const htIndia = asOf(sources.ht_india);
    const htUs = asOf(sources.ht_us);
    if (htIndia || htUs) {
      setFreshnessGroup("ht", `IN ${compact(htIndia)} · US ${compact(htUs)}`);
    }
  }

  async function loadFreshness() {
    if (!document.querySelector(".dashboard-freshness")) return;
    try {
      const response = await fetch("dashboard-freshness.json", {
        headers: { accept: "application/json" },
        cache: "no-store",
      });
      if (response.ok) applyStaticFreshness(await response.json());
    } catch (error) {
      // Page-specific status remains visible when the shared file is unavailable.
    }

    const requests = [
      fetch("/api/us-trend-bounce?meta=1", { headers: { accept: "application/json" } })
        .then((response) => (response.ok ? response.json() : null))
        .then((payload) => {
          const pages = payload && payload.snapshot && payload.snapshot.pages;
          if (!pages) return;
          setFreshnessGroup(
            "us",
            `W ${compact(pages.weekly && pages.weekly.data_cutoff)} · D ${compact(
              pages.daily && pages.daily.data_cutoff,
            )}`,
          );
        }),
      fetch("/api/tsha-hbcs?meta=1", { headers: { accept: "application/json" } })
        .then((response) => (response.ok ? response.json() : null))
        .then((payload) => {
          const cutoff = payload && payload.snapshot && payload.snapshot.data_cutoff;
          if (!cutoff) return;
          setFreshnessGroup(
            "ht",
            `IN ${compact(cutoff.IN)} · US ${compact(cutoff.US)}`,
          );
        }),
    ];
    await Promise.allSettled(requests);
  }

  function init() {
    const themeButton = document.getElementById("themeBtn");
    if (themeButton) themeButton.addEventListener("click", toggleTheme);
    setTheme(activeTheme());
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
    loadFreshness();
  }

  window.DashboardShell = {
    setFreshnessGroup,
    setTheme,
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
