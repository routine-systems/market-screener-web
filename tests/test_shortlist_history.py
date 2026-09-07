import base64
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class HistoryTests(unittest.TestCase):
    def test_api_is_market_scoped_read_only(self):
        url='data:text/javascript;base64,'+base64.b64encode((ROOT/'functions/api/shortlist-history.js').read_bytes()).decode()
        script=f'''import {{onRequestGet}} from {json.dumps(url)};
const calls=[];const env={{SCANLINKS:{{get:async(key)=>{{calls.push(key);return {{schema_version:'shortlist-history.snapshot.v1',market:key.endsWith('IN')?'IN':'US',timeframes:{{}}}}}}}}}};
const results=[];for(const market of ['IN','US','all']){{const response=await onRequestGet({{env,request:new Request('https://screener.chiragpatnaik.com/api/shortlist-history?market='+market)}});results.push(response.status)}}
console.log(JSON.stringify({{calls,results}}));'''
        r=json.loads(subprocess.check_output(['node','--input-type=module','-e',script],text=True))
        self.assertEqual(r['calls'],['shortlist-history:v1:IN','shortlist-history:v1:US'])
        self.assertEqual(r['results'],[200,200,400])

    def test_date_selection_filters_and_latest_restore(self):
        page=(ROOT/'templates/clusters.html').read_text();script=page.split('<script>')[1].split('function bind(')[0]
        fixture='''
const elements=new Map();document.querySelector=s=>{if(!elements.has(s))elements.set(s,{textContent:'',innerHTML:'',disabled:false,querySelector:()=>null});return elements.get(s)};
DATA={rows:[{market:'IN',timeframe:'daily',symbol:'LIVE',ht2of3:true,ht3of5:false,ht_vt:false,median_dollar_turnover_20:30}],cutoffs:{IN:{daily:'2026-09-07',weekly:'2026-09-07'},US:{daily:'2026-09-04',weekly:'2026-08-31'}}};
HISTORY.IN={timeframes:{daily:{periods:[{date:'2026-03-02',data_session:'2026-03-02',source:'reconstructed',rows:[{symbol:'OLD',ht2of3:true,ht3of5:true,ht_vt:true,median_dollar_turnover_20:10}]}]},weekly:{periods:[]}}};
HISTORY.US={timeframes:{daily:{periods:[]},weekly:{periods:[]}}};
state.period='2026-03-02';const old=selected().map(r=>r.symbol);const flags=qualification(bucketRows()[0],3);state.query='LIVE';const filtered=selected().length;state.query='';state.period='latest';const latest=selected().map(r=>r.symbol);state.market='US';state.period='2026-03-02';const us=bucketRows();
console.log(JSON.stringify({old,flags,filtered,latest,us}));
'''
        prefix="const document={querySelector:()=>null};const MarketRotation={industry:()=>'',classification:r=>r.sector||'',marker:()=>'',cell:()=>''};\n"
        r=json.loads(subprocess.check_output(['node','-e',prefix+script+fixture],text=True))
        self.assertEqual(r['old'],['OLD']);self.assertEqual(r['filtered'],0);self.assertEqual(r['latest'],['LIVE']);self.assertEqual(r['us'],[])
        self.assertIn('Yes',r['flags']);self.assertNotIn('class="dot',r['flags'])

    def test_history_controls_and_fallback_are_in_rendered_template(self):
        s=(ROOT/'templates/clusters.html').read_text()
        for expected in ['historyPrev','historyNext','historyLatest','historyDate','Saved history unavailable','Reconstructed historical top 20']:
            self.assertIn(expected,s)
        self.assertIn('state.period=\'latest\'',s)

if __name__=='__main__':unittest.main()
