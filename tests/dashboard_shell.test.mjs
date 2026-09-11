import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';

function harness(view) {
  const nodes = new Map();
  const field = key => {
    if (!nodes.has(key)) nodes.set(key, {options:[], value:'', listeners:{},
      addEventListener(name,fn){this.listeners[name]=fn;},
      set innerHTML(value){this.options=[...value.matchAll(/<option /g)];}});
    return nodes.get(key);
  };
  const nav={querySelector:field,setAttribute(){},addEventListener(name,fn){this[name]=fn;}};
  const document={readyState:'loading',documentElement:{setAttribute(){}},body:{dataset:{dashboardView:view}},
    createElement(){return nav;},querySelector(){return {after(){},scrollTop:0};},addEventListener(){}};
  const window={};
  vm.runInNewContext(readFileSync(new URL('../assets/dashboard-shell.js',import.meta.url),'utf8'),{document,window,localStorage:{getItem(){return null;}},matchMedia(){return {matches:false};},Intl,Date,Set});
  return {api:window.DashboardShell,window,nav,field};
}

for (const view of ['ht','us-weekly']) test(`${view}: every ranked row is reachable, narrowing and size changes reset the page`,()=>{
  const h=harness(view), rows=Array.from({length:1331},(_,rank)=>({rank,symbol:`S${rank}`}));
  let current=rows, shown;
  h.window.render=(first,second)=>{shown=h.api.paginate(current,view==='ht'?second:first);};
  shown=h.api.paginate(rows);
  assert.equal(shown.length,100);
  const visited=[...shown];
  for(let page=1;page<14;page++){
    h.nav.click({target:{closest(){return {dataset:{page:'next'}};}}});
    visited.push(...shown);
  }
  assert.deepEqual(visited,rows);
  assert.equal(h.field('[data-page-range]').textContent,'Rows 1301–1331 of 1331');
  assert.equal(h.field('[data-page="last"]').disabled,true);
  current=rows.filter(row=>row.rank%3===0);
  shown=h.api.paginate(current);
  assert.equal(shown[0],rows[0]);
  assert.equal(h.field('[data-page-select]').value,'0');
  h.field('[data-page-size]').listeners.change({target:{value:'250'}});
  assert.equal(shown.length,250);
  assert.equal(shown[249],current[249]);
  h.api.paginate([]);
  assert.equal(h.field('[data-page-range]').textContent,'0 rows');
  assert.equal(h.field('[data-page="next"]').disabled,true);
});
