import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../assets/market-consolidation.js',import.meta.url),'utf8');
function subject(fetch){const context={window:{},fetch,document:{readyState:'loading',addEventListener(){}}};vm.runInNewContext(source,context);return context.window.MarketConsolidation;}
const instrument_columns=['symbol','exchange'];
const row_columns=['instrument_index','signal','inside_count','volume_bar_low','volume_bar_high','zone_started'];
const zone=(periods,instruments=[['SAME','NSE']])=>({schema_version:'vt-locked-zones.v1',instrument_columns,row_columns,instruments,periods:periods.map(([date,rows])=>({date,rows}))});
const row=(date,overrides={})=>({symbol:'SAME',exchange:'NSE',market:'IN',timeframe:'daily',signal_date:date,...overrides});
const snapshot=history=>({markets:{IN:{timeframes:{daily:{locked_zones:history}}}}});
const history=zone([
 ['2026-09-01',[[0,'INSIDE',23,90,100,'2026-08-01']]],
 ['2026-09-02',[[0,'BUY',23,90,100,'2026-08-01']]],
 ['2026-09-03',[]],
 ['2026-09-04',[[0,'INSIDE',1,99,105,'2026-09-04']]],
 ['2026-09-07',[[0,'SELL',1,99,105,'2026-09-04']]],
 ['2026-09-08',[]],
]);
test('active count is causal, break retains count, later empty period retains completed run, new lock replaces it',()=>{
 const api=subject();api.register(snapshot(history));
 assert.match(api.describe(row('2026-09-01')),/Consolidating · 23 trading days/);
 assert.doesNotMatch(api.describe(row('2026-09-01')),/Broke/);
 assert.match(api.describe(row('2026-09-03')),/Consolidated · 23 trading days\nBroke above · 02 Sept 2026/);
 assert.match(api.describe(row('2026-09-04')),/Consolidating · 1 trading day/);
 assert.match(api.describe(row('2026-09-08')),/Consolidated · 1 trading day\nBroke below · 07 Sept 2026/);
 assert.equal(api.lookup(row('2026-08-31')),null);
});
test('market, exchange and timeframe identities do not leak counts',()=>{
 const api=subject();api.register(snapshot(history));
 for(const overrides of [{market:'US'},{timeframe:'weekly'},{exchange:'BSE'},{symbol:'MISSING'}]) assert.equal(api.lookup(row('2026-09-01',overrides)),null);
 assert.match(api.describe(row('2026-09-01',{market:'US'})),/Unavailable/);
});
test('separate commodity and equity refreshes preserve each others zone context',()=>{
 const api=subject();
 const commodities={markets:{MCX:{timeframes:{daily:{locked_zones:zone([['2026-09-01',[[0,'INSIDE',4,90,100,'2026-08-27']]]],[['GOLD1!','MCX']])}}}}};
 api.register(commodities);api.register(snapshot(history));
 assert.equal(api.lookup(row('2026-09-01')).inside_count,23);
 const gold=row('2026-09-01',{market:'MCX',exchange:'MCX',symbol:'GOLD1!'});
 assert.equal(api.lookup(gold).inside_count,4);
 api.register(commodities);
 assert.equal(api.lookup(row('2026-09-01')).inside_count,23);
 assert.equal(api.lookup({...gold,market:'US_COM'}),null);
});
test('missing observation never carries forward an active consolidation',()=>{
 const api=subject();api.register(snapshot(zone([['2026-09-01',[[0,'INSIDE',23,90,100,'2026-08-01']]],['2026-09-02',[]]])));
 assert.equal(api.lookup(row('2026-09-02')),null);
});
test('weekly context uses completed weeks and labels the cutoff when HT shows a partial week',()=>{
 const api=subject();api.register({markets:{IN:{timeframes:{weekly:{locked_zones:zone([['2026-08-24',[[0,'INSIDE',7,90,100,'2026-07-13']]],['2026-08-31',[[0,'INSIDE',8,90,100,'2026-07-13']]]])}}}}});
 const text=api.describe(row('2026-09-07',{timeframe:'weekly'}));assert.match(text,/Consolidating · 8 weeks/);assert.match(text,/Through week of 31 Aug 2026 · completed weeks only/);
 assert.equal(api.lookup(row('2026-08-28',{timeframe:'weekly'})).inside_count,7);
 assert.equal(api.lookup(row('2026-08-31',{timeframe:'weekly',consolidation_asof:'2026-09-02'})).inside_count,7);
 assert.equal(api.lookup(row('2026-08-31',{timeframe:'weekly',consolidation_asof:'2026-09-04'})).inside_count,8);
});
test('stale daily data is explicitly dated; missing blocks and invalid counts are unavailable',()=>{
 const api=subject();api.register(snapshot(history));assert.match(api.describe(row('2026-09-09')),/Consolidation data trails this row/);
 api.register(snapshot(zone([['2026-09-01',[[0,'INSIDE',null,90,100,'2026-08-01']]]])));assert.equal(api.lookup(row('2026-09-01')),null);
 api.register({});assert.match(api.describe(row('2026-09-01')),/Unavailable/);
});
test('attributes escape symbol and date content without changing the ticker destination',()=>{
 const api=subject();const text=api.attributes(row('2026-09-01',{symbol:'\"><script>',exchange:'X&Y'}));assert.doesNotMatch(text,/<script>/);assert.match(text,/&quot;&gt;&lt;script&gt;/);assert.match(text,/X&amp;Y/);assert.doesNotMatch(text,/href=/);
});
test('HT context loads once and failures leave explicit unavailable context',async()=>{
 let calls=0;const api=subject(async url=>{calls++;assert.equal(url,'/api/volume-trend?context=consolidation');return {ok:true,json:async()=>({schema_version:'volume-trend.api.v1',snapshot:snapshot(history)})};});await Promise.all([api.load(),api.load()]);await api.load();assert.equal(calls,1);assert.equal(api.lookup(row('2026-09-01')).inside_count,23);
 const broken=subject(async()=>{throw new Error('offline')});await broken.load();assert.match(broken.describe(row('2026-09-01')),/Unavailable/);
});
const apiSource=readFileSync(new URL('../functions/api/volume-trend.js',import.meta.url),'utf8');
const {onRequestGet}=await import('data:text/javascript;base64,'+Buffer.from(apiSource).toString('base64'));
test('context API reads existing KV once and omits unrelated events; full snapshot is unchanged',async()=>{
 let calls=0;const stored=snapshot(history);stored.columns=['large event payload'];stored.markets.IN.timeframes.daily.rows=['event rows'];const env={SCANLINKS:{getWithMetadata:async(key)=>{calls++;assert.equal(key,'volume-trend:v1:latest');return {value:stored,metadata:{revision:1}};}}};
 const request=url=>new Request('https://screener.chiragpatnaik.com/api/volume-trend'+url);
 const response=await onRequestGet({env,request:request('?context=consolidation')});const body=await response.json();assert.equal(calls,1);assert.deepEqual(body.snapshot.markets.IN.timeframes.daily.locked_zones,history);assert.equal(body.snapshot.columns,undefined);assert.equal(body.snapshot.markets.IN.timeframes.daily.rows,undefined);
 const full=await(await onRequestGet({env,request:request('')})).json();assert.deepEqual(full.snapshot,stored);
});
