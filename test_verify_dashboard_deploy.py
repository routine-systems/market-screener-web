from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import unittest

import verify_dashboard_deploy as subject


def _history(*, weekly: bool = False, rotation: bool = True) -> str:
    payload = {
        "weeks": [
            {
                "week": "2026-08-17" if weekly else "2026-08-19",
                "tickers": [{"symbol": "TEST"}],
            }
        ],
        "cross": {"weeks": {"2026-08-17": ["TEST"]}},
    }
    if rotation:
        payload["rotation"] = {
            "levels": ["sector"],
            "status": {"sector": {"Test": 1}},
            "of": {"TEST": ["Test"]},
        }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def _nav(active: str) -> str:
    links = []
    for href, label in subject.NAV_ITEMS:
        current = ' class="on" aria-current="page"' if href == active else ""
        links.append(f'<a href="{href}"{current}>{label}</a>')
    return '<nav class="nav dashboard-nav">' + "".join(links) + "</nav>"


def _page(active: str, body: str = "") -> str:
    return (
        '<!doctype html><html><head><link rel="stylesheet" '
        'href="dashboard-shell.css?v=1"></head><body>'
        '<a class="skip-link" href="#main-content">Skip to results</a>'
        f'{_nav(active)}<button id="themeBtn">Theme</button>'
        f'<main id="main-content">{body}</main>'
        '<script src="dashboard-shell.js?v=1"></script></body></html>'
    )


def _india_body(*, weekly: bool, rotation: bool = True) -> str:
    history = _history(weekly=weekly, rotation=rotation)
    appearance_header = (
        '<th data-k="count" class="sorted l">Appearances</th>'
        if weekly
        else '<th class="l" data-k="consist">Appearances</th>'
    )
    return f'''<button id="crossOnly"></button><button id="rotOnly"></button>
<table><thead><tr>{appearance_header}</tr></thead></table>
<div id="tt" role="tooltip"></div><span data-tip="row"></span>
<script src="market-events.js?v=5"></script><script>
const HISTORY_B64="{history}"; const glyph=on?'●':'○';
MarketEvents.load('IN',()=>MarketEvents.dot('TEST'));
MarketEvents.dot(r.symbol,'IN','insider_trade');
</script>'''


def _us_body(timeframe: str) -> str:
    week_start = "const weekStart=date=>date;" if timeframe == "weekly" else ""
    return f'''<button id="congressOnly">● Congress history</button><button id="rotOnly">◉ Rotation</button>
<table><thead><tr><th class="l ticker-col" data-sort="symbol">Ticker</th><th class="l sorted" data-sort="count">Appearances</th></tr></thead><tbody><tr><td class="l ticker-col">TEST</td></tr></tbody></table>
<div id="tt" role="tooltip"></div><span class="dots" data-tip="x"></span>
<script src="market-events.js?v=5"></script><script>
const TIMEFRAME='{timeframe}'; {week_start}
fetch('/api/us-trend-bounce'); state.congress; row.hasCongressHistory;
snapshot.rotation?.schema_version!=='us-sector-rotation.v1'; rotationDot(row.symbol);
const glyph=on?'●':'○'; MarketEvents.load('US',()=>MarketEvents.dot('TEST'));
const cell=`<div class="market">${{esc(row.exchange||'US')}} · ${{esc(row.rotationGroup||row.asset_type||'stock')}}</div>`;
</script>'''


