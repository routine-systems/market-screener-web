/* Isolated optional futures transport. Equity snapshot failures stay independent. */
(() => {
  'use strict';
  const markets = ['MCX', 'US_COM'];
  let pending, snapshot = null, error = '';
  const isMarket = market => markets.includes(market);
  const label = market => ({IN:'India', US:'US', MCX:'MCX', US_COM:'US Commodities', CM:'Commodities'}[market] || market);
  async function load() {
    if (!pending) pending = (async () => {
      try {
        const response = await fetch('/api/commodities', {headers:{accept:'application/json'}, signal:AbortSignal.timeout(15000)});
        const body = await response.json();
        if (!response.ok || body.schema_version !== 'commodities.api.v1' || body.snapshot?.schema_version !== 'commodities.snapshot.v1') {
          throw new Error(body.error || 'Commodity history unavailable');
        }
        snapshot = body.snapshot;
        window.MarketConsolidation?.register(snapshot.vt);
      } catch {
        error = 'Commodity history is not available yet.';
      }
      return snapshot;
    })();
    return pending;
  }
  function merge(base, kind, extra = snapshot) {
    const source = extra?.[kind];
    if (!source) return base;
    const columns = [...new Set([...base.columns, ...source.columns])];
    const result = {...base, columns, markets:{}};
    for (const [key, market] of Object.entries({...base.markets, ...source.markets})) {
      const original = isMarket(key) ? source.columns : base.columns;
      const indexes = columns.map(column => original.indexOf(column));
      result.markets[key] = {...market, timeframes:{}};
      for (const [timeframe, bucket] of Object.entries(market.timeframes)) {
        result.markets[key].timeframes[timeframe] = {...bucket,
          rows:bucket.rows.map(row => indexes.map(index => index < 0 ? null : row[index]))};
      }
    }
    return result;
  }
  function note(market) {
    if (!snapshot) return error || 'Loading commodity history…';
    const selected = isMarket(market) ? [market] : markets;
    const dates = selected.map(key => {
      const coverage = snapshot.coverage?.[key];
      const stale = Object.entries(coverage?.stale_symbols || {}).map(([symbol, day]) => `${symbol} ${day}`).join(', ');
      return `${label(key)} ${coverage?.data_session || 'unavailable'}${coverage?.status === 'partial' ? ' · incomplete coverage' : ''}${stale ? ` (${stale})` : ''}`;
    });
    return `${dates.join(' · ')} · Unadjusted continuous futures · ${snapshot.chart_parity === 'verified' ? 'Chart parity checked' : 'Source-series preview; chart parity pending'}`;
  }
  function scope(state) {
    const commodity = isMarket(state.market) || state.market === 'CM';
    const control = document.querySelector('#liquidity');
    if (control) control.hidden = commodity;
    const status = document.querySelector('#commodityStatus');
    if (status) {
      const show = commodity || state.market === 'all';
      status.hidden = !show;
      status.textContent = show ? note(state.market) : '';
    }
    const updated = document.querySelector('#updated');
    if (updated && commodity && snapshot) {
      if (!updated.dataset.commodityActive) updated.dataset.equityUpdated = updated.textContent;
      updated.dataset.commodityActive = '1';
      const captured = state.market === 'CM' && state.period !== 'latest'
        ? snapshot.shortlist_history?.timeframes?.[state.timeframe]?.periods?.find(period => period.date === state.period) : null;
      const when = new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Kolkata', dateStyle:'medium', timeStyle:'short', hour12:false}).format(new Date(captured?.generated_at_utc || snapshot.generated_at_utc));
      updated.textContent = `Last updated ${when} IST`;
    } else if (updated?.dataset.commodityActive) {
      updated.textContent = updated.dataset.equityUpdated;
      delete updated.dataset.commodityActive;
    }
    const footer = document.querySelector('#foot');
    if (footer && document.querySelector('#sectorTabs')) {
      if (commodity) {
        if (!footer.dataset.equityText) footer.dataset.equityText = footer.textContent;
        footer.textContent = 'Up to 20 combined MCX + US commodities · HT + VT, then HT 3/5, then HT 2/3 · Ties use symbol · Futures volume is in contracts; equity sector rotation and turnover filters do not apply';
      } else if (footer.dataset.equityText) footer.textContent = footer.dataset.equityText;
    }
    // Never describe lots × quoted price as comparable cash turnover.
    document.querySelectorAll('th[data-k="median_dollar_turnover_20"]').forEach(th => {
      th.title = commodity ? 'Cash-equivalent turnover is unavailable; futures volume is in contracts.' : '';
    });
    if (commodity && (!snapshot || (isMarket(state.market) && !snapshot.ht?.markets?.[state.market]))) {
      const hint = document.querySelector('#rankhint');
      if (hint) hint.textContent = `${label(state.market)} history unavailable. This is not a zero-signal result.`;
    }
  }
  const rows = () => snapshot?.shortlist || [];
  const cutoff = timeframe => markets.map(m => snapshot?.ht?.markets?.[m]?.timeframes?.[timeframe]?.signal_date).filter(Boolean).sort().at(-1) || '';
  const capturedHistory = () => snapshot?.shortlist_history;
  // Quote precision removes provider floating-point noise without losing ticks.
  const precision = row => row.asset_type !== 'futures' ? 2 :
    ({'GC1!':1,'SI1!':3,'HG1!':4,'PL1!':1,'PA1!':1,'CL1!':2,'NG1!':3,'RB1!':4,'HO1!':4,
      'ZC1!':2,'ZW1!':2,'ZS1!':2,'ZM1!':1,'ZL1!':2,'KC1!':2,'CC1!':0,'SB1!':2,'CT1!':2,'LE1!':3,'HE1!':3}[row.symbol] ?? 2);
  window.MarketCommodities = {capturedHistory, load, merge, isMarket, label, note, scope, rows, cutoff, precision};
})();
