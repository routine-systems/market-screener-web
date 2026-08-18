import copy
import json
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
            self.assertIn("fetch('/api/tsha-hbcs'", (output / "tsha_hbcs.html").read_text())
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
            self.assertNotIn('data-k="name">Name</th>', page)
            self.assertNotIn("${esc(r.name||r.symbol)}</td>", page)
            self.assertNotIn("Locally computed database screener", page)
            self.assertNotIn("Twin Smoothed HA + HBCS", page)
            self.assertNotIn("Completed-bar confluence", page)

    def test_ht_appearance_dots_preserve_period_order(self):
        page = (ROOT / "templates" / "tsha_hbcs.html").read_text()
        start = page.index("function appearanceCell(r){")
        end = page.index("\nfunction render(){", start)
        function_source = page[start:end]
        script = f"""
const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}}[c]));
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
        self.assertLess(
            rendered["mixed"].index("2026-08-12"),
            rendered["mixed"].index("2026-08-14"),
        )
        self.assertEqual(3, rendered["every"].count('class="dot hot"'))
        self.assertIn("—", rendered["missing"])

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
