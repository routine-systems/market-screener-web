from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ShortlistIchimokuUITests(unittest.TestCase):
    def test_source_cutoff_direction_history_and_top20(self):
        source=(ROOT/'templates/clusters.html').read_text().split('<script>')[1].split('function bind(')[0]
        setup="const document={querySelector:()=>null};const MarketRotation={industry:()=>'',available:()=>true,lookup:()=>({status:1}),classification:r=>r.sector||''};"
        harness=r'''
const assert=require('node:assert/strict');
const row=(symbol,signal,turnover,event='EXIT')=>({symbol,signal,event,exchange:'NSE',market:'IN',timeframe:'daily',signal_date:'2026-10-06',sector:'Tech',median_dollar_turnover_20:turnover});
const current=[...Array.from({length:25},(_,i)=>row('B'+String(i).padStart(2,'0'),'BUY',100-i)),row('S','SELL',1000,'FOLLOW_THROUGH')];
const daily={data_cutoff:'2026-10-06',data_session:'2026-10-06',periods:[{date:'2026-10-05',rows:[{...current.at(-1),event:'EXIT',signal_date:'2026-10-05'},row('OLD','BUY',2000)]},{date:'2026-10-06',rows:current}]};
ICHIMOKU={markets:{IN:{timeframes:{daily,weekly:{...daily,data_cutoff:'2026-09-28',periods:[]}}}}};
DATA={rows:[{symbol:'HT',market:'IN',timeframe:'daily',ht2of3:true}],cutoffs:{IN:{daily:'2026-10-05',weekly:'2026-10-05'}}};
assert.equal(state.direction,'BUY');assert.deepEqual(selected().map(r=>r.symbol),['HT']);
state.source='ichimoku';assert.equal(liveDate(),'2026-10-06');assert.equal(selected().length,20);assert.ok(selected().every(r=>r.signal==='BUY'));assert.ok(!bucketRows().some(r=>r.symbol==='OLD'));
state.query='B24';assert.equal(selected().length,0);state.query='';state.direction='SELL';assert.deepEqual(selected().map(r=>r.symbol),['S']);
assert.equal(bucketRows()[0].appearance_bits,'11');assert.equal(bucketRows()[0].follow_through_bits,'01');assert.ok(qualification(bucketRows()[0]).includes('dot follow-through'));assert.ok(qualification(bucketRows()[0]).includes('Follow-through'));
state.direction='all';assert.equal(selected().length,20);assert.equal(selected()[0].symbol,'S');
const saved={...bucketRows().find(r=>r.symbol==='S'),rotation_bucket:'other'};
HISTORY.IN={sources:{ichimoku:{daily:{periods:[{date:'2026-10-01',data_session:'2026-10-01',source:'captured',selection_mode:'sector_top20.v1',selections:{BUY:[],SELL:[saved],all:[saved]}}]}}}};
state.period='2026-10-01';state.direction='SELL';state.sectorTab='other';assert.deepEqual(selected().map(r=>r.symbol),['S']);state.sectorTab='rising';assert.equal(selected().length,0);state.direction='BUY';assert.equal(bucketRows().length,0);
state.period='latest';state.timeframe='weekly';assert.equal(liveDate(),'2026-09-28');state.source='ht';assert.equal(liveDate(),'2026-10-05');
'''
        result=subprocess.run(['node','-e',setup+source+harness],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
