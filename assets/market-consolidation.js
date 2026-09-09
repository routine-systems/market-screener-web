(() => {
  'use strict';
  const buckets = new Map();
  let loading = null, ready = false, refreshTip = () => {};
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const key = (symbol, exchange) => JSON.stringify([symbol, exchange || '']);
  const weekStart = date => {
    const d = new Date(`${date}T00:00:00Z`);
    if (!Number.isFinite(d.getTime())) return '';
    d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7);
    return d.toISOString().slice(0, 10);
  };
  function register(snapshot) {
    buckets.clear();
    for (const market of ['IN', 'US']) for (const timeframe of ['daily', 'weekly']) {
      const history = snapshot?.markets?.[market]?.timeframes?.[timeframe]?.locked_zones;
      if (history?.schema_version !== 'vt-locked-zones.v1' || !Array.isArray(history.periods) || !history.periods.length) continue;
      if (!Array.isArray(history.instrument_columns) || !Array.isArray(history.row_columns) || !Array.isArray(history.instruments)) continue;
      const instruments = history.instruments.map(values => Object.fromEntries(history.instrument_columns.map((column, i) => [column, values[i]])));
      const periods = [...history.periods].sort((a, b) => a.date.localeCompare(b.date));
      const records = new Map();
      for (const period of periods) for (const values of period.rows || []) {
        const row = Object.fromEntries(history.row_columns.map((column, i) => [column, values[i]]));
        const instrument = instruments[row.instrument_index];
        if (!instrument?.symbol || !['INSIDE', 'BUY', 'SELL'].includes(row.signal) || !Number.isInteger(row.inside_count) || row.inside_count < 1) continue;
        if (!(Number.isFinite(row.volume_bar_low) && Number.isFinite(row.volume_bar_high) && row.volume_bar_low > 0 && row.volume_bar_low <= row.volume_bar_high)) continue;
        const identity = key(instrument.symbol, instrument.exchange);
        if (!records.has(identity)) records.set(identity, []);
        records.get(identity).push({...row, date: period.date});
      }
      buckets.set(`${market}:${timeframe}`, {dates: periods.map(p => p.date), records});
    }
    ready = true;
    refreshTip();
  }
  function lookup(row) {
    const bucket = buckets.get(`${row.market}:${row.timeframe}`);
    const date = row.timeframe === 'weekly' ? weekStart(row.signal_date) : row.signal_date;
    if (!bucket || !date || date < bucket.dates[0]) return null;
    // Saved weekly Shortlists can be midweek captures. A later Friday close
    // must never enter their hover, even though both rows share a Monday label.
    const asof = bucket.dates.filter(value => {
      if (value > date) return false;
      if (row.timeframe !== 'weekly' || !row.consolidation_asof) return true;
      const friday = new Date(`${value}T00:00:00Z`);
      friday.setUTCDate(friday.getUTCDate() + 4);
      return friday.toISOString().slice(0, 10) <= row.consolidation_asof;
    }).at(-1);
    if (!asof) return null;
    // Never carry an earlier inside state over a missing observation.
    const observations = bucket.records.get(key(row.symbol, row.exchange)) || [];
    const latest = observations.filter(value => value.date <= asof).at(-1);
    if (!latest || (latest.signal === 'INSIDE' && latest.date !== asof)) return null;
    return {...latest, asof, requested: date, timeframe: row.timeframe};
  }
  const formatDate = date => new Intl.DateTimeFormat('en-GB', {timeZone:'UTC', day:'2-digit', month:'short', year:'numeric'}).format(new Date(`${date}T00:00:00Z`));
  const number = value => Number(value).toLocaleString(undefined, {maximumFractionDigits: 2});
  function describe(row) {
    const value = lookup(row);
    const timeframe = row.timeframe === 'weekly' ? 'Weekly' : 'Daily';
    if (!value) return `${timeframe} consolidation\n${ready ? 'Unavailable for this row in the stored zone history.' : 'Loading consolidation context…'}`;
    const units = value.timeframe === 'weekly' ? (value.inside_count === 1 ? 'week' : 'weeks') : (value.inside_count === 1 ? 'trading day' : 'trading days');
    const lines = [`${timeframe} consolidation`, `${value.signal === 'INSIDE' ? 'Consolidating' : 'Consolidated'} · ${value.inside_count} ${units}`];
    if (value.signal !== 'INSIDE') lines.push(`Broke ${value.signal === 'BUY' ? 'above' : 'below'} · ${value.timeframe === 'weekly' ? 'week of ' : ''}${formatDate(value.date)}`);
    lines.push(`Zone low ${number(value.volume_bar_low)} · high ${number(value.volume_bar_high)}`);
    if (value.zone_started) lines.push(`Tracked since ${formatDate(value.zone_started)}`);
    lines.push(value.timeframe === 'weekly' ? `Through week of ${formatDate(value.asof)} · completed weeks only` : `As of ${formatDate(value.asof)}`);
    if (value.asof < value.requested && value.timeframe === 'daily') lines.push('Consolidation data trails this row.');
    return lines.join('\n');
  }
  function attributes(row) {
    return `data-consolidation-symbol="${esc(row.symbol)}" data-consolidation-exchange="${esc(row.exchange)}" data-consolidation-market="${esc(row.market)}" data-consolidation-timeframe="${esc(row.timeframe)}" data-consolidation-date="${esc(row.signal_date)}" data-consolidation-asof="${esc(row.consolidation_asof)}"`;
  }
  async function load() {
    if (ready) return;
    if (loading) return loading;
    loading = (async () => {
      try {
        const response = await fetch('/api/volume-trend?context=consolidation', {headers:{accept:'application/json'}});
        const body = await response.json();
        if (!response.ok || body.schema_version !== 'volume-trend.api.v1' || !body.snapshot) throw new Error('Unavailable context');
        register(body.snapshot);
      } catch { ready = true; refreshTip(); }
    })();
    return loading;
  }
  function install() {
    const style = document.createElement('style');
    style.textContent = '#consolidation-tooltip{position:fixed;z-index:60;pointer-events:none;background:var(--ink);color:var(--surface);padding:8px 10px;border-radius:7px;font:12px/1.5 system-ui;white-space:pre-line;max-width:min(310px,calc(100vw - 32px));box-sizing:border-box;overflow-wrap:anywhere}';
    document.head.append(style);
    const tip = document.createElement('div');
    tip.id = 'consolidation-tooltip'; tip.setAttribute('role', 'tooltip'); tip.setAttribute('aria-hidden', 'true'); tip.hidden = true;
    document.body.append(tip);
    let active = null;
    const rowFor = node => ({symbol:node.dataset.consolidationSymbol, exchange:node.dataset.consolidationExchange, market:node.dataset.consolidationMarket, timeframe:node.dataset.consolidationTimeframe, signal_date:node.dataset.consolidationDate, consolidation_asof:node.dataset.consolidationAsof});
    function hide() {
      if (active) active.removeAttribute('aria-describedby');
      active = null; tip.hidden = true; tip.setAttribute('aria-hidden', 'true');
    }
    function show(node) {
      if (active && active !== node) active.removeAttribute('aria-describedby');
      active = node;
      tip.textContent = describe(rowFor(node)); tip.hidden = false; tip.setAttribute('aria-hidden', 'false');
      node.setAttribute('aria-describedby', tip.id);
      const anchor = node.getBoundingClientRect(), box = tip.getBoundingClientRect();
      tip.style.left = Math.max(8, Math.min(anchor.left, innerWidth - box.width - 8)) + 'px';
      tip.style.top = Math.max(8, Math.min(anchor.bottom + 8, innerHeight - box.height - 8)) + 'px';
    }
    refreshTip = () => { if (active?.isConnected) show(active); else hide(); };
    const selector = 'a[data-consolidation-symbol]';
    document.addEventListener('pointerover', event => { const node = event.target.closest?.(selector); if (node) show(node); });
    document.addEventListener('pointerout', event => { if (event.target.closest?.(selector) && !event.relatedTarget?.closest?.(selector)) hide(); });
    document.addEventListener('focusin', event => { const node = event.target.closest?.(selector); if (node) show(node); });
    document.addEventListener('focusout', hide);
    document.addEventListener('keydown', event => { if (event.key === 'Escape') hide(); });
    document.addEventListener('scroll', () => { if (active && document.activeElement === active) show(active); else hide(); }, true);
    window.addEventListener('resize', hide);
    new MutationObserver(() => { if (active && !active.isConnected) hide(); }).observe(document.querySelector('main') || document.body, {childList:true, subtree:true});
  }
  window.MarketConsolidation = {register, lookup, describe, attributes, load};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install); else install();
})();
