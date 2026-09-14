import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CommodityViewsTests(unittest.TestCase):
    def js(self, code):
        return json.loads(subprocess.check_output(['node','-e',code],text=True))

    def test_optional_feed_failure_and_column_alignment_preserve_equities(self):
        module=(ROOT/'assets/market-commodities.js').read_text()
        result=self.js("const window={};let requests=0;const fetch=async()=>{requests++;throw Error('offline')};"+module+"""
(async()=>{
 const base={columns:['symbol','close'],markets:{IN:{timeframes:{daily:{rows:[['ABC',12]]}}}}};
 const extra={ht:{columns:['close','symbol','price_unit'],markets:{MCX:{timeframes:{daily:{rows:[[102,'GOLD1!','INR / 10 g']]}}}}}};
 const merged=window.MarketCommodities.merge(base,'ht',extra);
 await Promise.all([window.MarketCommodities.load(),window.MarketCommodities.load()]);
 console.log(JSON.stringify({merged,base,requests,fallback:window.MarketCommodities.merge(base,'ht')===base}));
})();
""")
        self.assertEqual(result['requests'],1)
        self.assertTrue(result['fallback'])
        self.assertEqual(result['base']['columns'],['symbol','close'])
        self.assertEqual(result['merged']['markets']['IN']['timeframes']['daily']['rows'],[['ABC',12,None]])
        self.assertEqual(result['merged']['markets']['MCX']['timeframes']['daily']['rows'],[['GOLD1!',102,'INR / 10 g']])

    def test_combined_shortlist_needs_no_equity_rotation_or_cash_liquidity(self):
        script=(ROOT/'templates/clusters.html').read_text().split('<script>')[1].split('function bind(')[0]
        result=self.js("const document={querySelector:()=>null};const MarketRotation={available:()=>false,industry:()=>'',classification:r=>r.sector};"+script+"""
state.market='CM';state.timeframe='weekly';state.liquidity=10000000;
DATA={rows:[...Array.from({length:24},(_,i)=>({symbol:'C'+i,market:i%2?'MCX':'US_COM',timeframe:'weekly',ht2of3:true,ht_vt:i<2,sector:'Metals'})),{symbol:'STOCK',market:'IN',timeframe:'weekly',ht_vt:true}]};
const before=selected();state.query='C23';const after=selected();
console.log(JSON.stringify({count:before.length,markets:[...new Set(before.map(r=>r.market))],stocks:before.some(r=>r.symbol==='STOCK'),stable:after.every(r=>before.some(x=>x.symbol===r.symbol))}));
""")
        self.assertEqual(result['count'],20)
        self.assertEqual(set(result['markets']),{'MCX','US_COM'})
        self.assertFalse(result['stocks'])
        self.assertTrue(result['stable'])

    def test_market_order_and_shared_asset_are_rendered(self):
        shortlist=(ROOT/'templates/clusters.html').read_text()
        self.assertLess(shortlist.index('data-v="IN"'),shortlist.index('data-v="US"'))
        self.assertLess(shortlist.index('data-v="US"'),shortlist.index('data-v="CM"'))
        for name in ['clusters','tsha_hbcs','volume_trend']:
            html=(ROOT/'templates'/f'{name}.html').read_text()
            self.assertIn('market-commodities.js',html)
            self.assertIn('id="commodityStatus"',html)
        for name in ['tsha_hbcs','volume_trend']:
            html=(ROOT/'templates'/f'{name}.html').read_text()
            self.assertIn('data-v="MCX"',html)
            self.assertIn('data-v="US_COM"',html)


if __name__=='__main__':
    unittest.main()
