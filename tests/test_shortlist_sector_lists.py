import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SectorShortlistTests(unittest.TestCase):
    def run_js(self, body):
        script = (
            (ROOT / "templates/clusters.html")
            .read_text()
            .split("<script>")[1]
            .split("function bind(")[0]
        )
        prefix = """const document={querySelector:()=>null};let available=true;
const MarketRotation={available:()=>available,lookup:(symbol,market,sector)=>({status:sector==='Rising'?1:sector==='Cooling'?-1:0}),industry:()=>'',classification:r=>r.sector||''};
"""
        return json.loads(
            subprocess.check_output(["node", "-e", prefix + script + body], text=True)
        )

    def test_independent_caps_ranking_and_sort_filter_stability_all_buckets(self):
        result = self.run_js(
            """
const checked=[];
for(const market of ['IN','US'])for(const timeframe of ['daily','weekly']){
 state.market=market;state.timeframe=timeframe;state.period='latest';state.query='';state.cohort='all';state.sort='ht_vt';state.desc=true;
 DATA={rows:['Rising','Cooling'].flatMap(sector=>Array.from({length:25},(_,i)=>({symbol:sector+i,market,timeframe,sector,ht_vt:i<3,ht3of5:i<10,ht2of3:true,median_dollar_turnover_20:25-i,close:i})))};
 const lists=sectorLists();state.sectorTab='rising';const initial=selected().map(r=>r.symbol);
 state.sort='close';state.desc=true;const sorted=selected().map(r=>r.symbol);
 state.query='Rising24';const filtered=selected().length;
 checked.push({market,timeframe,lengths:[lists.rising.length,lists.other.length],first:initial.slice(0,4),same:initial.toSorted().join()===sorted.toSorted().join(),filtered,overlap:lists.rising.some(r=>lists.other.some(o=>o.symbol===r.symbol))});
}
console.log(JSON.stringify(checked));
"""
        )
        for row in result:
            self.assertEqual(row["lengths"], [20, 20])
            self.assertEqual(row["first"], ["Rising0", "Rising1", "Rising2", "Rising3"])
            self.assertTrue(row["same"])
            self.assertEqual(row["filtered"], 0)
            self.assertFalse(row["overlap"])

    def test_no_filling_missing_rotation_and_saved_membership(self):
        r = self.run_js(
            """
DATA={rows:[{symbol:'A',market:'IN',timeframe:'daily',sector:'Rising',ht2of3:true},{symbol:'B',market:'IN',timeframe:'daily',ht2of3:true}]};
const small=sectorLists();available=false;const missing=sectorLists();available=true;
state.period='2026-09-07';HISTORY.IN={timeframes:{daily:{periods:[{date:state.period,selection_mode:'sector_top20.v1',rows:[{symbol:'OLD',sector:'Cooling',rotation_bucket:'rising',ht_vt:true}]}]}}};
const saved=selected().map(r=>r.symbol);const valid=validHistoryRows(activePeriod());
console.log(JSON.stringify({small,missing,saved,valid}));
"""
        )
        self.assertEqual([len(r["small"][k]) for k in ["rising", "other"]], [1, 1])
        self.assertEqual(r["missing"], {"rising": [], "other": []})
        self.assertEqual(r["saved"], ["OLD"])
        self.assertTrue(r["valid"])

    def test_five_dated_dots_and_reconstructed_flags(self):
        r = self.run_js(
            """
const dates=['2026-08-10','2026-08-17','2026-08-24','2026-08-31','2026-09-07'];
console.log(JSON.stringify({dots:qualification({appearance_bits:'11001',appearance_periods:dates,ht3of5:true,ht2of3:false}),flags:qualification({ht2of3:true,ht3of5:false})}));
"""
        )
        self.assertEqual(r["dots"].count('class="dot '), 5)
        self.assertIn("○ 31 Aug 2026", r["dots"])
        self.assertIn("● 07 Sept 2026", r["dots"])
        self.assertIn("HT 3/5", r["dots"])
        self.assertNotIn("HT 2/3", r["dots"])
        self.assertIn("HT 2/3", r["flags"])
        self.assertNotIn('class="dot ', r["flags"])
