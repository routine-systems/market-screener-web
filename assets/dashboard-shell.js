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

  // Rows are selected/sorted by each page before paging; CSV uses the full set.
  const paging = { page: 0, size: 100, pages: 1, element: null };
  function paginate(rows, keepPage = false) {
    if (!paging.element) {
      const nav = document.createElement('nav');
      nav.className = 'pager';
      nav.setAttribute('aria-label', 'Results pagination');
      nav.innerHTML = '<button type="button" data-page="first">« First</button><button type="button" data-page="previous">‹ Previous</button><label>Page <select aria-label="Results page" data-page-select></select></label><span data-pages></span><button type="button" data-page="next">Next ›</button><button type="button" data-page="last">Last »</button><label>Rows per page <select aria-label="Rows per page" data-page-size><option>50</option><option selected>100</option><option>250</option></select></label><span data-page-range role="status"></span>';
      document.querySelector('.tablewrap').after(nav);
      paging.element = nav;
      const redraw = () => {
        if (document.body.dataset.dashboardView === 'ht') window.render(false, true);
        else window.render(true);
        document.querySelector('.tablewrap').scrollTop = 0;
      };
      nav.addEventListener('click', event => {
        const action = event.target.closest('[data-page]')?.dataset.page;
        if (!action) return;
        paging.page = {first: 0, previous: paging.page - 1, next: paging.page + 1, last: paging.pages - 1}[action];
        redraw();
      });
      nav.querySelector('[data-page-select]').addEventListener('change', event => {
        paging.page = Number(event.target.value); redraw();
      });
      nav.querySelector('[data-page-size]').addEventListener('change', event => {
        paging.size = Number(event.target.value); paging.page = 0; redraw();
      });
    }
    if (!keepPage) paging.page = 0;
    paging.pages = Math.max(1, Math.ceil(rows.length / paging.size));
    paging.page = Math.max(0, Math.min(paging.page, paging.pages - 1));
    const start = paging.page * paging.size, end = Math.min(rows.length, start + paging.size);
    const nav = paging.element, selector = nav.querySelector('[data-page-select]');
    if (selector.options.length !== paging.pages) selector.innerHTML = Array.from({length:paging.pages}, (_,i) => `<option value="${i}">${i + 1}</option>`).join('');
    selector.value = String(paging.page);
    nav.querySelector('[data-pages]').textContent = `of ${paging.pages}`;
    for (const key of ['first','previous']) nav.querySelector(`[data-page="${key}"]`).disabled = paging.page === 0;
    for (const key of ['next','last']) nav.querySelector(`[data-page="${key}"]`).disabled = paging.page === paging.pages - 1;
    nav.querySelector('[data-page-range]').textContent = rows.length ? `Rows ${start + 1}–${end} of ${rows.length}` : '0 rows';
    return rows.slice(start, end);
  }

  function initResponsiveLayout() {
    const mobile = matchMedia('(max-width: 640px)');
    const anchor = document.getElementById('dashboard-results');
    if (!anchor) return;
    const moves = [], sheets = {};
    const tools = document.createElement('div');
    tools.className = 'mobile-tools mobile-only';
    tools.innerHTML = '<button type="button" id="mobileFilters" aria-haspopup="dialog">Filters</button>';
    const scope = document.createElement('div');
    scope.className = 'mobile-scope mobile-only';
    scope.setAttribute('aria-live', 'polite');
    const count = document.createElement('div');
    count.className = 'mobile-count mobile-only';
    anchor.before(tools, scope, count);
    const table = anchor.nextElementSibling?.querySelector('table');
    if (table) {
      const columns = document.createElement('button');
      columns.type = 'button'; columns.className = 'mobile-only';
      columns.textContent = 'All columns'; columns.setAttribute('aria-pressed', 'false');
      columns.addEventListener('click', () => {
        const expanded = document.body.classList.toggle('mobile-all-columns');
        columns.setAttribute('aria-pressed', String(expanded));
        columns.textContent = expanded ? 'Key columns' : 'All columns';
      });
      tools.appendChild(columns);
    }
    function makeSheet(name, label, trigger) {
      const dialog = document.createElement('dialog');
      dialog.className = `mobile-sheet mobile-sheet-${name}`;
      dialog.id = `mobile-${name}-sheet`;
      dialog.setAttribute('aria-labelledby', `mobile-${name}-title`);
      dialog.innerHTML = `<div class="sheet-header"><h2 id="mobile-${name}-title">${label}</h2><button type="button" class="sheet-close" aria-label="Close ${label.toLowerCase()}">×</button></div><div class="sheet-body"></div><div class="sheet-footer"><button type="button" class="sheet-done">${name === 'filters' ? 'Show results' : 'Done'}</button></div>`;
      document.body.appendChild(dialog);
      trigger.setAttribute('aria-controls', dialog.id);
      trigger.setAttribute('aria-expanded', 'false');
      const close = () => dialog.close();
      trigger.addEventListener('click', () => { dialog.showModal(); trigger.setAttribute('aria-expanded','true'); });
      dialog.querySelector('.sheet-close').addEventListener('click', close);
      dialog.querySelector('.sheet-done').addEventListener('click', close);
      dialog.addEventListener('click', event => { if (event.target === dialog) { const r=dialog.getBoundingClientRect(); if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom) close(); } });
      dialog.addEventListener('close', () => { trigger.setAttribute('aria-expanded','false'); if(mobile.matches) trigger.focus(); });
      sheets[name] = {dialog, body: dialog.querySelector('.sheet-body')};
    }
    makeSheet('views', 'Views', document.getElementById('viewSwitcher'));
    makeSheet('info', 'Summary and data', document.getElementById('pageInfo'));
    makeSheet('filters', 'Filters and periods', document.getElementById('mobileFilters'));
    const clear = document.createElement('button');
    clear.type = 'button'; clear.textContent = 'Clear filters';
    sheets.filters.dialog.querySelector('.sheet-footer').prepend(clear);
    const narrowing = ['newOnly','filtOnly','filOnly','crossOnly','allThree','filteredOnly','htOnly','congressOnly','pbOnly','mqOnly','eventOnly','ignitionOnly'];
    clear.addEventListener('click', () => {
      for (const id of narrowing) {
        const button = document.getElementById(id);
        if (button?.classList.contains('on') && !button.hidden) button.click();
      }
      document.querySelector('#cohorts button[data-v="all"]')?.click();
      const forwardAll = sheets.filters.body.querySelector('button[data-filter="all"]');
      forwardAll?.click();
      for (const [id,value] of [['liquidity','0'],['side','all']]) {
        const select = document.getElementById(id);
        if (select) {select.value=value;select.dispatchEvent(new Event('change',{bubbles:true}));}
      }
      document.getElementById('clearSector')?.click();
      const search = document.getElementById('search');
      if (search) {search.value='';search.dispatchEvent(new Event('input',{bubbles:true}));}
      updateScope();
    });
    function relocate(element, destination) {
      if (!element) return;
      const marker = document.createComment('desktop position');
      element.before(marker); moves.push({element,marker}); destination.appendChild(element);
    }
    function updateScope() {
      if (!mobile.matches) return;
      let active = narrowing.filter(id => {
        const button=document.getElementById(id);return button && !button.hidden && button.classList.contains('on');
      }).length;
      for (const [id,none] of [['liquidity','0'],['side','all']]) {
        const select=document.getElementById(id);if(select && select.value!==none) active++;
      }
      if(document.querySelector('#cohorts button.on')?.dataset.v==='ht_vt') active++;
      if(document.getElementById('clearSector')) active++;
      const selectedForward=sheets.filters.body.querySelector('button[data-filter].on');
      if(selectedForward && selectedForward.dataset.filter!=='all') active++;
      clear.disabled=active===0&&!document.getElementById('search')?.value;
      clear.hidden=!!sheets.filters.body.querySelector('.presets');
      const filterButton=document.getElementById('mobileFilters');
      const label=active?`Filters (${active})`:'Filters';
      if(filterButton.textContent!==label) filterButton.textContent=label;
      const range=sheets.filters.body.querySelector('.rangebar');
      let summary='';
      if(range && range.getAttribute('aria-disabled')!=='true') {
        const selections=[...range.querySelectorAll('select')].filter(s=>!s.disabled);
        const dates=selections.map(s=>s.selectedOptions[0]?.textContent).filter(Boolean);
        const preset=[...range.querySelectorAll('button.on')].map(b=>b.textContent).join(' ');
        summary=[preset,dates.length?dates.join(' → '):''].filter(Boolean).join(' · ');
      }
      const chartControls=sheets.filters.body.querySelector('.presets');
      if(chartControls) summary=[...chartControls.querySelectorAll('button.on')].map(b=>b.textContent).join(' · ');
      const forward=sheets.filters.body.querySelector('button[data-filter].on');
      if(forward) summary=forward.textContent;
      if(scope.textContent!==summary) scope.textContent=summary;
    }
    function adapt() {
      if(mobile.matches && !moves.length) {
        relocate(document.querySelector('.dashboard-destinations'), sheets.views.body);
        for(const element of document.querySelectorAll('[data-mobile-panel]')) relocate(element,sheets[element.dataset.mobilePanel].body);
        relocate(document.getElementById('search'),tools);
        const search=document.getElementById('search');if(search) tools.prepend(search);
        for(const element of document.querySelectorAll('[data-mobile-count]')) relocate(element,count);
        updateScope();
      } else if(!mobile.matches && moves.length) {
        Object.values(sheets).forEach(({dialog})=>{if(dialog.open) dialog.close();});
        for(const {element,marker} of moves.reverse()) {marker.replaceWith(element);}
        moves.length=0;
      }
    }
    // Observe controls only; large result tables never enter this observer.
    let pending=false;
    const refresh=()=>{if(pending)return;pending=true;queueMicrotask(()=>{pending=false;updateScope();});};
    new MutationObserver(refresh).observe(sheets.filters.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class','hidden','aria-disabled']});
    document.addEventListener('input',refresh);
    document.addEventListener('change',refresh);
    mobile.addEventListener('change',adapt);
    adapt();
    document.querySelector('.skip-link').addEventListener('click',event=>{event.preventDefault();anchor.scrollIntoView({block:'start'});anchor.focus({preventScroll:true});});
  }

  function init() {
    const themeButton = document.getElementById("themeBtn");
    if (themeButton) themeButton.addEventListener("click", toggleTheme);
    setTheme(activeTheme());
    void loadFreshness();
    syncPressed();
    syncSortHeaders();
    initResponsiveLayout();
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
    paginate,
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
