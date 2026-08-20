import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../functions/api/market-events.js", import.meta.url),
  "utf8",
);
const subject = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

async function moduleFrom(path) {
  const moduleSource = readFileSync(new URL(path, import.meta.url), "utf8");
  return import(
    `data:text/javascript;base64,${Buffer.from(moduleSource).toString("base64")}`
  );
}

test("rejects an unsupported market before reading KV", async () => {
  let reads = 0;
  const response = await subject.onRequestGet({
    request: new Request("https://screener.example/api/market-events?market=CA"),
    env: { SCANLINKS: { getWithMetadata: async () => { reads += 1; } } },
  });

  assert.equal(response.status, 400);
  assert.equal(reads, 0);
  assert.deepEqual(await response.json(), { error: "market must be IN or US" });
});

test("reads the complete-history market snapshot from its market key", async () => {
  const snapshot = {
    schema_version: "market-events.snapshot.v1",
    market: "US",
    history_scope: "complete",
    records: { MRNA: { count: 2, events: [] } },
  };
  const response = await subject.onRequestGet({
    request: new Request("https://screener.example/api/market-events?market=us"),
    env: {
      SCANLINKS: {
        getWithMetadata: async (key, options) => {
          assert.equal(key, "market-events:v1:US");
          assert.deepEqual(options, { type: "json" });
          return { value: snapshot, metadata: { digest: "fixture" } };
        },
      },
    },
  });

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    schema_version: "market-events.api.v1",
    snapshot,
    publication: { digest: "fixture" },
  });
});

test("US Trend Bounce metadata response omits the stored histories", async () => {
  const endpoint = await moduleFrom("../functions/api/us-trend-bounce.js");
  const snapshot = {
    generated_at_utc: "2026-08-20T01:00:00Z",
    pages: {
      weekly: { data_cutoff: "2026-08-17", weeks: [{ large: "payload" }] },
      daily: { data_cutoff: "2026-08-19", weeks: [{ large: "payload" }] },
    },
  };
  const response = await endpoint.onRequestGet({
    request: new Request("https://screener.example/api/us-trend-bounce?meta=1"),
    env: {
      SCANLINKS: {
        getWithMetadata: async () => ({ value: snapshot, metadata: { digest: "us" } }),
      },
    },
  });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    schema_version: "us-trend-bounce.api.v1",
    snapshot: {
      generated_at_utc: "2026-08-20T01:00:00Z",
      pages: {
        weekly: { data_cutoff: "2026-08-17" },
        daily: { data_cutoff: "2026-08-19" },
      },
    },
    publication: { digest: "us" },
  });
});

test("HT metadata response exposes only market cutoffs", async () => {
  const endpoint = await moduleFrom("../functions/api/tsha-hbcs.js");
  const bucket = (signalDate) => ({
    signal_date: signalDate,
    shortlist_size: 0,
    rows: [],
  });
  const snapshot = {
    schema_version: "tsha-hbcs.snapshot.v1",
    generated_at_utc: "2026-08-20T02:00:00Z",
    snapshot_sha256: "0".repeat(64),
    columns: ["symbol"],
    markets: {
      IN: {
        data_session: "2026-08-19",
        timeframes: {
          daily: bucket("2026-08-19"),
          weekly: bucket("2026-08-14"),
        },
      },
      US: {
        data_session: "2026-08-19",
        timeframes: {
          daily: bucket("2026-08-19"),
          weekly: bucket("2026-08-14"),
        },
      },
    },
  };
  const response = await endpoint.onRequestGet({
    request: new Request("https://screener.example/api/tsha-hbcs?meta=1"),
    env: {
      SCANLINKS: {
        getWithMetadata: async () => ({ value: snapshot, metadata: { digest: "ht" } }),
      },
    },
  });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    schema_version: "tsha-hbcs.api.v1",
    snapshot: {
      generated_at_utc: "2026-08-20T02:00:00Z",
      data_cutoff: { IN: "2026-08-19", US: "2026-08-19" },
    },
    publication: { digest: "ht" },
  });
});
