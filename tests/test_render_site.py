import copy
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import render_site


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "signals-bundle.v1.json"


class RenderSiteTests(unittest.TestCase):
    def load_fixture(self):
        return json.loads(FIXTURE.read_text())

    def test_valid_fixture_renders_six_pages_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist"
            manifest = render_site.render_site(FIXTURE, output)
            expected = {
                "dashboard.html",
                "daily.html",
                "market.html",
                "sectors.html",
                "recommendations.html",
                "tsha_hbcs.html",
                "index.html",
                "build-manifest.json",
            }
            actual = {
                path.relative_to(output).as_posix()
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertEqual(expected, actual)
            self.assertEqual("fixture-commit", manifest["producer_commit"])
            self.assertIn("const WINDOW=8;", (output / "dashboard.html").read_text())
            self.assertNotIn("__HISTORY_B64__", (output / "dashboard.html").read_text())
            self.assertIn(
                "fetch('/api/tsha-hbcs'", (output / "tsha_hbcs.html").read_text()
            )
            self.assertFalse((output / "functions").exists())

    def test_all_six_pages_link_to_tsha_hbcs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist"
            render_site.render_site(FIXTURE, output)
            for name in (
                "dashboard.html",
                "daily.html",
                "market.html",
                "sectors.html",
                "recommendations.html",
                "tsha_hbcs.html",
            ):
                page = (output / name).read_text()
                self.assertIn('href="tsha_hbcs.html"', page)
                self.assertIn(">HT</a>", page)

    def test_ht_uses_shared_screener_shell_without_explainer(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist"
            render_site.render_site(FIXTURE, output)
            page = (output / "tsha_hbcs.html").read_text()
            self.assertIn("<h1>HT potentials</h1>", page)
            self.assertIn('class="tablecard"', page)
            self.assertIn('class="tablewrap"', page)
            self.assertIn('id="themeBtn"', page)
            self.assertIn("Appearances (oldest→newest)", page)
            self.assertIn("function appearanceCell(r)", page)
            self.assertIn('class="dots"', page)
            self.assertIn('id="tt" role="tooltip"', page)
            self.assertIn("Union potentials", page)
            self.assertIn("Latest period · ", page)
            self.assertIn("New in latest", page)
            self.assertIn("Every period · ", page)
            self.assertIn("India Daily", page)
            self.assertIn("US Weekly", page)
            self.assertNotIn('data-k="name">Name</th>', page)
            self.assertNotIn("${esc(r.name||r.symbol)}</td>", page)
            self.assertNotIn("Locally computed database screener", page)
            self.assertNotIn("Twin Smoothed HA + HBCS", page)
            self.assertNotIn("Completed-bar confluence", page)

    def test_ht_appearance_dots_preserve_period_order(self):
        page = (ROOT / "templates" / "tsha_hbcs.html").read_text()
        start = page.index("function appearanceCell(r){")
        end = page.index("\nfunction sourceSummary(", start)
        function_source = page[start:end]
        script = f"""
const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}}[c]));
{function_source}
const mixed=appearanceCell({{appearance_periods:['2026-08-12','2026-08-13','2026-08-14'],appearance_bits:'101',appearance_count:2}});
const every=appearanceCell({{appearance_periods:['2026-08-12','2026-08-13','2026-08-14'],appearance_bits:'111',appearance_count:3}});
const malicious=appearanceCell({{appearance_periods:['<img src=x onerror=alert(1)>'],appearance_bits:'1',appearance_count:1}});
const missing=appearanceCell({{appearance_periods:[],appearance_bits:'',appearance_count:0}});
console.log(JSON.stringify({{mixed,every,malicious,missing}}));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            check=True,
            capture_output=True,
            text=True,
        )
        rendered = json.loads(completed.stdout)
        self.assertIn("2<small>/3</small>", rendered["mixed"])
        self.assertEqual(3, rendered["mixed"].count('class="dot '))
        self.assertIn('data-tip="row"', rendered["mixed"])
        self.assertIn("2026-08-12: ●", rendered["mixed"])
        self.assertIn("2026-08-13: —", rendered["mixed"])
        self.assertLess(
            rendered["mixed"].index("2026-08-12"),
            rendered["mixed"].index("2026-08-14"),
        )
        self.assertEqual(3, rendered["every"].count('class="dot hot"'))
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", rendered["malicious"])
        self.assertNotIn("<img", rendered["malicious"])
        self.assertIn("—", rendered["missing"])

    def test_ht_appearance_hover_uses_weekly_tooltip_contract(self):
        page = (ROOT / "templates" / "tsha_hbcs.html").read_text()
        self.assertIn("#tt{position:fixed", page)
        self.assertIn("function showTip(text,x,y)", page)
        self.assertIn("tt.textContent=text", page)
        self.assertNotIn("tt.innerHTML=", page)
        self.assertIn("function hideTip()", page)
        self.assertIn("document.body.addEventListener('mousemove'", page)
        self.assertIn("target.dataset.w.split(' · ').join('\\n')", page)
        self.assertIn("document.body.addEventListener('mouseleave',hideTip)", page)

    def test_ht_history_missing_falls_back_and_range_unions_periods(self):
        page = (ROOT / "templates" / "tsha_hbcs.html").read_text()
        start = page.index("function buildHistoryRows(")
        end = page.index("\nfunction singleSelection()", start)
        function_source = page[start:end]
        script = f"""
{function_source}
const latest=[{{symbol:'LATEST'}}];
const history={{periods:[
  {{date:'2026-08-14',source:'replay',rows:[{{symbol:'ABC',close:10}},{{symbol:'XYZ',close:20}}]}},
  {{date:'2026-08-15',source:'stored',rows:[{{symbol:'ABC',close:12}},{{symbol:'NEW',close:30}}]}},
]}};
console.log(JSON.stringify({{
  fallback:rowsForView(latest,null,0,0,'IN','daily'),
  history:rowsForView(latest,history,0,1,'IN','daily'),
  stats:buildHistoryStats(history,0,1,'IN','daily'),
}}));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["fallback"], [{"symbol": "LATEST"}])
        by_symbol = {row["symbol"]: row for row in result["history"]}
        self.assertEqual(set(by_symbol), {"ABC", "XYZ", "NEW"})
        self.assertEqual(by_symbol["ABC"]["close"], 12)
        self.assertEqual(by_symbol["ABC"]["appearance_bits"], "11")
        self.assertEqual(by_symbol["XYZ"]["appearance_bits"], "10")
        self.assertEqual(by_symbol["NEW"]["appearance_bits"], "01")
        self.assertEqual(
            by_symbol["ABC"]["appearance_periods"],
            ["2026-08-14", "2026-08-15"],
        )
        self.assertEqual(result["stats"]["latestCount"], 2)
        self.assertEqual(result["stats"]["newCount"], 1)
        self.assertEqual(result["stats"]["everyCount"], 1)

    def test_ht_history_csv_uses_only_populated_history_columns(self):
        page = (ROOT / "templates" / "tsha_hbcs.html").read_text()
        constant_start = page.index("const HISTORY_EXPORT_COLUMNS=")
        constant_end = page.index(";", constant_start) + 1
        function_start = page.index("function csvColumns(")
        function_end = page.index("\nfunction singleSelection()", function_start)
        script = f"""
{page[constant_start:constant_end]}
{page[function_start:function_end]}
const latest=['market','name','industry','volume'];
console.log(JSON.stringify({{history:csvColumns({{}},latest),latest:csvColumns(null,latest)}}));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["latest"], ["market", "name", "industry", "volume"])
        self.assertIn("appearance_count", result["history"])
        self.assertIn("appearance_periods", result["history"])
        self.assertIn("appearance_bits", result["history"])
        self.assertIn("instrument_index", result["history"])
        self.assertNotIn("name", result["history"])
        self.assertNotIn("industry", result["history"])
        self.assertNotIn("volume", result["history"])

    def test_ht_browser_rejects_unknown_history_instrument(self):
        page = (ROOT / "templates" / "tsha_hbcs.html").read_text()
        start = page.index("function unpackHistory(")
        end = page.index("\nfunction unpack(snapshot)", start)
        function_source = page[start:end]
        script = f"""
{function_source}
const history={{schema_version:'ht-history.v1',instrument_columns:['symbol','exchange','asset_type','sector'],instruments:[['ABC','NSE','equity','Industrials']],row_columns:['instrument_index','hbcs_bull_component_count','hbcs_components','fast_body_pct','slow_body_pct','close','median_dollar_turnover_20'],periods:[{{date:'2026-08-18',source:'stored',rows:[[9,2,'HMM',1,1,100,2000000]]}}]}};
let error='';try{{unpackHistory(history,'IN','daily')}}catch(caught){{error=caught.message}}
console.log(JSON.stringify({{error}}));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            json.loads(completed.stdout)["error"], "Invalid history instrument"
        )

    def test_ht_browser_rejects_malformed_compact_row(self):
        page = (ROOT / "templates" / "tsha_hbcs.html").read_text()
        start = page.index("function unpackHistory(")
        end = page.index("\nfunction unpack(snapshot)", start)
        function_source = page[start:end]
        script = f"""
{function_source}
const history={{schema_version:'ht-history.v1',instrument_columns:['symbol','exchange','asset_type','sector'],instruments:[['ABC','NSE','equity','Industrials']],row_columns:['instrument_index','hbcs_bull_component_count','hbcs_components','fast_body_pct','slow_body_pct','close','median_dollar_turnover_20'],periods:[{{date:'2026-08-18',source:'stored',rows:[[0,2,'HMM']]}}]}};
let error='';try{{unpackHistory(history,'IN','daily')}}catch(caught){{error=caught.message}}
console.log(JSON.stringify({{error}}));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout)["error"], "Invalid history row")

    def test_ht_history_controls_have_arrows_and_fibonacci_presets(self):
        page = (ROOT / "templates" / "tsha_hbcs.html").read_text()
        self.assertIn('id="fromPeriod"', page)
        self.assertIn('id="toPeriod"', page)
        self.assertIn('id="rangeBack"', page)
        self.assertIn('id="rangeFwd"', page)
        self.assertIn(">◀</button>", page)
        self.assertIn(">▶</button>", page)
        self.assertEqual(
            re.findall(r'data-periods="(\d+)"', page), ["1", "3", "5", "8", "13"]
        )
        self.assertIn("state.market!=='all'&&state.timeframe!=='all'", page)
        self.assertIn("sourceSummary(selected)", page)
        self.assertIn('placeholder="Search symbol / sector…"', page)

    def test_ht_history_arrows_shift_a_fixed_window(self):
        page = (ROOT / "templates" / "tsha_hbcs.html").read_text()
        start = page.index("function shiftRange(")
        end = page.index("\nfunction render(", start)
        function_source = page[start:end]
        script = f"""
