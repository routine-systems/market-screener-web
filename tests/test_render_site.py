import base64
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

    def decode_rendered_payload(self, page):
        match = re.search(
            r'(?:const (?:HISTORY|MARKET|SECTOR)_B64=|b64utf8\()"([^"]+)"',
            page,
        )
        self.assertIsNotNone(match)
        return json.loads(base64.b64decode(match.group(1)))

    def test_valid_fixture_renders_eight_pages_and_manifest(self):
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
                "us-weekly.html",
                "us-daily.html",
                "index.html",
                "build-manifest.json",
                "dashboard-freshness.json",
                "dashboard-shell.css",
                "dashboard-shell.js",
                "market-events.js",
                "functions/_middleware.js",
                "functions/api/market-events.js",
                "functions/api/refresh.js",
                "functions/api/scanlink.js",
                "functions/api/tsha-hbcs.js",
                "functions/api/us-trend-bounce.js",
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
            for name in (
                "dashboard.html",
                "daily.html",
                "market.html",
                "sectors.html",
                "recommendations.html",
            ):
                payload = self.decode_rendered_payload((output / name).read_text())
                self.assertEqual("11 Aug 2026, 17:30 IST", payload["last_updated_ist"])
            self.assertIn(
                "fetch('/api/tsha-hbcs'", (output / "tsha_hbcs.html").read_text()
            )
            self.assertTrue((output / "functions").exists())

    def test_build_requires_an_explicit_immutable_bundle(self):
        completed = subprocess.run(
            [ROOT / "scripts" / "build"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(64, completed.returncode)
        self.assertIn("immutable-signals-bundle.v1.json", completed.stderr)

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
            self.assertIn("<h1>HT Confirmations</h1>", page)
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
            self.assertIn('id="updated">Last updated —', page)
            self.assertIn("function formatIst(value)", page)
            self.assertIn("India data through", page)
            self.assertIn("US data through", page)
            self.assertNotIn('data-k="name">Name</th>', page)
            self.assertNotIn("${esc(r.name||r.symbol)}</td>", page)
            self.assertNotIn("Locally computed database screener", page)
            self.assertNotIn("Twin Smoothed HA + HBCS", page)
            self.assertNotIn("Completed-bar confluence", page)

    def test_render_injects_page_freshness_and_ist_timestamp(self):
        bundle = self.load_fixture()
        bundle["source_freshness"] = {
            "daily": {"as_of": "2026-08-11"},
            "market": {"as_of": "2026-08-11"},
            "sectors": {"as_of": "2026-08-10"},
            "weekly": {"as_of": "2026-08-10"},
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bundle.json"
            output = Path(directory) / "dist"
            source.write_text(json.dumps(bundle))
            render_site.render_site(source, output)
            expectations = {
                "dashboard.html": ("2026-08-10", "Data through"),
                "daily.html": ("2026-08-11", "Data through"),
                "market.html": ("2026-08-11", "Data through"),
                "sectors.html": ("2026-08-10", "Data through"),
                "recommendations.html": ("2026-08-10", "Data through"),
            }
            for name, (as_of, label) in expectations.items():
                page = (output / name).read_text()
                payload = self.decode_rendered_payload(page)
                self.assertEqual("11 Aug 2026, 17:30 IST", payload["last_updated_ist"])
                self.assertEqual(as_of, payload["data_as_of"])
                self.assertIn(label, page)

    def test_format_ist_handles_midnight_rollover(self):
        self.assertEqual(
            "01 Jan 2027, 05:00 IST",
            render_site._format_ist("2026-12-31T23:30:00Z"),
        )

    def test_generated_timestamp_requires_timezone(self):
        bundle = self.load_fixture()
        bundle["generated_at_utc"] = "2026-08-11T12:00:00"
        with self.assertRaisesRegex(
            render_site.BundleError, "must include a timezone offset"
        ):
            render_site.validate_bundle(bundle)

    def test_ht_format_ist_rejects_missing_timezone(self):
        page = (ROOT / "templates" / "tsha_hbcs.html").read_text()
        start = page.index("function formatIst(")
        end = page.index("\nfunction showTip(", start)
        function_source = page[start:end]
        script = f"""
{function_source}
console.log(JSON.stringify({{
  valid:formatIst('2026-08-18T16:07:23Z'),
  missing:formatIst(null),
  naive:formatIst('2026-08-18T16:07:23'),
}}));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual("18 Aug 2026, 21:37 IST", result["valid"])
        self.assertEqual("—", result["missing"])
        self.assertEqual("—", result["naive"])

    def test_shared_freshness_shell_writes_values_as_text(self):
        shell = (ROOT / "assets" / "dashboard-shell.js").read_text()
        self.assertIn('output.textContent = value || "—"', shell)
        self.assertNotIn("output.innerHTML", shell)

    def test_ht_appearance_dots_preserve_period_order(self):
        page = (ROOT / "templates" / "tsha_hbcs.html").read_text()
        start = page.index("function appearanceCell(r){")
        end = page.index("\nfunction sourceSummary(", start)
        function_source = page[start:end]
        label_start = page.index("const periodLabel=")
        label_end = page.index("\n", label_start)
        script = f"""
const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}}[c]));
{page[label_start:label_end]}
{function_source}
const mixed=appearanceCell({{appearance_periods:['2026-08-12','2026-08-13','2026-08-14'],appearance_bits:'101',appearance_count:2}});
const every=appearanceCell({{appearance_periods:['2026-08-12','2026-08-13','2026-08-14'],appearance_bits:'111',appearance_count:3}});
const missing=appearanceCell({{appearance_periods:[],appearance_bits:'',appearance_count:0}});
console.log(JSON.stringify({{mixed,every,missing}}));
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
        self.assertIn("● 12 Aug 2026", rendered["mixed"])
        self.assertIn("○ 13 Aug 2026", rendered["mixed"])
        self.assertLess(
            rendered["mixed"].index("12 Aug 2026"),
            rendered["mixed"].index("14 Aug 2026"),
        )
        self.assertEqual(3, rendered["every"].count('class="dot hot"'))
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
