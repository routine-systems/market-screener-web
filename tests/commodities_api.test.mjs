import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';

const source = await readFile(new URL('../functions/api/commodities.js',import.meta.url),'utf8');
const {validSnapshot,onRequestGet} = await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
function fixture() {
  const result={schema_version:'commodities.snapshot.v1',generated_at_utc:'2026-09-12T02:00:00Z',snapshot_sha256:'a'.repeat(64),shortlist:[],coverage:{MCX:{status:'available'}}};
  for(const kind of ['ht','vt']) {
    result[kind]={schema_version:kind==='ht'?'tsha-hbcs.snapshot.v1':'volume-trend.snapshot.v1',columns:['market','symbol'],markets:{MCX:{data_session:'2026-09-11',timeframes:{}}}};
    for(const [timeframe,day] of [['daily','2026-09-11'],['weekly','2026-09-07']]) {
      result[kind].markets.MCX.timeframes[timeframe]={signal_date:day,shortlist_size:1,rows:[['MCX','GOLD1!']],appearance_periods:[day],appearance_bits:{'GOLD1!':'1'},
        history:{schema_version:kind+'-history.v1',instrument_columns:['symbol','exchange'],instruments:[['GOLD1!','MCX']],row_columns:['instrument_index'],periods:[{date:day,source:'replay',rows:[[0]]}]}};
    }
  }
  return result;
}
test('rejects misaligned histories, invalid identities and cross-timeframe cutoffs',()=>{
  assert.equal(validSnapshot(fixture()),true);
  for(const mutate of [s=>s.ht.markets.MCX.timeframes.weekly.history.periods[0].rows[0][0]=12,
                       s=>s.ht.markets.MCX.timeframes.daily.appearance_bits['GOLD1!']='0x',
                       s=>s.vt.markets.MCX.timeframes.daily.signal_date='2026-09-10',
                       s=>s.ht.markets.MCX.timeframes.weekly.history.periods[0].date='2026-09-08']) {
    const s=fixture();mutate(s);assert.equal(validSnapshot(s),false);
  }
});
test('read-only endpoint reports unavailable independently and reads the dedicated key',async()=>{
  let key;
  const response=await onRequestGet({env:{SCANLINKS:{get:async k=>{key=k;return fixture()}}}});
  assert.equal(response.status,200);assert.equal(key,'commodities:v1:latest');
  assert.equal((await onRequestGet({env:{}})).status,503);
  assert.equal((await onRequestGet({env:{SCANLINKS:{get:async()=>null}}})).status,503);
});
