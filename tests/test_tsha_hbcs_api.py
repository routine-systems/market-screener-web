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
        "generated_at_utc": "2026-08-18T16:07:23.826157+00:00",
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


def history_fixture(*, ignition: bool = False):
    history = {
        "schema_version": "ht-history.v1",
        "instrument_columns": ["symbol", "exchange", "asset_type", "sector"],
        "instruments": [["ABC", "NSE", "equity", "Industrials"]],
        "row_columns": [
            "instrument_index",
            "hbcs_bull_component_count",
            "hbcs_components",
            "fast_body_pct",
            "slow_body_pct",
            "close",
            "median_dollar_turnover_20",
        ],
        "periods": [
            {
                "date": "2026-08-18",
                "source": "stored",
                "rows": [[0, 2, "HMM, CTS", 0.7, 0.5, 101.5, 2_000_000]],
            }
        ],
    }
    if ignition:
        history["row_columns"].extend(["ignition", "ignition_reason"])
        history["periods"][0]["rows"][0].extend(
            [True, "first_bullish_stack_signal"]
        )
    return history


def run_probe(mode: str) -> dict:
    source_url = "data:text/javascript;base64," + base64.b64encode(
        API.read_bytes()
    ).decode("ascii")
    snapshot_value = valid_snapshot()
    history_modes = {
        "history",
        "ignition_history",
        "malformed_history",
        "current_history",
        "empty_history",
        "max_history",
        "oversized_history",
        "stale_history",
        "invalid_date_history",
        "duplicate_instrument_history",
        "nonfinite_number_history",
        "invalid_components_history",
        "missing_instruments_history",
        "missing_rows_history",
        "wrong_instrument_columns_history",
        "wrong_row_columns_history",
        "wrong_history_version",
    }
    if mode in history_modes:
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"] = (
            history_fixture()
        )
    if mode == "ignition_history":
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"] = (
            history_fixture(ignition=True)
        )
    if mode == "malformed_history":
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"]["periods"][0][
            "rows"
        ][0][0] = 9
    if mode == "current_history":
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"]["periods"][0][
            "source"
        ] = "current"
    if mode == "empty_history":
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"][
            "periods"
        ] = []
    if mode == "oversized_history":
        history = snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"]
        latest = history["periods"][0]
        history["periods"] = [
            {"date": f"2026-08-{day:02d}", "source": "replay", "rows": []}
            for day in range(5, 18)
        ] + [latest]
    if mode == "max_history":
        history = snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"]
        latest = history["periods"][0]
        history["periods"] = [
            {"date": f"2026-08-{day:02d}", "source": "replay", "rows": []}
            for day in range(6, 18)
        ] + [latest]
    if mode == "stale_history":
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"]["periods"][0][
            "date"
        ] = "2026-08-17"
    if mode == "invalid_date_history":
        bucket = snapshot_value["markets"]["IN"]["timeframes"]["daily"]
        bucket["signal_date"] = "2026-02-30"
        bucket["history"]["periods"][0]["date"] = "2026-02-30"
    if mode == "duplicate_instrument_history":
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"][
            "instruments"
        ].append(["ABC", "NSE", "equity", "Industrials"])
    if mode == "nonfinite_number_history":
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"]["periods"][0][
            "rows"
        ][0][5] = None
    if mode == "invalid_components_history":
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"]["periods"][0][
            "rows"
        ][0][2] = "HMM, UNKNOWN"
    if mode == "missing_instruments_history":
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"][
            "instruments"
        ] = {}
    if mode == "missing_rows_history":
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"]["periods"][0][
            "rows"
        ] = {}
    if mode == "wrong_instrument_columns_history":
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"][
            "instrument_columns"
        ][0] = "ticker"
    if mode == "wrong_row_columns_history":
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"][
            "row_columns"
        ].pop()
    if mode == "wrong_history_version":
        snapshot_value["markets"]["IN"]["timeframes"]["daily"]["history"][
            "schema_version"
        ] = "ht-history.v2"
    if mode == "missing_timestamp":
        snapshot_value.pop("generated_at_utc")
    if mode == "naive_timestamp":
        snapshot_value["generated_at_utc"] = "2026-08-18T16:07:23"
    if mode == "invalid_timestamp":
        snapshot_value["generated_at_utc"] = "not-a-timestamp"
    snapshot = json.dumps(snapshot_value)
    script = f"""
const api = await import({source_url!r});
let reads = 0;
const stores = {{
  missing: {{async getWithMetadata(){{reads += 1; return {{value:null,metadata:null}};}}}},
  valid: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:{{write_count:2}}}};}}}},
  history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:{{write_count:2}}}};}}}},
  ignition_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:{{write_count:2}}}};}}}},
  malformed_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  current_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  empty_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  max_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  oversized_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  stale_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  invalid_date_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  duplicate_instrument_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  nonfinite_number_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  invalid_components_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  missing_instruments_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  missing_rows_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  wrong_instrument_columns_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  wrong_row_columns_history: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  wrong_history_version: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  missing_timestamp: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  naive_timestamp: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
  invalid_timestamp: {{async getWithMetadata(){{reads += 1; return {{value:{snapshot},metadata:null}};}}}},
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
    def test_snapshot_without_history_remains_valid_fallback(self):
        result = run_probe("valid")
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["reads"], 1)
        self.assertEqual(result["body"]["schema_version"], "tsha-hbcs.api.v1")
        self.assertEqual(result["body"]["publication"]["write_count"], 2)
        self.assertEqual(result["cache"], "private, max-age=300")
        self.assertIsNone(result["cors"])
        self.assertNotIn(
            "history",
            result["body"]["snapshot"]["markets"]["IN"]["timeframes"]["daily"],
        )

    def test_valid_optional_history_is_returned(self):
        result = run_probe("history")
        self.assertEqual(result["status"], 200)
        history = result["body"]["snapshot"]["markets"]["IN"]["timeframes"]["daily"][
            "history"
        ]
        self.assertEqual(history["schema_version"], "ht-history.v1")
        self.assertEqual(history["periods"][0]["source"], "stored")

    def test_ignition_history_columns_are_returned(self):
        result = run_probe("ignition_history")
        self.assertEqual(result["status"], 200)
        history = result["body"]["snapshot"]["markets"]["IN"]["timeframes"]["daily"][
            "history"
        ]
        self.assertEqual(history["row_columns"][-2:], ["ignition", "ignition_reason"])
        self.assertEqual(
            history["periods"][0]["rows"][0][-2:],
            [True, "first_bullish_stack_signal"],
        )

    def test_api_defers_deep_history_record_validation(self):
        for mode in (
            "malformed_history",
            "duplicate_instrument_history",
            "nonfinite_number_history",
            "invalid_components_history",
        ):
            with self.subTest(mode=mode):
                result = run_probe(mode)
                self.assertEqual(result["status"], 200)

    def test_history_rejects_current_source(self):
        result = run_probe("current_history")
        self.assertEqual(result["status"], 500)
        self.assertEqual(result["body"]["error"], "snapshot invalid")

    def test_history_period_count_is_nonzero_and_capped_at_thirteen(self):
        accepted = run_probe("max_history")
        self.assertEqual(accepted["status"], 200)
        self.assertEqual(
            len(
                accepted["body"]["snapshot"]["markets"]["IN"]["timeframes"]["daily"][
                    "history"
                ]["periods"]
            ),
            13,
        )
        for mode in ("empty_history", "oversized_history"):
            with self.subTest(mode=mode):
                result = run_probe(mode)
                self.assertEqual(result["status"], 500)
                self.assertEqual(result["body"]["error"], "snapshot invalid")

    def test_history_rejects_last_date_before_bucket_signal_date(self):
        result = run_probe("stale_history")
        self.assertEqual(result["status"], 500)
        self.assertEqual(result["body"]["error"], "snapshot invalid")

    def test_history_rejects_nonexistent_calendar_date(self):
        result = run_probe("invalid_date_history")
        self.assertEqual(result["status"], 500)
        self.assertEqual(result["body"]["error"], "snapshot invalid")

    def test_history_requires_instrument_and_period_row_arrays(self):
        for mode in ("missing_instruments_history", "missing_rows_history"):
            with self.subTest(mode=mode):
                result = run_probe(mode)
                self.assertEqual(result["status"], 500)
                self.assertEqual(result["body"]["error"], "snapshot invalid")

    def test_history_requires_version_and_exact_column_arrays(self):
        for mode in (
            "wrong_history_version",
            "wrong_instrument_columns_history",
            "wrong_row_columns_history",
        ):
            with self.subTest(mode=mode):
                result = run_probe(mode)
                self.assertEqual(result["status"], 500)
                self.assertEqual(result["body"]["error"], "snapshot invalid")

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

    def test_snapshot_requires_timezone_aware_generation_timestamp(self):
        for mode in ("missing_timestamp", "naive_timestamp", "invalid_timestamp"):
            with self.subTest(mode=mode):
                result = run_probe(mode)
                self.assertEqual(result["status"], 500)
                self.assertEqual(result["body"]["error"], "snapshot invalid")

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
