import base64
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "functions" / "api" / "tsha-hbcs.js"


def valid_snapshot():
    def bucket(date):
        return {"signal_date": date, "shortlist_size": 0, "rows": []}

    return {
        "schema_version": "tsha-hbcs.snapshot.v1",
        "snapshot_sha256": "0" * 64,
        "columns": ["market"],
        "markets": {
            "IN": {
                "data_session": "2026-08-18",
                "timeframes": {
                    "daily": bucket("2026-08-18"),
                    "weekly": bucket("2026-08-14"),
                },
            },
            "US": {
                "data_session": "2026-08-17",
                "timeframes": {
                    "daily": bucket("2026-08-17"),
                    "weekly": bucket("2026-08-14"),
                },
            },
        },
    }


def run_probe(mode: str) -> dict:
    source_url = "data:text/javascript;base64," + base64.b64encode(
        API.read_bytes()
    ).decode("ascii")
    snapshot = json.dumps(valid_snapshot())
    script = f"""
const api = await import({source_url!r});
let reads = 0;
const stores = {{
  missing: {{async getWithMetadata(){{reads += 1; return {{value:null,metadata:null}};}}}},
  valid: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:{{write_count:2}}}};}}}},
  corrupt: {{async getWithMetadata(){{reads += 1; return {{value:{{schema_version:'old'}},metadata:null}};}}}},
  throws: {{async getWithMetadata(){{reads += 1; throw new Error('fixture')}}}},
}};
const mode={mode!r};
const env=mode==='unbound'?{{}}:{{SCANLINKS:stores[mode]}};
const response=await api.onRequestGet({{env}});
console.log(JSON.stringify({{
  status:response.status,
  reads,
  cache:response.headers.get('cache-control'),
  cors:response.headers.get('access-control-allow-origin'),
  body:await response.json(),
}}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


class TshaHbcsApiTests(unittest.TestCase):
    def test_valid_snapshot_uses_one_kv_read(self):
        result = run_probe("valid")
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["reads"], 1)
        self.assertEqual(result["body"]["schema_version"], "tsha-hbcs.api.v1")
        self.assertEqual(result["body"]["publication"]["write_count"], 2)
        self.assertEqual(result["cache"], "private, max-age=300")
        self.assertIsNone(result["cors"])

    def test_missing_snapshot_returns_503(self):
        result = run_probe("missing")
        self.assertEqual(result["status"], 503)
        self.assertEqual(result["reads"], 1)
        self.assertEqual(result["cache"], "no-store")

    def test_invalid_snapshot_returns_500(self):
        result = run_probe("corrupt")
        self.assertEqual(result["status"], 500)
        self.assertEqual(result["reads"], 1)
        self.assertEqual(result["cache"], "no-store")

    def test_missing_binding_returns_500_without_read(self):
        result = run_probe("unbound")
        self.assertEqual(result["status"], 500)
        self.assertEqual(result["reads"], 0)

    def test_store_failure_returns_500(self):
        result = run_probe("throws")
        self.assertEqual(result["status"], 500)
        self.assertEqual(result["reads"], 1)


if __name__ == "__main__":
    unittest.main()
