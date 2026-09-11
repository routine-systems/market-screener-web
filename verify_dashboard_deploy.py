#!/usr/bin/env python3
"""Reject a dashboard bundle that would degrade the live eleven-tab contract."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
import re


PAGES = {
    "shortlist.html": "shortlist.html",
    "dashboard.html": "dashboard.html",
    "daily.html": "daily.html",
    "us-weekly.html": "us-weekly.html",
    "us-daily.html": "us-daily.html",
    "market.html": "market.html",
    "sectors.html": "sectors.html",
    "tsha_hbcs.html": "tsha_hbcs.html",
    "volume_trend.html": "volume_trend.html",
    "transactions.html": "transactions.html",
    "recommendations.html": "recommendations.html",
}
NAV_ITEMS = (
    ("shortlist.html", "Shortlist"),
    ("dashboard.html", "Weekly"),
    ("daily.html", "Daily"),
    ("us-weekly.html", "US Weekly"),
    ("us-daily.html", "US Daily"),
    ("tsha_hbcs.html", "HT"),
    ("volume_trend.html", "VT"),
    ("transactions.html", "Trades"),
    ("market.html", "Market"),
    ("sectors.html", "Sectors"),
    ("recommendations.html", "Forward Test"),
)
REQUIRED_FILES = {
    *PAGES,
    "index.html",
    "dashboard-freshness.json",
    "dashboard-shell.css",
    "dashboard-shell.js",
    "market-events.js",
    "market-consolidation.js",
    "market-rotation.js",
    "india-rotation.json",
    "functions/_middleware.js",
    "functions/api/market-events.js",
    "functions/api/forward-test.js",
    "functions/api/refresh.js",
    "functions/api/scanlink.js",
    "functions/api/shortlist-history.js",
    "functions/api/tsha-hbcs.js",
    "functions/api/us-trend-bounce.js",
    "functions/api/volume-trend.js",
}
INDIA_PAGES = ("dashboard.html", "daily.html")
US_PAGES = ("us-weekly.html", "us-daily.html")


class DashboardContractError(RuntimeError):
    """The deploy directory does not satisfy the live dashboard contract."""


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: Counter[str] = Counter()
        self.in_nav = False
        self.nav_items: list[tuple[dict[str, str], str]] = []
        self._anchor_attrs: dict[str, str] | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        if element_id := attributes.get("id"):
            self.ids[element_id] += 1
        classes = set(attributes.get("class", "").split())
        if tag == "nav" and "dashboard-nav" in classes:
            self.in_nav = True
        elif self.in_nav and tag == "a":
            self._anchor_attrs = attributes
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._anchor_attrs is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_attrs is not None:
            label = " ".join("".join(self._anchor_text).split())
            self.nav_items.append((self._anchor_attrs, label))
            self._anchor_attrs = None
            self._anchor_text = []
        elif tag == "nav" and self.in_nav:
            self.in_nav = False


def _fail(message: str) -> None:
    raise DashboardContractError(message)


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        _fail(f"required deploy file is missing: {relative}")
    return path.read_text(encoding="utf-8")


def _require_text(page: str, source: str, values: tuple[str, ...]) -> None:
    missing = [value for value in values if value not in source]
    if missing:
        _fail(f"{page} misses contract markers: {missing}")


def _verify_navigation(page: str, source: str, active_href: str) -> None:
    parser = _PageParser()
    parser.feed(source)
    actual = tuple((attrs.get("href"), label) for attrs, label in parser.nav_items)
    if actual != NAV_ITEMS:
        _fail(f"{page} navigation differs from the canonical eleven-tab order")
    active = [
        attrs.get("href")
        for attrs, _ in parser.nav_items
        if attrs.get("aria-current") == "page"
    ]
    if active != [active_href]:
        _fail(f"{page} active navigation is {active!r}, expected {[active_href]!r}")
    for element_id in ("themeBtn", "main-content", "dashboard-results", "viewSwitcher", "pageInfo"):
        if parser.ids[element_id] != 1:
            _fail(f"{page} must contain one id={element_id!r}")
    if source.count('class="dashboard-freshness"') != 1:
        _fail(f"{page} must contain one shared cutoff strip")
    expected_active_inputs = (
        0 if page in {"volume_trend.html", "transactions.html"} else 1
    )
    if source.count('data-active="true"') != expected_active_inputs:
        _fail(
            f"{page} must identify {expected_active_inputs} active cutoff inputs"
        )
    expected_groups = (
        "india_weekly",
        "india_daily",
        "market",
        "sectors",
        "us_weekly",
        "us_daily",
        "ht",
        "outcomes",
    )
    expected_sources = (
        "india_weekly",
        "india_daily",
        "market",
        "sectors",
        "us_weekly",
        "us_daily",
        "ht_india",
        "ht_us",
        "outcomes",
    )
    for group in expected_groups:
        if source.count(f'data-freshness-group="{group}"') != 1:
            _fail(f"{page} cutoff strip misses group {group!r}")
    for freshness_source in expected_sources:
        if source.count(f'data-freshness="{freshness_source}"') != 1:
            _fail(f"{page} cutoff strip misses source {freshness_source!r}")
    if "DATA THROUGH" in source or ">Data through<" in source:
        _fail(f"{page} restores the superseded data-through label")
    if 'class="purpose"' in source or 'id="purpose"' in source:
        _fail(f"{page} retains the superseded title description")


def _decode_history(page: str, source: str) -> dict:
    match = re.search(r'const HISTORY_B64="([A-Za-z0-9+/=]+)"', source)
    if not match:
        _fail(f"{page} misses its embedded history payload")
    try:
        payload = json.loads(base64.b64decode(match.group(1), validate=True))
    except (ValueError, json.JSONDecodeError) as error:
        _fail(f"{page} history payload is invalid: {error}")
    if not isinstance(payload, dict):
        _fail(f"{page} history payload must be an object")
    return payload


def _verify_india_payload(page: str, payload: dict) -> None:
    cross = payload.get("cross")
    if not isinstance(cross, dict) or not isinstance(cross.get("weeks"), dict):
        _fail(f"{page} misses linked-period membership")
    if not cross["weeks"]:
        _fail(f"{page} linked-period membership is empty")
    linked_periods = sorted(cross["weeks"])
    if page == "daily.html":
        linked_periods = linked_periods[-13:]
    for period in linked_periods:
        try:
            parsed = date.fromisoformat(period)
        except ValueError:
            _fail(f"{page} has an invalid linked-period date: {period!r}")
        if page == "daily.html" and parsed.weekday() != 0:
            _fail(f"{page} linked-period date is not Monday-keyed: {period}")

    rotation = payload.get("rotation")
    if not isinstance(rotation, dict):
        _fail(f"{page} misses rotation metadata")
    for field, expected in (("levels", list), ("status", dict), ("of", dict)):
        if not isinstance(rotation.get(field), expected) or not rotation[field]:
            _fail(f"{page} rotation.{field} is missing or empty")

    if page == "dashboard.html":
        periods = payload.get("weeks")
        if not isinstance(periods, list) or not periods:
            _fail("dashboard.html weekly history is missing or empty")
        for item in periods[-13:]:
            period = item.get("week") if isinstance(item, dict) else None
            try:
                parsed = date.fromisoformat(period)
            except (TypeError, ValueError):
                _fail(f"dashboard.html has an invalid weekly period: {period!r}")
            if parsed.weekday() != 0:
                _fail(f"dashboard.html period is not Monday-keyed: {period}")


def _verify_manifest(root: Path) -> str:
    names = [name for name in ("site-manifest.json", "build-manifest.json") if (root / name).is_file()]
    if len(names) != 1:
        _fail("deploy must contain exactly one supported build manifest")
    manifest = json.loads(_read(root, names[0]))
    if manifest.get("schema_version") != 1:
        _fail(f"{names[0]} has an unsupported schema_version")
    files = set(manifest.get("files", []))
    missing = sorted(REQUIRED_FILES - files)
    if missing:
        _fail(f"{names[0]} omits required files: {missing}")
    return names[0]


def verify_site(root: Path) -> dict:
    root = root.resolve()
    if not root.is_dir():
        _fail(f"deploy directory does not exist: {root}")
    missing = sorted(name for name in REQUIRED_FILES if not (root / name).is_file())
    if missing:
        _fail(f"deploy directory misses required files: {missing}")
    manifest_name = _verify_manifest(root)

    page_sources: dict[str, str] = {}
    for page, active_href in PAGES.items():
        source = _read(root, page)
        page_sources[page] = source
        _verify_navigation(page, source, active_href)
        _require_text(
            page,
            source,
            (
                'href="#dashboard-results">Skip to results</a>',
                'src="dashboard-shell.js?v=3"',
                'href="dashboard-shell.css?v=4"',
            ),
        )
        unresolved = re.findall(r"__[A-Z][A-Z0-9_]+__", source)
        if unresolved:
            _fail(f"{page} retains template placeholders: {sorted(set(unresolved))}")

    state_words = re.compile(r"\?\s*['\"]present['\"]\s*:\s*['\"]absent['\"]")
    for page in INDIA_PAGES:
        source = page_sources[page]
        _require_text(
            page,
            source,
            (
                'id="crossOnly"',
                'id="rotOnly"',
                'id="tt" role="tooltip"',
                'data-tip="row"',
                "MarketEvents.load('IN'",
                "MarketEvents.dot(",
                "MarketEvents.dot(r.symbol,'IN','insider_trade')",
                'src="market-events.js?v=5"',
                "?'●':'○'",
            ),
        )
        if state_words.search(source):
            _fail(f"{page} uses present/absent appearance tooltip words")
        _verify_india_payload(page, _decode_history(page, source))
    _require_text(
        "dashboard.html",
        page_sources["dashboard.html"],
        ('<th data-k="count" class="sorted l">Appearances</th>',),
    )
    _require_text(
        "daily.html",
        page_sources["daily.html"],
        ('<th class="l" data-k="consist">Appearances</th>',),
    )

    for page in ("dashboard.html", "daily.html", "us-weekly.html", "us-daily.html", "shortlist.html", "tsha_hbcs.html", "volume_trend.html", "transactions.html", "recommendations.html"):
        _require_text(page, page_sources[page], ('src="market-rotation.js?v=2"', "MarketRotation."))

    for page in ("tsha_hbcs.html", "volume_trend.html", "shortlist.html"):
        _require_text(page, page_sources[page], ('src="market-consolidation.js?v=1"', "MarketConsolidation.attributes(r)"))

    for page, timeframe in (("us-weekly.html", "weekly"), ("us-daily.html", "daily")):
        source = page_sources[page]
        _require_text(
            page,
            source,
            (
                f"const TIMEFRAME='{timeframe}';",
                "fetch('/api/us-trend-bounce'",
                'id="congressOnly"',
                "state.congress",
                "row.hasCongressHistory",
                "MarketEvents.load('US'",
                "MarketEvents.dot(",
                'src="market-events.js?v=5"',
                'id="tt" role="tooltip"',
                "?'●':'○'",
                '<th class="l ticker-col" data-sort="symbol">Ticker</th>',
                '<th class="l sorted" data-sort="count">Appearances</th>',
                '<td class="l ticker-col">',
                '<div class="market">${esc(row.exchange||\'US\')} · ${esc(row.asset_type||\'stock\')}</div>',
                'id="rotOnly"',
                "snapshot.rotation?.schema_version!=='us-sector-rotation.v1'",
                "rotationDot(row.symbol)",
                'data-sort="industry">Industry</th>',
            ),
        )
        if '<div class="name">' in source or 'data-sort="exchange"' in source:
            _fail(f"{page} retains the superseded company-name or Exchange column")
        if 'id="formula"' in source or "Formula: EMA10" in source:
            _fail(f"{page} retains the superseded formula row")
        if state_words.search(source):
            _fail(f"{page} uses present/absent appearance tooltip words")
    _require_text(
        "us-weekly.html",
        page_sources["us-weekly.html"],
        ("const weekStart=date=>",),
    )

    _require_text(
        "sectors.html",
        page_sources["sectors.html"],
        (
            "let LAYOUT=(localStorage.getItem('sec.layout')==='grid')?'grid':'quad';",
            'data-layout="quad" aria-pressed="true">Quadrant</button>',
            '<section class="grid" id="grid" hidden>',
            '<section class="quadwrap" id="quad">',
            "b.setAttribute('aria-pressed',String(on))",
            'data-market="IN" aria-pressed="true">India</button>',
            'data-market="US" aria-pressed="false">US</button>',
            "snapshot?.rotation?.schema_version!=='us-sector-rotation.v1'",
            "MARKET==='US'?'us-weekly.html':'dashboard.html'",
            "MARKET==='US'?'us-daily.html':'daily.html'",
        ),
    )

    ht = page_sources["tsha_hbcs.html"]
    _require_text(
        "tsha_hbcs.html",
        ht,
        (
            'id="ignitionOnly"',
            'class="ignition-dot"',
            "function ignitionDot(r)",
            "!state.ignition||r.ignition===true",
            'id="eventOnly"',
            "MarketEvents.load(market",
            "MarketEvents.record(r.symbol,r.market)",
            "MarketEvents.dot(r.symbol,r.market)",
            "MarketEvents.dot(r.symbol,'IN','insider_trade')",
            'src="market-events.js?v=5"',
            '<th class="l sorted" data-k="appearance_count">Appearances</th>',
            "sort:'appearance_count'",
            "function compareRows(",
            ".sort(compareRows)",
            "const weekStart=date=>",
            "● Bulk history",
            "● Congress history",
            "?'●':'○'",
            'id="liquidity"',
            'value="5" selected>Turnover ≥ ₹5cr / $5m</option>',
            "liquidity:5",
            "const turnoverFloor=market=>state.liquidity*(market==='IN'?10000000:1000000);",
        ),
    )
    if 'id="historyPrompt"' in ht or "unlock period history" in ht:
        _fail("tsha_hbcs.html retains the superseded history instruction box")
    for diagnostic_column in (
        'data-k="hbcs_components"',
        'data-k="fast_body_pct"',
        'data-k="slow_body_pct"',
        "Fresh components</th>",
        "Bullish components</th>",
    ):
        if diagnostic_column in ht:
            _fail("tsha_hbcs.html restores suppressed diagnostic columns")

    _require_text(
        "recommendations.html",
        page_sources["recommendations.html"],
        (
            "fetch('/api/forward-test'",
            "forward-test.api.v1",
            "applyPayload(fallbackPayload)",
        ),
    )

    _require_text(
        "shortlist.html",
        page_sources["shortlist.html"],
        (
            "India + US Daily + Weekly · Shortlist",
            ".slice(0,20)",
            "fetch('/api/tsha-hbcs'",
            "fetch('/api/volume-trend'",
            "const nearbyWindow=3",
            "ht2of3",
            "ht3of5",
            "ht_vt",
            "prior 2 same-timeframe periods",
            'id="historyDate"',
            'id="historyLatest"',
            "shortlist-history.api.v1",
            'id="sectorTabs"',
            "Rising sectors",
            "Other sectors",
            'data-k="appearances">Appearances',
            "data-appearance-tip",
            "sector_top20.v1",
        ),
    )

    vt = page_sources["volume_trend.html"]
    _require_text(
        "volume_trend.html",
        vt,
        (
            "VT · Volume Breakout / Breakdown",
            "fetch('/api/volume-trend'",
            "volume-trend.api.v1",
            "vt-history.v1",
            "vt-locked-zones.v1",
            'id="views"',
            'data-k="inside_count"',
            "buildZoneRows",
            'id="directions"',
            'id="historyRange"',
            'id="pageNumber"',
            'id="pageSize"',
            '<th class="l sorted" data-k="appearance_count">Appearances</th>',
            "MarketEvents.record(r.symbol,r.market)",
            "?'●':'○'",
            '<button class="toolbtn on" data-v="BUY">BUY</button>',
            "view:'events'",
            "direction:'BUY'",
            'id="liquidity"',
            'value="5" selected>Turnover ≥ ₹5cr / $5m</option>',
            "liquidity:5",
            "const turnoverFloor=market=>state.liquidity*(market==='IN'?10000000:1000000);",
            "volume confirmation off by default",
            "confirmed close crossing the previous zone",
            "75-bar lookback · volume confirmation off",
        ),
    )
    if state_words.search(vt):
        _fail("volume_trend.html uses present/absent appearance tooltip words")

    _require_text(
        "transactions.html",
        page_sources["transactions.html"],
        (
            "Transactions · India + U.S.",
            "`/api/market-events?market=${market}`",
            "market-events.snapshot.v1",
            "market-events.api.v1",
            "bulk_deal",
            "insider_trade",
            "political_trade_report",
            "option_flow",
            "Options flow",
            'id="categories"',
            'id="search"',
            'id="side"',
            'id="pageNumber"',
            'id="pageSize"',
            'id="download"',
            "function flatten(",
            "function syncCoverage(",
            "filteredRows()",
        ),
    )

    freshness = json.loads(_read(root, "dashboard-freshness.json"))
    if freshness.get("schema_version") != "dashboard-freshness.v1":
        _fail("dashboard-freshness.json has an unsupported schema_version")
    shell = _read(root, "dashboard-shell.js")
    _require_text(
        "dashboard-shell.js",
        shell,
        (
            "loadFreshness",
            "setFreshnessGroup",
            'fetchJson("dashboard-freshness.json")',
            'fetchJson("/api/us-trend-bounce?meta=1")',
            'fetchJson("/api/tsha-hbcs?meta=1")',
            'fetchJson("/api/forward-test?meta=1")',
        ),
    )
    middleware = _read(root, "functions/_middleware.js")
    if 'const TRUSTED_HOST = "screener.chiragpatnaik.com";' not in middleware:
        _fail("functions/_middleware.js misses the production-host restriction")

    return {
        "schema_version": "dashboard-deploy-contract.v1",
        "pages": len(PAGES),
        "required_files": len(REQUIRED_FILES),
        "manifest": manifest_name,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path("dist"))
    arguments = parser.parse_args()
    try:
        result = verify_site(arguments.root)
    except DashboardContractError as error:
        parser.exit(1, f"dashboard deploy rejected: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
