import base64
import copy
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import render_site


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "signals-bundle.v1.json"
HT_TEMPLATE = ROOT / "templates" / "tsha_hbcs.html"


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
            self.assertNotIn("__DASHBOARD_NAV__", (output / "tsha_hbcs.html").read_text())
            self.assertIn("fetch('/api/tsha-hbcs'", (output / "tsha_hbcs.html").read_text())
            self.assertIn(
                "fetch('/api/us-trend-bounce'",
                (output / "us-weekly.html").read_text(),
            )
            self.assertIn(
                "const TIMEFRAME='weekly';",
                (output / "us-weekly.html").read_text(),
            )
            self.assertIn(
                "const TIMEFRAME='daily';",
                (output / "us-daily.html").read_text(),
            )
            for page, market in (
                ("dashboard.html", "IN"),
                ("daily.html", "IN"),
                ("us-weekly.html", "US"),
                ("us-daily.html", "US"),
            ):
                rendered = (output / page).read_text()
                self.assertIn('src="market-events.js?v=2"', rendered)
                self.assertIn(f"MarketEvents.load('{market}'", rendered)
                self.assertIn("MarketEvents.dot(", rendered)
            us_weekly = (output / "us-weekly.html").read_text()
            self.assertIn('id="tt" role="tooltip"', us_weekly)
            self.assertIn('class="dots" data-tip=', us_weekly)
            self.assertIn("return `${on?'●':'○'} ${periodLabel(period.week)}`", us_weekly)
            self.assertNotIn("?'present':'absent'", us_weekly)
            self.assertIn("const weekStart=date=>", us_weekly)
            for page in ("us-weekly.html", "us-daily.html"):
                rendered = (output / page).read_text()
                self.assertIn('id="congressOnly"', rendered)
                self.assertIn("state.congress", rendered)
                self.assertIn("row.hasCongressHistory", rendered)
                self.assertIn("'hasCongressHistory'", rendered)
                self.assertIn("EVENTS_READY", rendered)
                self.assertIn(
                    '<th class="l ticker-col" data-sort="symbol">Ticker</th>', rendered
                )
                self.assertIn(
                    '<div class="market">${esc(row.exchange||\'US\')} · '
                    "${esc(row.asset_type||'stock')}</div>",
                    rendered,
                )
                self.assertNotIn('<div class="name">', rendered)
                self.assertNotIn('data-sort="exchange"', rendered)
                self.assertNotIn('id="formula"', rendered)
                self.assertNotIn("Formula: EMA10", rendered)
            ht_page = (output / "tsha_hbcs.html").read_text()
            self.assertIn('src="market-events.js?v=2"', ht_page)
            self.assertIn('id="eventOnly"', ht_page)
            self.assertIn("MarketEvents.load(market", ht_page)
            self.assertIn("MarketEvents.record(r.symbol,r.market)", ht_page)
            self.assertIn("MarketEvents.dot(r.symbol,r.market)", ht_page)
            self.assertNotIn("?'present':'absent'", ht_page)
            self.assertNotIn('id="historyPrompt"', ht_page)
            self.assertNotIn("unlock period history", ht_page)
            for page in (
                "dashboard.html",
                "daily.html",
                "us-weekly.html",
                "us-daily.html",
                "market.html",
                "sectors.html",
                "recommendations.html",
                "tsha_hbcs.html",
            ):
                rendered = (output / page).read_text()
                self.assertIn('href="tsha_hbcs.html"', rendered)
                self.assertIn('href="us-weekly.html"', rendered)
                self.assertIn('href="us-daily.html"', rendered)
                self.assertEqual(1, rendered.count('id="themeBtn"'))
                self.assertEqual(1, rendered.count('aria-current="page"'))
                self.assertIn('href="#main-content">Skip to results</a>', rendered)
                self.assertIn('id="main-content"', rendered)
                self.assertNotIn('class="dashboard-freshness"', rendered)
                self.assertNotIn('data-freshness="', rendered)
                self.assertNotIn('class="purpose"', rendered)
                self.assertNotIn('id="purpose"', rendered)
                self.assertIn('src="dashboard-shell.js?v=1"', rendered)
                self.assertIn('href="dashboard-shell.css?v=1"', rendered)
            freshness = json.loads((output / "dashboard-freshness.json").read_text())
            self.assertEqual("dashboard-freshness.v1", freshness["schema_version"])
            self.assertEqual(
                "2026-08-11",
                freshness["sources"]["india_weekly"]["as_of"],
            )
            self.assertNotIn("status", freshness["sources"]["india_weekly"])
            weekly = (output / "dashboard.html").read_text()
            daily = (output / "daily.html").read_text()
            recommendations = (output / "recommendations.html").read_text()
            for page in (weekly, daily):
                self.assertNotIn("?'present':'absent'", page)
                self.assertIn("?'●':'○'", page)
            self.assertIn("India Weekly · Trend Bounce", weekly)
            self.assertIn('data-preset="8">8W</button>', weekly)
            self.assertIn("India Daily · Trend Bounce", daily)
            self.assertIn("const WINDOW=8;", daily)
            self.assertIn('data-days="8">8D</button>', daily)
            self.assertIn("Forward Test · Outcomes", recommendations)
            self.assertIn('id="researchColumns"', recommendations)
            self.assertIn('data-sort="entry_open"', recommendations)
            self.assertIn("1. Choose market", ht_page)
            shell = (output / "dashboard-shell.js").read_text()
            self.assertIn('const THEME_KEY = "market-screener-theme"', shell)
            self.assertIn('header.setAttribute(\n        "aria-sort"', shell)

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
                "dashboard.html": "2026-08-10",
                "daily.html": "2026-08-11",
                "market.html": "2026-08-11",
                "sectors.html": "2026-08-10",
                "recommendations.html": "2026-08-10",
            }
            for name, as_of in expectations.items():
                payload = self.decode_rendered_payload((output / name).read_text())
                self.assertEqual("11 Aug 2026, 17:30 IST", payload["last_updated_ist"])
                self.assertEqual(as_of, payload["data_as_of"])

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

    def test_rejects_missing_ht_page(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(render_site, "TEMPLATES", Path(directory)):
                with self.assertRaisesRegex(render_site.BundleError, "HT template not found"):
                    render_site.render_site(FIXTURE, Path(directory) / "dist")

    def test_rejects_missing_us_trend_bounce_page(self):
        with tempfile.TemporaryDirectory() as directory:
            templates = Path(directory)
            (templates / "tsha_hbcs.html").write_text("fixture")
            with mock.patch.object(render_site, "TEMPLATES", templates):
                with self.assertRaisesRegex(
                    render_site.BundleError,
                    "US Trend Bounce template not found",
                ):
                    render_site.render_site(FIXTURE, templates / "dist")

    def test_rejects_unsupported_major_version(self):
        bundle = self.load_fixture()
        bundle["schema_version"] = "2.0"
        with self.assertRaisesRegex(render_site.BundleError, "unsupported schema_version"):
            render_site.validate_bundle(bundle)

    def test_rejects_missing_page(self):
        bundle = self.load_fixture()
        del bundle["pages"]["daily"]
        with self.assertRaisesRegex(render_site.BundleError, "bundle misses pages: daily"):
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

    def test_rejects_missing_weekly_cross_membership(self):
        bundle = copy.deepcopy(self.load_fixture())
        del bundle["pages"]["weekly"]["payload"]["cross"]
        with self.assertRaisesRegex(
            render_site.BundleError,
            r"pages\.weekly\.payload\.cross requires a weeks object",
        ):
            render_site.validate_bundle(bundle)

    def test_rejects_missing_daily_rotation(self):
        bundle = copy.deepcopy(self.load_fixture())
        del bundle["pages"]["daily"]["payload"]["rotation"]
        with self.assertRaisesRegex(
            render_site.BundleError,
            r"pages\.daily\.payload\.rotation must be an object",
        ):
            render_site.validate_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
