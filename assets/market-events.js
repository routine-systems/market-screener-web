(() => {
  "use strict";

  const state = {
    datasets: new Map(),
    defaultMarket: null,
    card: null,
    pinnedKey: null,
    closeTimer: null,
  };

  const escapeHtml = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (character) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[character],
    );

  const safeUrl = (value) => {
    try {
      const url = new URL(String(value));
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
    } catch {
      return null;
    }
  };

  function install() {
    if (state.card) return;
    const style = document.createElement("style");
    style.textContent = `
      .event-dot{appearance:none!important;display:inline-block!important;width:9px!important;height:9px!important;min-width:9px!important;padding:0!important;margin:0 0 0 6px!important;border:0!important;border-radius:50%!important;background:var(--ink)!important;box-shadow:0 0 0 1px var(--surface),0 0 0 2px var(--ink)!important;vertical-align:middle!important;cursor:pointer!important}
      .event-dot:hover,.event-dot:focus-visible{transform:scale(1.25);outline:2px solid var(--vol)!important;outline-offset:2px}
      #market-event-card{position:fixed;z-index:120;width:min(390px,calc(100vw - 16px));max-height:min(520px,calc(100vh - 16px));overflow:auto;background:var(--surface);color:var(--ink);border:1px solid var(--axis);border-radius:8px;box-shadow:0 12px 34px rgba(0,0,0,.24);padding:12px;white-space:normal;text-align:left;font:12px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
      #market-event-card[hidden]{display:none}
      .event-card-head{display:flex;align-items:flex-start;gap:10px;padding-bottom:8px;border-bottom:1px solid var(--grid)}
      .event-card-head strong{font-size:14px}.event-card-head .event-card-meta{color:var(--muted);margin-top:2px}.event-card-pin{margin-left:auto;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.04em}
      .event-card-row{padding:9px 0;border-bottom:1px solid var(--grid)}.event-card-row:last-of-type{border-bottom:0}.event-card-title{font-weight:700}.event-card-side{display:inline-block;margin-left:5px;font-size:9px;letter-spacing:.04em;color:var(--ink-2)}
      .event-card-when,.event-card-amount{color:var(--ink-2);margin-top:2px}.event-card-source{margin-top:3px}.event-card-source a{color:var(--vol);text-decoration:none}.event-card-source a:hover{text-decoration:underline}.event-card-foot{color:var(--muted);font-size:10.5px;padding-top:7px}
    `;
    document.head.appendChild(style);
    state.card = document.createElement("aside");
    state.card.id = "market-event-card";
    state.card.hidden = true;
    state.card.setAttribute("role", "dialog");
    state.card.setAttribute("aria-label", "Ticker transaction history");
    document.body.appendChild(state.card);

    const cancelClose = () => {
      if (state.closeTimer) window.clearTimeout(state.closeTimer);
      state.closeTimer = null;
    };
    const scheduleClose = () => {
      cancelClose();
      if (state.pinnedKey) return;
      state.closeTimer = window.setTimeout(hide, 180);
    };

    document.addEventListener("pointerover", (event) => {
      const dot = event.target.closest?.("[data-event-symbol]");
      if (!dot || state.pinnedKey) return;
      cancelClose();
      show(dot, false);
    });
    document.addEventListener("pointerout", (event) => {
      const dot = event.target.closest?.("[data-event-symbol]");
      if (!dot || state.card.contains(event.relatedTarget)) return;
      scheduleClose();
    });
    document.addEventListener("focusin", (event) => {
      const dot = event.target.closest?.("[data-event-symbol]");
      if (dot && !state.pinnedKey) show(dot, false);
    });
    document.addEventListener("focusout", (event) => {
      if (event.target.closest?.("[data-event-symbol]")) scheduleClose();
    });
    document.addEventListener("click", (event) => {
      const dot = event.target.closest?.("[data-event-symbol]");
      if (dot) {
        event.preventDefault();
        event.stopPropagation();
        const symbol = dot.dataset.eventSymbol;
        const market = dot.dataset.eventMarket || state.defaultMarket;
        const key = `${market}:${symbol}`;
        if (state.pinnedKey === key) {
          state.pinnedKey = null;
          hide();
        } else {
          state.pinnedKey = key;
          show(dot, true);
        }
        return;
      }
      if (!state.card.contains(event.target)) {
        state.pinnedKey = null;
        hide();
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      state.pinnedKey = null;
      hide();
    });
    state.card.addEventListener("pointerenter", cancelClose);
    state.card.addEventListener("pointerleave", scheduleClose);
  }

  function normalizedMarket(market) {
    const normalized = String(market || "").toUpperCase();
    return new Set(["IN", "US"]).has(normalized) ? normalized : null;
  }

  function dataset(market) {
    const normalized = normalizedMarket(market) || state.defaultMarket;
    return normalized ? state.datasets.get(normalized) || null : null;
  }

  function record(symbol, market) {
    return dataset(market)?.snapshot?.records?.[String(symbol).trim().toUpperCase()] || null;
  }

  function dot(symbol, market) {
    const normalized = String(symbol).trim().toUpperCase();
    const eventMarket = normalizedMarket(market) || state.defaultMarket;
    const entry = record(normalized, eventMarket);
    if (!entry) return "";
    const kind = eventMarket === "IN" ? "bulk deal" : "political transaction";
    const count = Number(entry.count) || 0;
    const label = `${normalized}: ${count} ${kind}${count === 1 ? "" : "s"} in complete history`;
    return `<button type="button" class="event-dot" data-event-market="${eventMarket}" data-event-symbol="${escapeHtml(normalized)}" aria-label="${escapeHtml(label)}" title="${escapeHtml(label)}"></button>`;
  }

  function field(row, name, market) {
    const index = dataset(market)?.columns.get(name);
    return index === undefined ? null : row[index];
  }

  function formatNumber(value, digits = 0) {
    const number = Number(value);
    if (value == null || !Number.isFinite(number)) return null;
    return number.toLocaleString("en-IN", { maximumFractionDigits: digits });
  }

  function formatMoney(value, market) {
    const number = formatNumber(value, 2);
    if (number === null) return null;
    return `${market === "IN" ? "₹" : "$"}${number}`;
  }

  function eventHtml(row, market) {
    const actor = field(row, "actor", market) || "Actor not stated";
    const side = field(row, "side", market);
    const eventDate = field(row, "event_date", market) || "Date not stated";
    const reportedAt = field(row, "reported_at", market);
    const shares = formatNumber(field(row, "shares", market), 4);
    const value = formatMoney(field(row, "value", market), market);
    const price = formatMoney(field(row, "price", market), market);
    const source = field(row, "source", market) || "Source not stated";
    const sourceUrl = safeUrl(field(row, "url", market));
    const amount = [
      shares === null ? null : `${shares} shares`,
      value === null ? null : `${value} value`,
      price === null ? null : `${price} per share`,
    ].filter(Boolean);
    const reportDate = reportedAt ? ` · reported ${escapeHtml(String(reportedAt).slice(0, 10))}` : "";
    const sourceMarkup = sourceUrl
      ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener">${escapeHtml(source)} ↗</a>`
      : escapeHtml(source);
    return `<div class="event-card-row"><div class="event-card-title">${escapeHtml(actor)}${side ? `<span class="event-card-side">${escapeHtml(side)}</span>` : ""}</div><div class="event-card-when">Transaction ${escapeHtml(eventDate)}${reportDate}</div><div class="event-card-amount">${amount.length ? amount.join(" · ") : "amount not stated in source"}</div><div class="event-card-source">${sourceMarkup}</div></div>`;
  }

  function cardHtml(symbol, entry, pinned, market) {
    const count = Number(entry.count) || 0;
    const events = Array.isArray(entry.events) ? entry.events : [];
    const kind = market === "IN" ? "bulk deals" : "political transactions";
    const span = entry.first_date && entry.last_date
      ? `${entry.first_date} → ${entry.last_date}`
      : "stored history";
    const detail = events.map((event) => eventHtml(event, market)).join("");
    const truncated = count > events.length
      ? `Showing latest ${events.length} of ${count} events.`
      : `Showing all ${count} stored event${count === 1 ? "" : "s"}.`;
    return `<div class="event-card-head"><div><strong>${escapeHtml(symbol)}</strong><div class="event-card-meta">${count.toLocaleString("en-IN")} ${kind} · ${escapeHtml(span)}</div></div><span class="event-card-pin">${pinned ? "Pinned" : "Click to pin"}</span></div>${detail}<div class="event-card-foot">${escapeHtml(truncated)} Marker scope: complete history.</div>`;
  }

  function show(dotElement, pinned) {
    const symbol = dotElement.dataset.eventSymbol;
    const market = dotElement.dataset.eventMarket || state.defaultMarket;
    const entry = record(symbol, market);
    if (!entry) return;
    state.card.innerHTML = cardHtml(symbol, entry, pinned, market);
    state.card.hidden = false;
    const anchor = dotElement.getBoundingClientRect();
    const box = state.card.getBoundingClientRect();
    let left = anchor.left;
    let top = anchor.bottom + 8;
    if (left + box.width > window.innerWidth - 8) left = window.innerWidth - box.width - 8;
    if (top + box.height > window.innerHeight - 8) top = anchor.top - box.height - 8;
    state.card.style.left = `${Math.max(8, left)}px`;
    state.card.style.top = `${Math.max(8, top)}px`;
  }

  function hide() {
    if (!state.card) return;
    state.card.hidden = true;
    state.card.innerHTML = "";
  }

  async function load(market, onReady) {
    install();
    const normalized = normalizedMarket(market);
    if (!normalized || location.protocol === "file:") return null;
    try {
      const response = await fetch(`/api/market-events?market=${normalized}`, {
        headers: { accept: "application/json" },
      });
      const payload = await response.json().catch(() => ({}));
      const snapshot = payload.snapshot;
      if (
        !response.ok ||
        payload.schema_version !== "market-events.api.v1" ||
        snapshot?.schema_version !== "market-events.snapshot.v1" ||
        snapshot?.market !== normalized ||
        snapshot?.history_scope !== "complete" ||
        !Array.isArray(snapshot?.event_columns) ||
        !snapshot?.records
      ) {
        throw new Error(payload.error || `HTTP ${response.status}`);
      }
      state.defaultMarket = normalized;
      state.datasets.set(normalized, {
        snapshot,
        columns: new Map(snapshot.event_columns.map((name, index) => [name, index])),
      });
      if (typeof onReady === "function") onReady(snapshot);
      return snapshot;
    } catch (error) {
      console.warn("Market-event context unavailable", error);
      return null;
    }
  }

  window.MarketEvents = Object.freeze({ load, dot, record });
})();
