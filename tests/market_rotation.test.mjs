import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
function subject(){const context={window:{},document:{readyState:'loading',addEventListener(){},dispatchEvent(){},querySelectorAll(){return[]}},CustomEvent:class {}};vm.runInNewContext(readFileSync(new URL('../assets/market-rotation.js',import.meta.url),'utf8'),context);return context.window.MarketRotation}
test('joins all stored US metadata to sector status without screener membership',()=>{
 const api=subject();api.register('US',{status:{sector:{Technology:1,Energy:-1,Financials:0}},of:{}},{columns:['symbol','sector','industry'],rows:[['ONLYHT','Technology','Semiconductors'],['OIL','Energy','Petroleum refining'],['BANK','Financials','Commercial banks']]});
 assert.equal(api.lookup('ONLYHT','US').status,1);assert.equal(api.lookup('OIL','US').status,-1);assert.equal(api.lookup('BANK','US').status,0);
 assert.equal(api.classification({symbol:'ONLYHT',market:'US',sector:'Technology'}),'Semiconductors');
 assert.equal(api.lookup('FUND','US','Technology'),null);
});
test('market isolation and missing status do not fabricate a flat marker',()=>{
 const api=subject();api.register('IN',{of:{SAME:['India sector'],UNKNOWN:['Missing']},status:{sector:{'India sector':-1}}});api.register('US',{status:{sector:{Technology:1}}},{columns:['symbol','sector','industry'],rows:[['SAME','Technology','Software']]});
 assert.equal(api.lookup('SAME','IN').status,-1);assert.equal(api.lookup('SAME','US').status,1);assert.equal(api.lookup('UNKNOWN','IN'),null);assert.equal(api.lookup('UNKNOWN','US'),null);
 assert.equal(api.classification({symbol:'SAME',market:'IN',sector:'India sector'}),'India sector');
});
test('shared marker retains India states, accessible hover and escaping',()=>{
 const api=subject();assert.match(api.dot('Tech & <test>',1),/Tech &amp; &lt;test&gt; — rotating in \(rising\)/);assert.match(api.dot('Energy',-1),/rotation-marker down/);assert.match(api.dot('Banks',0),/rotation-marker flat/);assert.match(api.dot('Banks',0),/tabindex="0" role="img"/);assert.equal(api.dot('No data',null),'');
 assert.doesNotMatch(api.marker('\"><script>','US'),/<script>/);
});
