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
  }

  window.DashboardShell = {
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