def _write_valid_site(root: Path) -> None:
    bodies = {
        "dashboard.html": _india_body(weekly=True),
        "daily.html": _india_body(weekly=False),
        "us-weekly.html": _us_body("weekly"),
        "us-daily.html": _us_body("daily"),
        "sectors.html": '''<button data-market="IN" aria-pressed="true">India</button><button data-market="US" aria-pressed="false">US</button>
<button data-layout="quad" aria-pressed="true">Quadrant</button>
<section class="grid" id="grid" hidden></section><section class="quadwrap" id="quad"></section>
<script>let LAYOUT=(localStorage.getItem('sec.layout')==='grid')?'grid':'quad';
snapshot?.rotation?.schema_version!=='us-sector-rotation.v1';
const wt=MARKET==='US'?'us-weekly.html':'dashboard.html'; const dt=MARKET==='US'?'us-daily.html':'daily.html';
const b={setAttribute(){}}; const on=true; b.setAttribute('aria-pressed',String(on));</script>''',
        "tsha_hbcs.html": '''<button id="eventOnly">● Bulk history · ● Congress history</button>
<table><th class="l sorted" data-k="appearance_count">Appearances</th></table>
<script src="market-events.js?v=5"></script><script>const state={sort:'appearance_count'}; const weekStart=date=>date;
function compareRows(a,b){return 0} const rows=[]; rows.sort(compareRows); const glyph=on?'●':'○'; MarketEvents.load(market,()=>{});
MarketEvents.record(r.symbol,r.market); MarketEvents.dot(r.symbol,r.market);
MarketEvents.dot(r.symbol,'IN','insider_trade');</script>''',
    }
    for page, active in subject.PAGES.items():
        (root / page).write_text(_page(active, bodies.get(page, "")))
    for name in subject.REQUIRED_FILES - set(subject.PAGES):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    (root / "functions/_middleware.js").write_text(
        'const TRUSTED_HOST = "screener.chiragpatnaik.com";\n'
    )
    (root / "dashboard-freshness.json").write_text(
        json.dumps({"schema_version": "dashboard-freshness.v1"})
    )
    (root / "site-manifest.json").write_text(
        json.dumps({"schema_version": 1, "files": sorted(subject.REQUIRED_FILES)})
    )


