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
HT_TEMPLATE = ROOT / "templates" / "tsha_hbcs.html"


def javascript_function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    body_start = source.index("{", start)
    depth = 0
    for position in range(body_start, len(source)):
        if source[position] == "{":
            depth += 1
        elif source[position] == "}":
            depth -= 1
            if depth == 0:
                return source[start : position + 1]
    raise AssertionError(f"unterminated JavaScript function: {name}")


class RenderSiteTests(unittest.TestCase):
    def test_navigation_groups_ranked_shortlists_before_context_pages(self):
        self.assertEqual(
            (
                ("shortlist", "shortlist.html", "Shortlist"),
                ("weekly", "dashboard.html", "Weekly"),
                ("daily", "daily.html", "Daily"),
                ("us-weekly", "us-weekly.html", "US Weekly"),
                ("us-daily", "us-daily.html", "US Daily"),
                ("ht", "tsha_hbcs.html", "HT"),
                ("vt", "volume_trend.html", "VT"),
                ("transactions", "transactions.html", "Trades"),
                ("market", "market.html", "Market"),
                ("sectors", "sectors.html", "Sectors"),
                ("recommendations", "recommendations.html", "Forward Test"),
            ),
            render_site.NAV_ITEMS,
        )

    def load_fixture(self):
        return json.loads(FIXTURE.read_text())

    def decode_rendered_payload(self, page):
        match = re.search(
            r'(?:const (?:HISTORY|MARKET|SECTOR)_B64=|b64utf8\()"([^"]+)"',
            page,
        )
        self.assertIsNotNone(match)
        return json.loads(base64.b64decode(match.group(1)))

    def test_valid_fixture_renders_eleven_pages_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist"
            manifest = render_site.render_site(FIXTURE, output)
            expected = {
                "shortlist.html",
                "dashboard.html",
                "daily.html",
                "market.html",
                "sectors.html",
                "recommendations.html",
                "tsha_hbcs.html",
                "volume_trend.html",
                "transactions.html",
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
                "functions/api/forward-test.js",
                "functions/api/refresh.js",
                "functions/api/scanlink.js",
                "functions/api/tsha-hbcs.js",
                "functions/api/us-trend-bounce.js",
                "functions/api/volume-trend.js",
            }
            actual = {
                path.relative_to(output).as_posix()
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertEqual(expected, actual)
            self.assertEqual("fixture-commit", manifest["producer_commit"])
            weekly = (output / "dashboard.html").read_text()
            self.assertIn("const WINDOW=8;", weekly)
            self.assertNotIn("__HISTORY_B64__", weekly)
            self.assertIn("weeks · ranking over", weekly)
            self.assertNotIn("in-scan links on", weekly)
            self.assertNotIn("source ↗", weekly)
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
            self.assertIn(
                "fetch('/api/volume-trend'", (output / "volume_trend.html").read_text()
            )
            transactions = (output / "transactions.html").read_text()
            self.assertIn("Transactions · India + U.S.", transactions)
            self.assertIn("`/api/market-events?market=${market}`", transactions)
            self.assertIn("function syncCoverage(", transactions)
            self.assertIn("market==='IN'?'en-IN':'en-US'", transactions)
            shortlist = (output / "shortlist.html").read_text()
            self.assertIn("India + US Weekly · Shortlist", shortlist)
            self.assertIn('data-view="now"', shortlist)
            self.assertIn("function isFreshBatch(", shortlist)
            self.assertIn(".slice(0,5)", shortlist)
            self.assertIn("_rank:old._rank", shortlist)
            self.assertIn("rankedBatch(row.market,row.signal_date)", shortlist)
            self.assertIn("Fresh / Returned this week", shortlist)
            self.assertIn("Continuing this week", shortlist)
            self.assertIn("function appearanceMeta(", shortlist)
            self.assertIn("FIRST_SEEN", shortlist)
            self.assertIn("batchesAway", shortlist)
            self.assertIn("rankMove", shortlist)
            self.assertIn("jsonFetch('/api/forward-test'", shortlist)
            self.assertIn("jsonFetch('/api/tsha-hbcs'", shortlist)
            self.assertIn("jsonFetch('/api/volume-trend'", shortlist)
            self.assertIn('url=shortlist.html', (output / "index.html").read_text())
            self.assertTrue((output / "functions").exists())

    def test_shortlist_classifies_first_returned_and_continuing_appearances(self):
        page = (ROOT / "templates" / "shortlist.html").read_text()
        appearance_meta = javascript_function(page, "appearanceMeta")
        script = f"""
const number=value=>value==null||value===''||Number.isNaN(Number(value))?null:Number(value);
const dates=['2026-08-01','2026-08-08','2026-08-15','2026-08-22'];
const batches={{
  '2026-08-01':[{{symbol:'RETURNED',_rank:4}},{{symbol:'CONT',_rank:4}}],
  '2026-08-08':[{{symbol:'CONT',_rank:3}}],
  '2026-08-15':[{{symbol:'CONT',_rank:3}}],
  '2026-08-22':[{{symbol:'FIRST',_rank:1}},{{symbol:'RETURNED',_rank:2}},{{symbol:'CONT',_rank:1}}],
}};
function presentedDates(){{return dates}}
function rankedBatch(_market,date){{return batches[date]||[]}}
{appearance_meta}
const rows=batches['2026-08-22'];
console.log(JSON.stringify(rows.map(row=>appearanceMeta('US',{{...row,signal_date:'2026-08-22'}}))));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", script],
            check=True,
            capture_output=True,
            text=True,
        )
        first, returned, continuing = json.loads(completed.stdout)
        self.assertEqual(first["kind"], "FIRST_SEEN")
        self.assertEqual(
            returned,
            {
                "kind": "RETURNED",
                "lastSeen": "2026-08-01",
                "batchesAway": 2,
                "lastRank": 4,
            },
        )
        self.assertEqual(
            continuing,
            {"kind": "CONTINUING", "streak": 4, "rankMove": 2},
        )

    def test_sectors_defaults_to_quadrant(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist"
            render_site.render_site(FIXTURE, output)
            page = (output / "sectors.html").read_text()
            self.assertIn(
                "let LAYOUT=(localStorage.getItem('sec.layout')==='grid')?"
                "'grid':'quad';",
                page,
            )
            self.assertIn(
                'data-layout="quad" aria-pressed="true">Quadrant</button>', page
            )
            self.assertIn('<section class="grid" id="grid" hidden>', page)
            self.assertIn('<section class="quadwrap" id="quad">', page)

    def test_sectors_switches_between_india_and_us_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist"
            render_site.render_site(FIXTURE, output)
            page = (output / "sectors.html").read_text()
            self.assertIn('data-market="IN" aria-pressed="true">India</button>', page)
            self.assertIn('data-market="US" aria-pressed="false">US</button>', page)
            self.assertIn("snapshot?.rotation?.schema_version!=='us-sector-rotation.v1'", page)
            self.assertIn("MARKET==='US'?'us-weekly.html':'dashboard.html'", page)
            self.assertIn("MARKET==='US'?'us-daily.html':'daily.html'", page)

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
                "shortlist.html",
                "dashboard.html",
                "daily.html",
                "market.html",
                "sectors.html",
                "recommendations.html",
                "tsha_hbcs.html",
                "volume_trend.html",
                "transactions.html",
            ):
                page = (output / name).read_text()
                self.assertIn('href="tsha_hbcs.html"', page)
                self.assertIn(">HT</a>", page)
                self.assertIn('href="volume_trend.html"', page)
                self.assertIn(">VT</a>", page)
                self.assertIn('href="transactions.html"', page)
                self.assertIn(">Trades</a>", page)

    def test_ht_uses_shared_screener_shell_without_explainer(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist"
            render_site.render_site(FIXTURE, output)
            page = (output / "tsha_hbcs.html").read_text()
            self.assertIn("<h1>HT Confirmations</h1>", page)
            self.assertIn('class="tablecard"', page)
            self.assertIn('class="tablewrap"', page)
            self.assertIn('id="themeBtn"', page)
            self.assertIn(
                '<th class="l sorted" data-k="appearance_count">Appearances</th>',
                page,
            )
            self.assertIn("function appearanceCell(r)", page)
            self.assertIn('id="ignitionOnly"', page)
            self.assertIn("function ignitionDot(r)", page)
            self.assertIn('class="ignition-dot"', page)
            self.assertIn("!state.ignition||r.ignition===true", page)
            self.assertIn(
                'value="5" selected>Turnover ≥ ₹5cr / $5m</option>', page
            )
            self.assertIn(
                "const turnoverFloor=market=>state.liquidity*"
                "(market==='IN'?10000000:1000000);",
                page,
            )
            self.assertIn(".sort(compareRows)", page)
            self.assertNotIn('data-k="hbcs_components"', page)
            self.assertNotIn('data-k="fast_body_pct"', page)
            self.assertNotIn('data-k="slow_body_pct"', page)
            self.assertIn("const weekStart=date=>", page)
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

    def test_vt_mirrors_the_ht_selection_and_history_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist"
            render_site.render_site(FIXTURE, output)
            page = (output / "volume_trend.html").read_text()
            self.assertIn("<h1>VT · Volume Breakout / Breakdown</h1>", page)
            self.assertIn('id="markets"', page)
            self.assertIn('id="timeframes"', page)
            self.assertIn('id="directions"', page)
            self.assertIn(
                '<button class="toolbtn on" data-v="BUY">BUY</button>', page
            )
            self.assertIn("direction:'BUY'", page)
            self.assertIn(
                'value="5" selected>Turnover ≥ ₹5cr / $5m</option>', page
            )
            self.assertIn(
                "const turnoverFloor=market=>state.liquidity*"
                "(market==='IN'?10000000:1000000);",
                page,
            )
            self.assertIn('id="historyRange"', page)
            self.assertIn('id="pageNumber"', page)
            self.assertIn('id="pageSize"', page)
            self.assertIn(
                '<th class="l sorted" data-k="appearance_count">Appearances</th>',
                page,
            )
            self.assertIn("const weekStart=date=>", page)
            self.assertIn("schema_version!=='volume-trend.snapshot.v1'", page)
            self.assertIn("MarketEvents.record(r.symbol,r.market)", page)
            self.assertNotIn("?'present':'absent'", page)

    def test_render_preserves_page_cutoffs_with_shared_strip_inputs(self):
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
                "dashboard.html": "2026-08-10",
                "daily.html": "2026-08-11",
                "market.html": "2026-08-11",
                "sectors.html": "2026-08-10",
                "recommendations.html": "2026-08-10",
            }
            for name, as_of in expectations.items():
                page = (output / name).read_text()
                payload = self.decode_rendered_payload(page)
                self.assertEqual("11 Aug 2026, 17:30 IST", payload["last_updated_ist"])
                self.assertEqual(as_of, payload["data_as_of"])
                self.assertEqual(1, page.count('class="dashboard-freshness"'))
                self.assertEqual(1, page.count('data-active="true"'))
                for freshness_source in (
                    "india_weekly",
                    "india_daily",
                    "market",
                    "sectors",
                    "us_weekly",
                    "us_daily",
                    "ht_india",
                    "ht_us",
                    "outcomes",
                ):
                    self.assertIn(f'data-freshness="{freshness_source}"', page)

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

    def test_rejects_market_cutoff_behind_daily(self):
        bundle = self.load_fixture()
        bundle["source_freshness"]["market"]["as_of"] = "2026-08-07"
        with self.assertRaisesRegex(
            render_site.BundleError, "market cutoff must equal the daily cutoff"
        ):
            render_site.validate_bundle(bundle)

    def test_rejects_sector_cutoff_outside_daily_week(self):
        bundle = self.load_fixture()
        bundle["source_freshness"]["sectors"]["as_of"] = "2026-08-03"
        with self.assertRaisesRegex(
            render_site.BundleError, "sectors cutoff must equal the daily session's Monday"
        ):
            render_site.validate_bundle(bundle)

    def test_rejects_weekly_cutoff_outside_daily_week(self):
        bundle = self.load_fixture()
        bundle["source_freshness"]["weekly"]["as_of"] = "2026-08-03"
        with self.assertRaisesRegex(
            render_site.BundleError, "weekly cutoff must equal the daily session's Monday"
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

    def test_shared_shell_loads_static_and_live_freshness_inputs(self):
        shell = (ROOT / "assets" / "dashboard-shell.js").read_text()
        self.assertIn("loadFreshness", shell)
        self.assertIn("setFreshnessGroup", shell)
        self.assertIn('fetchJson("dashboard-freshness.json")', shell)
        self.assertIn('fetchJson("/api/us-trend-bounce?meta=1")', shell)
        self.assertIn('fetchJson("/api/tsha-hbcs?meta=1")', shell)
        self.assertIn('fetchJson("/api/forward-test?meta=1")', shell)

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
        ignition_label = javascript_function(page, "ignitionReasonLabel")
        script = f"""
{ignition_label}
{function_source}
const latest=[{{symbol:'LATEST'}}];
const history={{periods:[
  {{date:'2026-08-14',source:'replay',rows:[{{symbol:'ABC',close:10,ignition:true,ignition_reason:'first_bullish_stack_signal'}},{{symbol:'XYZ',close:20,ignition:false,ignition_reason:''}}]}},
  {{date:'2026-08-15',source:'stored',rows:[{{symbol:'ABC',close:12,ignition:false,ignition_reason:''}},{{symbol:'NEW',close:30,ignition:true,ignition_reason:'fast_sha_bounce_signal'}}]}},
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
        self.assertTrue(by_symbol["ABC"]["ignition"])
        self.assertTrue(by_symbol["NEW"]["ignition"])
        self.assertFalse(by_symbol["XYZ"]["ignition"])
        self.assertEqual(
            by_symbol["ABC"]["ignition_periods"],
            ["2026-08-14 · first bullish-stack signal"],
        )
        self.assertEqual(
            by_symbol["ABC"]["appearance_periods"],
            ["2026-08-14", "2026-08-15"],
        )
        self.assertEqual(result["stats"]["latestCount"], 2)
        self.assertEqual(result["stats"]["newCount"], 1)
        self.assertEqual(result["stats"]["everyCount"], 1)

    def test_ht_default_sort_uses_appearance_count_and_recency(self):
        compare_rows = javascript_function(HT_TEMPLATE.read_text(), "compareRows")
        rows = [
            {
                "symbol": "OLD",
                "market": "IN",
                "timeframe": "daily",
                "appearance_count": 2,
                "appearance_bits": "110",
                "hbcs_bull_component_count": 1,
            },
            {
                "symbol": "LOWCOUNT",
                "market": "IN",
                "timeframe": "daily",
                "appearance_count": 1,
                "appearance_bits": "001",
                "hbcs_bull_component_count": 4,
            },
            {
                "symbol": "RECENT",
                "market": "IN",
                "timeframe": "daily",
                "appearance_count": 2,
                "appearance_bits": "011",
                "hbcs_bull_component_count": 4,
            },
        ]
        program = f"""
const state={{sort:'appearance_count',desc:true}};
{compare_rows}
const rows={json.dumps(rows)}.sort(compareRows);
process.stdout.write(JSON.stringify(rows.map(row=>row.symbol)));
"""

        completed = subprocess.run(
            ["node", "-e", program],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            ["RECENT", "OLD", "LOWCOUNT"],
            json.loads(completed.stdout),
        )

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
        period_helpers_start = page.index("const weekStart=")
        period_helpers_end = page.index("\nconst periodLabel=", period_helpers_start)
        start = page.index("function unpackHistory(")
        end = page.index("\nfunction unpack(snapshot)", start)
        function_source = page[start:end]
        script = f"""
{page[period_helpers_start:period_helpers_end]}
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
        period_helpers_start = page.index("const weekStart=")
        period_helpers_end = page.index("\nconst periodLabel=", period_helpers_start)
        start = page.index("function unpackHistory(")
        end = page.index("\nfunction unpack(snapshot)", start)
        function_source = page[start:end]
        script = f"""
{page[period_helpers_start:period_helpers_end]}
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
