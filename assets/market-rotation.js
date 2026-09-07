(() => {
  'use strict';
  const datasets = new Map(), loading = new Map();
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const word = status => status > 0 ? 'rotating in (rising)' : status < 0 ? 'rotating out (cooling)' : 'flat';
  function lookup(symbol, market, fallbackSector = '') {
    const data = datasets.get(market);
    if (!data) return null;
    // The shared US classification is authoritative even for funds/unresolved rows.
    const sector = market === 'US' && data.hasProfiles
      ? data.profiles[symbol]?.sector
      : data.rotation?.of?.[symbol]?.[0] || fallbackSector;
    const status = data.rotation?.status?.sector?.[sector];
    return sector && Number.isFinite(status) ? {group:sector,status} : null;
  }
  function industry(symbol, fallback = '') { return datasets.get('US')?.profiles?.[symbol]?.industry || fallback || ''; }
  function classification(row) { return row.market === 'US' ? industry(row.symbol, row.industry) : row.sector || ''; }
  function dot(group, status, current = false) {
    if (!group || !Number.isFinite(status)) return '';
    const text = `${group} — ${word(status)}${current?" · current weekly rotation":""}`;
    return `<span class="rot rotation-marker ${status>0?'up':status<0?'down':'flat'}" tabindex="0" role="img" aria-label="${esc(text)}" title="${esc(text)}" data-rotation-tip="${esc(text)}"></span>`;
  }
  function marker(symbol, market, sector = '') {
    return `<span class="rotation-slot" data-rotation-symbol="${esc(symbol)}" data-rotation-market="${esc(market)}" data-rotation-sector="${esc(sector)}"></span>`;
  }
  function cell(row) {
    return row.market === 'US' ? `<span data-industry-symbol="${esc(row.symbol)}">${esc(industry(row.symbol,row.industry)||'—')}</span>` : esc(row.sector||'—');
  }
  function register(market, rotation, metadata) {
    const profiles = Object.create(null);
    if (metadata?.columns && metadata?.rows) {
      for (const values of metadata.rows) {
        const row = Object.fromEntries(metadata.columns.map((key,index)=>[key,values[index]]));
        profiles[row.symbol] = row;
      }
    }
    datasets.set(market,{rotation,profiles,hasProfiles:!!metadata});
    scan();
    document.dispatchEvent(new CustomEvent('market-rotation-ready',{detail:{market}}));
  }
  async function load(market) {
    if (datasets.has(market) || loading.has(market)) return loading.get(market);
    const pending = (async()=>{
      try {
        const response = await fetch(market==='US'?'/api/us-trend-bounce?context=1':'/india-rotation.json');
        if (!response.ok) return;
        const value = await response.json();
        if (market==='US') register(market,value.rotation,value.security_metadata);
        else register(market,value.rotation);
      } catch { /* Unavailable rotation must not masquerade as flat. */ }
    })();
    loading.set(market,pending);
    return pending;
  }
  function scan() {
    document.querySelectorAll('[data-rotation-symbol]').forEach(node=>{
      const {rotationSymbol:symbol,rotationMarket:market,rotationSector:sector} = node.dataset;
      if (!['IN','US'].includes(market)) return;
      if (!datasets.has(market)) { load(market); return; }
      const item=lookup(symbol,market,sector), html=item?dot(item.group,item.status,true):'';
      if (node.innerHTML!==html) node.innerHTML=html;
    });
    document.querySelectorAll('[data-industry-symbol]').forEach(node=>{
      const text=industry(node.dataset.industrySymbol);
      if (text && node.textContent!==text) node.textContent=text;
    });
  }
  function install() {
    const tip=document.createElement('div'); tip.id='rotation-tooltip'; tip.setAttribute('role','tooltip'); tip.setAttribute('aria-hidden','true'); tip.hidden=true; document.body.append(tip);
    const hide=()=>{tip.hidden=true;tip.setAttribute('aria-hidden','true')};
    function show(node,x,y) {
      tip.textContent=node.dataset.rotationTip; tip.hidden=false; tip.setAttribute('aria-hidden','false');
      const box=tip.getBoundingClientRect();
      tip.style.left=Math.max(8,Math.min(x+12,innerWidth-box.width-8))+'px';
      tip.style.top=Math.max(8,Math.min(y+16,innerHeight-box.height-8))+'px';
    }
    document.addEventListener('pointerover',event=>{const node=event.target.closest?.('[data-rotation-tip]');if(node)show(node,event.clientX,event.clientY)});
    document.addEventListener('pointerout',event=>{if(event.target.closest?.('[data-rotation-tip]'))hide()});
    document.addEventListener('focusin',event=>{const node=event.target.closest?.('[data-rotation-tip]');if(node){const box=node.getBoundingClientRect();show(node,box.left,box.bottom)}});
    document.addEventListener('focusout',hide);document.addEventListener('keydown',event=>{if(event.key==='Escape')hide()});
    let scheduled=false;
    new MutationObserver(()=>{if(!scheduled){scheduled=true;requestAnimationFrame(()=>{scheduled=false;scan()})}}).observe(document.querySelector('main')||document.body,{childList:true,subtree:true});
    scan();
  }
  window.MarketRotation={dot,marker,lookup,industry,classification,cell,register,load};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install);else install();
})();
