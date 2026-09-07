import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../functions/api/us-trend-bounce.js',import.meta.url),'utf8');
const {onRequestGet}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
test('context response supplies full-universe metadata without signal histories',async()=>{
 const snapshot={rotation:{status:{sector:{Technology:1}}},security_metadata:{columns:['symbol','sector','industry'],rows:[['ONLYHT','Technology','Software']]},pages:{weekly:{weeks:['large history']}}};
 const env={SCANLINKS:{getWithMetadata:async()=>({value:snapshot})}};
 const response=await onRequestGet({env,request:new Request('https://screener.chiragpatnaik.com/api/us-trend-bounce?context=1')});
 assert.equal(response.status,200);const body=await response.json();assert.deepEqual(body.security_metadata,snapshot.security_metadata);assert.deepEqual(body.rotation,snapshot.rotation);assert.equal(body.pages,undefined);
});
