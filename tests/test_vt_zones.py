import json
import subprocess
import unittest
from pathlib import Path

from test_render_site import javascript_function

SOURCE = (Path(__file__).resolve().parents[1] / 'templates/volume_trend.html').read_text()


class LockedZoneTests(unittest.TestCase):
    def test_endpoint_membership_break_direction_counts_and_pagination(self):
        functions = '\n'.join(javascript_function(SOURCE, name) for name in ('buildZoneRows', 'compareRows', 'paginate'))
        script = r'''
const assert=require('node:assert/strict');
const state={direction:'INSIDE',sort:'inside_count',desc:true,page:0,pageSize:100};
FUNCTIONS
const row=(symbol,signal,date,count,start='2026-08-01')=>({symbol,exchange:'NSE',signal,signal_date:date,inside_count:count,zone_started:start});
const history={periods:[
 {date:'2026-08-03',rows:[row('A','INSIDE','2026-08-03',40),row('B','INSIDE','2026-08-03',12)]},
 {date:'2026-08-04',rows:[row('A','BUY','2026-08-04',40),row('B','INSIDE','2026-08-04',13)]},
 {date:'2026-08-05',rows:[row('A','INSIDE','2026-08-05',1,'2026-08-05'),row('B','SELL','2026-08-05',13)]}
]};
let result=buildZoneRows(history,0,1,'IN','daily');
assert.deepEqual(result.map(r=>r.symbol),['B']); // A already broke at endpoint.
assert.equal(result[0].inside_count,13); // Not restricted to selected two periods.
result=buildZoneRows(history,0,2,'IN','daily');
assert.deepEqual(result.map(r=>r.symbol),['A']);
assert.equal(result[0].appearance_bits,'001'); // An older zone cannot pad the dots.
state.direction='BUY';
result=buildZoneRows(history,0,2,'IN','daily');
assert.equal(result[0].symbol,'A');
assert.equal(result[0].inside_count,40); // Preserve count on break despite later re-entry.
assert.equal(result[0].signal_date,'2026-08-04');
assert.equal(result[0].appearance_bits,'100');
state.direction='SELL';
result=buildZoneRows(history,0,2,'IN','daily');
assert.equal(result[0].symbol,'B');
assert.equal(result[0].inside_count,13);
const many=Array.from({length:251},(_,i)=>({symbol:String(i),inside_count:i+1})).sort(compareRows);
assert.equal(paginate(many).shown[0].inside_count,251);
state.page=2;assert.equal(paginate(many).shown.at(-1).inside_count,1);
state.desc=false;many.sort(compareRows);state.page=0;
assert.equal(paginate(many).shown[0].inside_count,1);
'''.replace('FUNCTIONS', functions)
        subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)
