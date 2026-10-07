import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../functions/api/ichimoku.js',import.meta.url),'utf8');
const {onRequestGet}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
test('Ichimoku reads only its independent KV key',async()=>{
 let key;const response=await onRequestGet({env:{SCANLINKS:{get:async value=>{key=value;return {schema_version:'ichimoku.snapshot.v1',markets:{IN:{}}}}}}});
 assert.equal(key,'ichimoku:v1:latest');assert.equal(response.status,200);assert.equal((await response.json()).schema_version,'ichimoku.api.v1');
});
test('unavailable, invalid and failed storage never fabricate signals',async()=>{
 for(const [env,status] of [[{},500],[{SCANLINKS:{get:async()=>null}},503],[{SCANLINKS:{get:async()=>({})}},503],[{SCANLINKS:{get:async()=>{throw Error('private internal details')}}},500]]){
  const r=await onRequestGet({env});assert.equal(r.status,status);assert.equal((await r.json()).snapshot,undefined);
 }
});