let state={{from:2,to:4}},renders=0;
const history={{periods:[0,1,2,3,4,5]}};
function selectedHistory(){{return history}}
function render(){{renders+=1}}
{function_source}
shiftRange(-1);
const older={{from:state.from,to:state.to}};
shiftRange(1);
shiftRange(1);
const newest={{from:state.from,to:state.to}};
console.log(JSON.stringify({{older,newest,renders}}));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["older"], {"from": 1, "to": 3})
        self.assertEqual(result["newest"], {"from": 3, "to": 5})
        self.assertEqual(result["renders"], 3)

    def test_rejects_unsupported_major_version(self):
        bundle = self.load_fixture()
        bundle["schema_version"] = "2.0"
        with self.assertRaisesRegex(
            render_site.BundleError, "unsupported schema_version"
        ):
            render_site.validate_bundle(bundle)

    def test_rejects_missing_page(self):
        bundle = self.load_fixture()
        del bundle["pages"]["daily"]
        with self.assertRaisesRegex(
            render_site.BundleError, "bundle misses pages: daily"
        ):
            render_site.validate_bundle(bundle)

    def test_rejects_artifact_path_traversal(self):
        bundle = self.load_fixture()
        bundle["artifacts"] = [
            {"path": "../private.parquet", "row_count": 1, "sha256": "0" * 64}
        ]
        with self.assertRaisesRegex(render_site.BundleError, "bundle-relative"):
            render_site.validate_bundle(bundle)

    def test_rejects_invalid_weekly_window(self):
        bundle = copy.deepcopy(self.load_fixture())
        bundle["pages"]["weekly"]["default_window"] = 0
        with self.assertRaisesRegex(render_site.BundleError, "positive integer"):
            render_site.validate_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
