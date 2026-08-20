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
