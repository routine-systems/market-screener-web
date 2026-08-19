import copy
import json
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
            self.assertEqual(HT_TEMPLATE.read_text(), (output / "tsha_hbcs.html").read_text())
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
            us_weekly = (output / "us-weekly.html").read_text()
            self.assertIn('id="tt" role="tooltip"', us_weekly)
            self.assertIn('class="dots" data-tip=', us_weekly)
            self.assertIn("return `${on?'●':'○'} ${periodLabel(period.week)}`", us_weekly)
            self.assertNotIn("?'present':'absent'", us_weekly)
            self.assertIn("const weekStart=date=>", us_weekly)
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