class VerifyDashboardDeployTests(unittest.TestCase):
    def test_accepts_the_eight_tab_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            result = subject.verify_site(root)
            self.assertEqual(8, result["pages"])
            self.assertEqual("site-manifest.json", result["manifest"])

    def test_rejects_legacy_ht_position_after_context_tabs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            source = (root / "dashboard.html").read_text()
            current = (
                '<a href="tsha_hbcs.html">HT</a>'
                '<a href="market.html">Market</a>'
                '<a href="sectors.html">Sectors</a>'
            )
            legacy = (
                '<a href="market.html">Market</a>'
                '<a href="sectors.html">Sectors</a>'
                '<a href="tsha_hbcs.html">HT</a>'
            )
            self.assertIn(current, source)
            (root / "dashboard.html").write_text(source.replace(current, legacy, 1))
            with self.assertRaisesRegex(
                subject.DashboardContractError, "canonical eight-tab order"
            ):
                subject.verify_site(root)

    def test_rejects_grid_as_the_sectors_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            source = (root / "sectors.html").read_text().replace(
                "let LAYOUT=(localStorage.getItem('sec.layout')==='grid')?"
                "'grid':'quad';",
                "let LAYOUT=(localStorage.getItem('sec.layout')==='quad')?"
                "'quad':'grid';",
            )
            (root / "sectors.html").write_text(source)
            with self.assertRaisesRegex(
                subject.DashboardContractError, "sectors.html misses contract markers"
            ):
                subject.verify_site(root)

    def test_rejects_sectors_without_the_us_market_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            source = (root / "sectors.html").read_text().replace(
                '<button data-market="US" aria-pressed="false">US</button>', ""
            )
            (root / "sectors.html").write_text(source)
            with self.assertRaisesRegex(
                subject.DashboardContractError, "sectors.html misses contract markers"
            ):
                subject.verify_site(root)

    def test_rejects_us_page_without_rotation_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            source = (root / "us-weekly.html").read_text().replace(
                "snapshot.rotation?.schema_version!=='us-sector-rotation.v1'", ""
            )
            (root / "us-weekly.html").write_text(source)
            with self.assertRaisesRegex(
                subject.DashboardContractError, "us-weekly.html misses contract markers"
            ):
                subject.verify_site(root)

    def test_rejects_an_old_six_page_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            (root / "us-weekly.html").unlink()
            with self.assertRaisesRegex(subject.DashboardContractError, "us-weekly"):
                subject.verify_site(root)

    def test_rejects_shared_data_through_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            source = (root / "dashboard.html").read_text().replace(
                '<main id="main-content">',
                '<main id="main-content"><section class="dashboard-freshness">'
                '<span data-freshness="india">Data through</span></section>',
            )
            (root / "dashboard.html").write_text(source)
            with self.assertRaisesRegex(
                subject.DashboardContractError, "shared data-through row"
            ):
                subject.verify_site(root)

    def test_rejects_title_description(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            source = (root / "dashboard.html").read_text().replace(
                '<main id="main-content">',
                '<main id="main-content"><p class="purpose">Description</p>',
            )
            (root / "dashboard.html").write_text(source)
            with self.assertRaisesRegex(
                subject.DashboardContractError, "title description"
            ):
                subject.verify_site(root)

    def test_rejects_missing_rotation_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            source = (root / "dashboard.html").read_text()
            source = source.replace(_history(weekly=True), _history(weekly=True, rotation=False))
            (root / "dashboard.html").write_text(source)
            with self.assertRaisesRegex(subject.DashboardContractError, "rotation metadata"):
                subject.verify_site(root)

    def test_rejects_ht_history_instruction_box(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            source = (root / "tsha_hbcs.html").read_text()
            source = source.replace(
                '<button id="eventOnly">',
                '<span id="historyPrompt">unlock period history</span>'
                '<button id="eventOnly">',
            )
            (root / "tsha_hbcs.html").write_text(source)
            with self.assertRaisesRegex(
                subject.DashboardContractError, "history instruction box"
            ):
                subject.verify_site(root)

    def test_rejects_us_formula_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            source = (root / "us-weekly.html").read_text().replace(
                '<button id="congressOnly">',
                '<div id="formula">Formula: EMA10</div><button id="congressOnly">',
            )
            (root / "us-weekly.html").write_text(source)
            with self.assertRaisesRegex(
                subject.DashboardContractError, "formula row"
            ):
                subject.verify_site(root)

    def test_rejects_missing_congress_history_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            source = (root / "us-weekly.html").read_text().replace(
                'id="congressOnly"', 'id="removedCongressFilter"'
            )
            (root / "us-weekly.html").write_text(source)
            with self.assertRaisesRegex(subject.DashboardContractError, "congressOnly"):
                subject.verify_site(root)

    def test_rejects_missing_india_insider_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            source = (root / "dashboard.html").read_text().replace(
                "MarketEvents.dot(r.symbol,'IN','insider_trade');", ""
            )
            (root / "dashboard.html").write_text(source)
            with self.assertRaisesRegex(
                subject.DashboardContractError, "insider_trade"
            ):
                subject.verify_site(root)

    def test_rejects_verbose_appearance_header(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            source = (root / "dashboard.html").read_text().replace(
                ">Appearances</th>",
                ">Appearances in range (oldest→newest)</th>",
                1,
            )
            (root / "dashboard.html").write_text(source)
            with self.assertRaisesRegex(
                subject.DashboardContractError, "Appearances"
            ):
                subject.verify_site(root)

    def test_rejects_ht_diagnostic_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_valid_site(root)
            source = (root / "tsha_hbcs.html").read_text().replace(
                "</table>",
                '<th data-k="hbcs_components">Fresh components</th></table>',
                1,
            )
            (root / "tsha_hbcs.html").write_text(source)
            with self.assertRaisesRegex(
                subject.DashboardContractError, "suppressed diagnostic"
            ):
                subject.verify_site(root)


if __name__ == "__main__":
    unittest.main()
