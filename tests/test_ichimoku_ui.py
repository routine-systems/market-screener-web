import json
from pathlib import Path
import re
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class IchimokuUITests(unittest.TestCase):
    def test_direction_event_histories_and_calendar_join(self):
        source=re.findall(r'<script>(.*?)</script>',(ROOT/'templates/ichimoku.html').read_text(),re.S)[0].split('function bind(')[0]
        harness=r'''
const assert=require('node:assert/strict');
const row=(symbol,date,signal,event)=>({market:'IN',timeframe:'daily',exchange:'NSE',symbol,signal_date:date,signal,event,sector:'Tech'});
DATA={markets:{IN:{timeframes:{daily:{periods:[
{date:'2026-10-01',rows:[row('A','2026-10-01','BUY','EXIT'),row('A','2026-10-01','SELL','EXIT')]},
{date:'2026-10-05',rows:[row('A','2026-10-05','BUY','FOLLOW_THROUGH')]},
{date:'2026-10-06',rows:[row('A','2026-10-06','BUY','EXIT')]}
]},weekly:{periods:[{date:'2026-09-28',rows:[row('A','2026-09-28','BUY','EXIT')]}]}}}}};
state.from=0;state.to=2;
let rows=historyRows(bucket());assert.equal(rows.length,1);
assert.equal(rows[0].appearance_bits,'111');assert.equal(rows[0].follow_through_bits,'010');assert.equal(rows[0].appearance_count,3);
assert.ok(appearanceCell(rows[0]).includes('dot follow-through'));assert.ok(appearanceCell(rows[0]).includes('● 05 Oct 2026 · Follow-through'));
assert.ok(rows.every(r=>r.signal==='BUY'&&r.linked));
state.direction='SELL';rows=historyRows(bucket());assert.equal(rows.length,1);assert.equal(rows[0].appearance_bits,'100');assert.equal(rows[0].linked,false);
state.direction='all';assert.equal(historyRows(bucket()).length,2);
state.direction='BUY';assert.equal(historyRows(bucket()).length,1);
state.from=1;assert.equal(historyRows(bucket())[0].linked,false);
assert.equal(periodLabel('2026-09-28'),'28 Sep 2026');
'''
        result=subprocess.run(['node','-e',source+'\n'+harness],capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr)

    def test_csv_contains_every_filtered_row_and_sanitizes_spreadsheet_formulas(self):
        page=(ROOT/'templates/ichimoku.html').read_text()
        source=re.findall(r'<script>(.*?)</script>',page,re.S)[0]
        declarations=source.split('function bind(')[0]
        export=source[source.index("$('#download').addEventListener"):source.index('async function load(')]
        harness=r"""
const assert=require('node:assert/strict');
DATA={markets:{IN:{timeframes:{daily:{periods:[{date:'2026-10-06'}]}}}}};
lastRows=Array.from({length:121},(_,i)=>({market:'IN',timeframe:'daily',symbol:i===0?'=formula':`SYM${i}`,appearance_periods:['2026-10-05','2026-10-06'],appearance_bits:'01',follow_through_bits:'01'}));
handlers.click();
(async()=>{const content=await csvBlob.text();assert.equal(content.split('\n').length,122);assert.ok(content.includes("'=formula"));assert.ok(content.includes('SYM120'));assert.ok(content.includes('2026-10-05|2026-10-06'))})();
"""
        setup="const handlers={};let csvBlob;const document={querySelector:()=>({addEventListener:(type,fn)=>handlers[type]=fn}),createElement:()=>({click(){}})};URL.createObjectURL=blob=>{csvBlob=blob;return 'blob:test'};URL.revokeObjectURL=()=>{};"
        result=subprocess.run(['node','-e',setup+declarations+export+harness],capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr)

    def test_bounce_controls_removed_and_legacy_snapshot_rejected(self):
        page=(ROOT/'templates/ichimoku.html').read_text()
        self.assertNotIn('Bounce',page)
        self.assertNotIn('id="events"',page)
        self.assertIn('ichimoku-exit-follow-through.v3',page)
        self.assertIn('Follow-through: next candle closes further',page)
