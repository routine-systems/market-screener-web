import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../assets/market-events.js", import.meta.url),
  "utf8",
);

function element() {
  return {
    hidden: false,
    innerHTML: "",
    style: {},
    dataset: {},
    addEventListener() {},
    appendChild() {},
    contains() { return false; },
    getBoundingClientRect() {
      return { left: 10, top: 10, bottom: 20, width: 300, height: 200 };
    },
    setAttribute() {},
  };
}

function snapshot() {
  const columns = [
    "event_date", "reported_at", "actor", "side", "shares",
    "price", "value", "source", "url", "summary",
  ];
  return {
    schema_version: "market-events.snapshot.v1",
    market: "IN",
    event_type: "bulk_deal",
    history_scope: "rolling_1_year",
    event_columns: columns,
    records: {
      TEST: {
        count: 1,
        first_date: "2026-08-18",
        last_date: "2026-08-18",
        events: [["2026-08-18", null, "Fixture Fund", "BUY", 100, 10, 1000, "NSE", null, ""]],
      },
    },
    related_event_sets: {
      insider_trade: {
        event_type: "insider_trade",
        history_scope: "rolling_1_year",
        event_columns: columns,
        records: {
          TEST: {
            count: 2,
            first_date: "2026-08-17",
            last_date: "2026-08-19",
            events: [["2026-08-19", "2026-08-20T09:00:00Z", "Fixture Director", "BUY", 50, 12, 600, "NSE PIT", "https://example.test/pit", "Director"]],
          },
        },
      },
    },
  };
}

test("renders independent bulk and insider dots from one India snapshot", async () => {
  const document = {
    head: element(),
    body: element(),
    createElement: element,
    addEventListener() {},
  };
  const context = {
    URL,
    console,
    document,
    fetch: async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: "market-events.api.v1",
        snapshot: snapshot(),
      }),
    }),
    location: { protocol: "https:" },
    window: {
      clearTimeout() {},
      innerHeight: 900,
      innerWidth: 1200,
      setTimeout() { return 1; },
    },
  };
  vm.runInNewContext(source, context);

  await context.window.MarketEvents.load("IN");

  const bulk = context.window.MarketEvents.dot("TEST", "IN");
  const insider = context.window.MarketEvents.dot("TEST", "IN", "insider_trade");
  assert.match(bulk, /data-event-type="bulk_deal"/);
  assert.match(bulk, /1 bulk deal in the last year/);
  assert.match(insider, /data-event-type="insider_trade"/);
  assert.match(insider, /2 insider trades in the last year/);
  assert.equal(
    context.window.MarketEvents.record("TEST", "IN", "insider_trade").count,
    2,
  );
});
