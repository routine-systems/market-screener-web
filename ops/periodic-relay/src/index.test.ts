import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import worker, {
  EXPECTED_COLUMNS,
  HISTORY_INSTRUMENT_COLUMNS,
  HISTORY_ROW_COLUMNS,
  LEGACY_EXPECTED_COLUMNS,
  marketEventsSemanticDigest,
  semanticDigest,
  trendBounceSemanticDigest,
  validateMarketEventsSnapshot,
  validateSnapshot,
  validateTrendBounceSnapshot,
} from "./index.ts";

type StoredMetadata = {
  in_session_revision?: number;
  us_session_revision?: number;
  session_revision?: number;
  write_day_ist?: string;
  write_count?: number;
};

class FakeKV {
  value: Record<string, unknown> | null = null;
  metadata: StoredMetadata | null = null;
  reads = 0;
  puts = 0;

  async getWithMetadata(): Promise<{
    value: Record<string, unknown> | null;
    metadata: StoredMetadata | null;
  }> {
    this.reads += 1;
    return { value: this.value, metadata: this.metadata };
  }

  async put(
    _key: string,
    value: ArrayBuffer,
    options: { metadata: StoredMetadata },
  ): Promise<void> {
    this.puts += 1;
    this.value = JSON.parse(new TextDecoder().decode(value));
    this.metadata = options.metadata;
  }
}

function row(market: string, timeframe: string, signalDate: string, symbol: string): unknown[] {
  return EXPECTED_COLUMNS.map((column) => {
    const values: Record<string, unknown> = {
      market,
      timeframe,
      signal_date: signalDate,
      symbol,
      name: `${symbol} Incorporated`,
      exchange: market === "IN" ? "NSE" : "NYSE",
      asset_type: "stock",
      sector: "Test",
      industry: "Fixtures",
      hbcs_components: "HMM",
      ignition: true,
      ignition_reason: "first_bullish_stack_signal",
    };
    if (column in values) return values[column];
    if (column.endsWith("_bull")) return true;
    return 1;
  });
}

async function withoutIgnition(
  snapshot: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const legacy = structuredClone(snapshot);
  legacy.columns = [...LEGACY_EXPECTED_COLUMNS];
  const markets = legacy.markets as Record<string, Record<string, unknown>>;
  for (const market of ["IN", "US"]) {
    const timeframes = markets[market].timeframes as Record<
      string,
      Record<string, unknown>
    >;
    for (const timeframe of ["daily", "weekly"]) {
      const bucket = timeframes[timeframe];
      bucket.rows = (bucket.rows as unknown[][]).map((values) => values.slice(0, -2));
      const history = bucket.history as Record<string, unknown> | undefined;
      if (!history) continue;
      history.row_columns = (history.row_columns as unknown[]).slice(0, -2);
      for (const period of history.periods as Array<Record<string, unknown>>) {
        period.rows = (period.rows as unknown[][]).map((values) => values.slice(0, -2));
      }
    }
  }
  legacy.snapshot_sha256 = await semanticDigest(legacy);
  return legacy;
}

function columnIndex(column: string): number {
  return (EXPECTED_COLUMNS as readonly string[]).indexOf(column);
}

function mondayOf(value: string): string {
  const parsed = new Date(`${value}T00:00:00Z`);
  const daysSinceMonday = (parsed.getUTCDay() + 6) % 7;
  parsed.setUTCDate(parsed.getUTCDate() - daysSinceMonday);
  return parsed.toISOString().slice(0, 10);
}

async function makeSnapshot(
  inSession = "2026-08-18",
  usSession = "2026-08-18",
  updateMarket = "IN",
  generatedAt = "2026-08-18T12:00:00Z",
): Promise<Record<string, unknown>> {
  const markets: Record<string, unknown> = {};
  for (const [market, dailySession] of [
    ["IN", inSession],
    ["US", usSession],
  ]) {
    const weeklySession = mondayOf(dailySession);
    markets[market] = {
      data_session: dailySession,
      timeframes: {
        daily: {
          signal_date: dailySession,
          requested_asof: dailySession,
          universe_size: 10,
          shortlist_size: 1,
          universe_by_exchange: {},
          shortlist_by_exchange: {},
          condition: "fixture",
          appearance_periods: [dailySession],
          appearance_bits: { [`${market}D`]: "1" },
          rows: [row(market, "daily", dailySession, `${market}D`)],
        },
        weekly: {
          signal_date: weeklySession,
          requested_asof: dailySession,
          universe_size: 10,
          shortlist_size: 1,
          universe_by_exchange: {},
          shortlist_by_exchange: {},
          condition: "fixture",
          appearance_periods: [weeklySession],
          appearance_bits: { [`${market}W`]: "1" },
          rows: [row(market, "weekly", weeklySession, `${market}W`)],
        },
      },
    };
  }
  const snapshot: Record<string, unknown> = {
    schema_version: "tsha-hbcs.snapshot.v1",
    algorithm_version: "tsha-hbcs-confluence.v1",
    columns: [...EXPECTED_COLUMNS],
    markets,
    update_market: updateMarket,
    target_session: updateMarket === "IN" ? inSession : usSession,
    generated_at_utc: generatedAt,
    producer_commit: "fixture-commit",
    row_count: 4,
  };
  snapshot.snapshot_sha256 = await semanticDigest(snapshot);
  return snapshot;
}

function addHistory(snapshot: Record<string, unknown>): void {
  const markets = snapshot.markets as Record<string, Record<string, unknown>>;
  for (const market of ["IN", "US"]) {
    const timeframes = markets[market].timeframes as Record<
      string,
      Record<string, unknown>
    >;
    for (const timeframe of ["daily", "weekly"]) {
      const bucket = timeframes[timeframe];
      const rows = bucket.rows as unknown[][];
      const instruments = rows.map((latestRow) =>
        HISTORY_INSTRUMENT_COLUMNS.map(
          (column) => latestRow[columnIndex(column)],
        ),
      );
      const historyRows = rows.map((latestRow, instrumentIndex) => [
        instrumentIndex,
        ...HISTORY_ROW_COLUMNS.slice(1).map(
          (column) => latestRow[columnIndex(column)],
        ),
      ]);
      const signalDate = bucket.signal_date as string;
      const previousDate = timeframe === "daily" ? "2026-08-17" : "2026-08-07";
      bucket.history = {
        schema_version: "ht-history.v1",
        instrument_columns: [...HISTORY_INSTRUMENT_COLUMNS],
        instruments,
        row_columns: [...HISTORY_ROW_COLUMNS],
        periods: [
          { date: previousDate, source: "replay", rows: [] },
          { date: signalDate, source: "stored", rows: historyRows },
        ],
      };
      bucket.appearance_periods = [previousDate, signalDate];
      bucket.appearance_bits = Object.fromEntries(
        rows.map((latestRow) => [
          latestRow[columnIndex("symbol")],
          "01",
        ]),
      );
    }
  }
}

async function makeHistoryBootstrap(
  generatedAt = "2026-08-18T14:00:00Z",
  updateMarket = "IN",
): Promise<Record<string, unknown>> {
  const snapshot = await makeSnapshot(
    "2026-08-18",
    "2026-08-18",
    updateMarket,
    generatedAt,
  );
  addHistory(snapshot);
  snapshot.snapshot_sha256 = await semanticDigest(snapshot);
  return snapshot;
}

async function makeCoreChangingHistoryBootstrap(
  generatedAt = "2026-08-18T14:00:00Z",
): Promise<Record<string, unknown>> {
  const snapshot = await makeSnapshot(
    "2026-08-18",
    "2026-08-18",
    "US",
    generatedAt,
  );
  const markets = snapshot.markets as Record<string, Record<string, unknown>>;
  const us = markets.US.timeframes as Record<string, Record<string, unknown>>;
  us.weekly.universe_size = 11;
  (us.weekly.rows as unknown[][])[0][columnIndex("close")] = 999;
  addHistory(snapshot);
  snapshot.snapshot_sha256 = await semanticDigest(snapshot);
  return snapshot;
}

async function signedRequest(
  snapshot: Record<string, unknown>,
  token = "fixture-token",
): Promise<Request> {
  const body = JSON.stringify(snapshot);
  const digest = createHash("sha256").update(body).digest("hex");
  return new Request("https://relay.example/v1/tsha-hbcs", {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "content-length": String(Buffer.byteLength(body)),
      "x-content-sha256": digest,
    },
    body,
  });
}

function trendBouncePage(
  timeframe: "daily" | "weekly",
  signalDate: string,
): Record<string, unknown> {
  const page: Record<string, unknown> = {
    schema_version: "us-trend-bounce.page.v1",
    timeframe,
    data_cutoff: signalDate,
    weeks: [
      {
        week: signalDate,
        tickers: [{ symbol: "MRNA", sector: "", marketcap: "Largecap" }],
      },
    ],
    filter: { weeks: { [signalDate]: [] } },
    instruments: {
      MRNA: { name: "Moderna", exchange: "NASDAQ", asset_type: "stock" },
    },
  };
  if (timeframe === "daily") {
    page.signals = {
      pb: { weeks: { [signalDate]: [] } },
      mq: { weeks: { [signalDate]: [] } },
    };
  }
  return page;
}

const rotationGroups = [
  "Agribusiness", "Metals and mining", "Energy", "Materials",
  "Home construction", "Consumer staples", "Consumer discretionary",
  "Industrials", "Technology", "Health care", "Transportation",
  "Communication services", "Utilities", "Retail", "Financials", "Real estate",
];

function trendBounceRotation(weeklyDate: string): Record<string, unknown> {
  const counts = Object.fromEntries(
    rotationGroups.map((group) => [group, [group === "Health care" ? 1 : 0]]),
  );
  const status = Object.fromEntries(rotationGroups.map((group) => [group, 0]));
  return {
    schema_version: "us-sector-rotation.v1",
    market: "US",
    method_version: "trend-bounce-membership-sec-sic-proxy.v1",
    levels: [["sector", "Sector"]],
    weeks: [weeklyDate],
    counts: { sector: counts },
    totals: [1],
    coverage: { mapped: 1, total: 1, latest_mapped: 1, latest_total: 1 },
    status: { sector: status },
    of: { MRNA: ["Health care"] },
    parents: {},
    data_cutoff: weeklyDate,
    requested_asof: "2026-08-18",
    source: "US Weekly Trend Bounce",
    url: "us-weekly.html",
    window: 13,
  };
}

async function makeTrendBounceSnapshot(): Promise<Record<string, unknown>> {
  const weeklyDate = "2026-08-17";
  const rotation = trendBounceRotation(weeklyDate);
  const pageRotation = {
    schema_version: "us-sector-rotation.v1",
    window: 13,
    updated_at: weeklyDate,
    levels: ["sector"],
    levelNames: { sector: "Sector" },
    status: rotation.status,
    of: rotation.of,
  };
  const daily = trendBouncePage("daily", "2026-08-18");
  const weekly = trendBouncePage("weekly", weeklyDate);
  daily.rotation = pageRotation;
  weekly.rotation = pageRotation;
  const snapshot: Record<string, unknown> = {
    schema_version: "us-trend-bounce.snapshot.v1",
    algorithm_version: "chartink-trend-bounce-translation.v1",
    market: "US",
    data_session: "2026-08-18",
    weekly_session: weeklyDate,
    pages: {
      daily,
      weekly,
    },
    rotation,
    generated_at_utc: "2026-08-18T22:00:00Z",
    producer_commit: "fixture-commit",
    row_count: 2,
  };
  snapshot.snapshot_sha256 = await trendBounceSemanticDigest(snapshot);
  return snapshot;
}

async function trendBounceSignedRequest(
  snapshot: Record<string, unknown>,
): Promise<Request> {
  const body = JSON.stringify(snapshot);
  const digest = createHash("sha256").update(body).digest("hex");
  return new Request("https://relay.example/v1/us-trend-bounce", {
    method: "POST",
    headers: {
      authorization: "Bearer fixture-token",
      "content-type": "application/json",
      "content-length": String(Buffer.byteLength(body)),
      "x-content-sha256": digest,
    },
    body,
  });
}

async function makeMarketEventsSnapshot(
  market: "IN" | "US" = "US",
): Promise<Record<string, unknown>> {
  const event = market === "IN"
    ? [
        "2026-08-18",
        null,
        "Fixture Fund",
        "BUY",
        1000,
        125.5,
        125500,
        "NSE",
        null,
        "Fixture Limited",
      ]
    : [
        "2026-03-02",
        "2026-08-19T15:29:20Z",
        "Donald Trump",
        "BUY",
        null,
        null,
        null,
        "Quiver Quantitative",
        "https://x.com/QuiverQuant/status/1",
        "President Trump filed a March 2nd purchase of Moderna stock.",
      ];
  const symbol = market === "IN" ? "M&M" : "MRNA";
  const snapshot: Record<string, unknown> = {
    schema_version: "market-events.snapshot.v1",
    algorithm_version: "market-events-normalization.v1",
    market,
    event_type: market === "IN" ? "bulk_deal" : "political_trade_report",
    history_scope: market === "IN" ? "rolling_1_year" : "complete",
    detail_limit: 12,
    event_columns: [
      "event_date",
      "reported_at",
      "actor",
      "side",
      "shares",
      "price",
      "value",
      "source",
      "url",
      "summary",
    ],
    records: {
      [symbol]: {
        count: 1,
        first_date: event[0],
        last_date: event[0],
        events: [event],
      },
    },
    row_count: 1,
    detail_row_count: 1,
    symbol_count: 1,
    source_cutoff: event[0],
    source: "fixture",
    generated_at_utc: "2026-08-20T01:00:00Z",
    producer_commit: "fixture-commit",
  };
  if (market === "IN") {
    snapshot.related_event_sets = {
      insider_trade: {
        event_type: "insider_trade",
        history_scope: "rolling_1_year",
        detail_limit: 12,
        event_columns: snapshot.event_columns,
        records: {
          "M&M": {
            count: 1,
            first_date: "2026-08-17",
            last_date: "2026-08-17",
            events: [[
              "2026-08-17",
              "2026-08-19T09:00:00Z",
              "Fixture Director",
              "BUY",
              500,
              124,
              62000,
              "NSE PIT",
              "https://www.nseindia.com/fixture",
              "Director · Market purchase · Equity",
            ]],
          },
        },
        row_count: 1,
        detail_row_count: 1,
        symbol_count: 1,
        source_cutoff: "2026-08-17",
        source: "fixture PIT",
      },
    };
  }
  snapshot.snapshot_sha256 = await marketEventsSemanticDigest(snapshot);
  return snapshot;
}

async function marketEventsSignedRequest(
  snapshot: Record<string, unknown>,
): Promise<Request> {
  const body = JSON.stringify(snapshot);
  const digest = createHash("sha256").update(body).digest("hex");
  return new Request("https://relay.example/v1/market-events", {
    method: "POST",
    headers: {
      authorization: "Bearer fixture-token",
      "content-type": "application/json",
      "content-length": String(Buffer.byteLength(body)),
      "x-content-sha256": digest,
    },
    body,
  });
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(object[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

async function canonicalSignedRequest(
  snapshot: Record<string, unknown>,
): Promise<Request> {
  const body = `${canonicalJson(snapshot)}\n`;
  const digest = createHash("sha256").update(body).digest("hex");
  return new Request("https://relay.example/v1/tsha-hbcs", {
    method: "POST",
    headers: {
      authorization: "Bearer fixture-token",
      "content-type": "application/json",
      "content-length": String(Buffer.byteLength(body)),
      "x-content-sha256": digest,
    },
    body,
  });
}

function env(kv: FakeKV): Env {
  return { BUNDLES: kv, INGEST_TOKEN: "fixture-token" } as unknown as Env;
}

test("rejects unauthenticated writes before KV access", async () => {
  const kv = new FakeKV();
  const response = await worker.fetch(
    new Request("https://relay.example/v1/tsha-hbcs", { method: "POST" }),
    env(kv),
  );
  assert.equal(response.status, 401);
  assert.equal(kv.reads, 0);
  assert.equal(kv.puts, 0);
});

test("accepts one validated snapshot", async () => {
  const kv = new FakeKV();
  const response = await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  assert.equal(response.status, 202);
  assert.equal(kv.reads, 1);
  assert.equal(kv.puts, 1);
  assert.equal(((await response.json()) as Record<string, unknown>).write_performed, true);
});

test("rejects a weekly HT bucket that omits the active week", async () => {
  const kv = new FakeKV();
  const snapshot = await makeSnapshot();
  const markets = snapshot.markets as Record<string, Record<string, unknown>>;
  const india = markets.IN.timeframes as Record<string, Record<string, unknown>>;
  const weekly = india.weekly;
  weekly.signal_date = "2026-08-10";
  weekly.appearance_periods = ["2026-08-10"];
  (weekly.rows as unknown[][])[0][columnIndex("signal_date")] = "2026-08-10";
  snapshot.snapshot_sha256 = await semanticDigest(snapshot);

  const response = await worker.fetch(await signedRequest(snapshot), env(kv));

  assert.equal(response.status, 400);
  assert.equal(kv.puts, 0);
  assert.match(
    String(((await response.json()) as Record<string, unknown>).error),
    /weekly session does not match active week/,
  );
});

test("canonical producer wire still enforces the semantic digest", async () => {
  const acceptedKv = new FakeKV();
  const accepted = await worker.fetch(
    await canonicalSignedRequest(await makeSnapshot()),
    env(acceptedKv),
  );
  assert.equal(accepted.status, 202);

  const rejectedKv = new FakeKV();
  const tampered = await makeSnapshot();
  const markets = tampered.markets as Record<string, Record<string, unknown>>;
  const india = markets.IN.timeframes as Record<string, Record<string, unknown>>;
  (india.daily.rows as unknown[][])[0][columnIndex("symbol")] = "TAMPERED";
  const rejected = await worker.fetch(
    await canonicalSignedRequest(tampered),
    env(rejectedKv),
  );
  assert.equal(rejected.status, 400);
  assert.equal(rejectedKv.puts, 0);
  assert.match(
    String(((await rejected.json()) as Record<string, unknown>).error),
    /snapshot digest mismatch/,
  );
});

test("identical retry performs no second write", async () => {
  const kv = new FakeKV();
  const snapshot = await makeSnapshot();
  const first = await worker.fetch(await signedRequest(snapshot), env(kv));
  const second = await worker.fetch(await signedRequest(snapshot), env(kv));
  assert.equal(first.status, 202);
  assert.equal(second.status, 200);
  assert.equal(kv.puts, 1);
  assert.equal(((await second.json()) as Record<string, unknown>).status, "unchanged");
});

test("rejects a regressing market session", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  const response = await worker.fetch(
    await signedRequest(await makeSnapshot("2026-08-17", "2026-08-18", "IN")),
    env(kv),
  );
  assert.equal(response.status, 409);
  assert.equal(kv.puts, 1);
});

test("accepts one catch-up snapshot that advances both markets", async () => {
  const kv = new FakeKV();
  await worker.fetch(
    await signedRequest(
      await makeSnapshot(
        "2026-08-14",
        "2026-08-14",
        "IN",
        "2026-08-14T14:00:00Z",
      ),
    ),
    env(kv),
  );
  const response = await worker.fetch(
    await signedRequest(
      await makeSnapshot(
        "2026-08-18",
        "2026-08-17",
        "US",
        "2026-08-18T14:00:00Z",
      ),
    ),
    env(kv),
  );
  assert.equal(response.status, 202);
  assert.equal(kv.puts, 2);
});

test("accepts a same-session revision for the declared update market", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  const changed = await makeSnapshot(
    "2026-08-18",
    "2026-08-18",
    "IN",
    "2026-08-18T14:00:00Z",
  );
  const markets = changed.markets as Record<string, Record<string, unknown>>;
  const india = markets.IN.timeframes as Record<string, Record<string, unknown>>;
  const rows = india.daily.rows as unknown[][];
  rows[0][EXPECTED_COLUMNS.indexOf("symbol")] = "CHANGED";
  changed.snapshot_sha256 = await semanticDigest(changed);
  const response = await worker.fetch(await signedRequest(changed), env(kv));
  assert.equal(response.status, 202);
  assert.equal(kv.puts, 2);
});

test("rejects a same-session revision without a later generation", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  const changed = await makeSnapshot();
  const markets = changed.markets as Record<string, Record<string, unknown>>;
  const india = markets.IN.timeframes as Record<string, Record<string, unknown>>;
  const rows = india.daily.rows as unknown[][];
  rows[0][EXPECTED_COLUMNS.indexOf("symbol")] = "CHANGED";
  changed.snapshot_sha256 = await semanticDigest(changed);
  const response = await worker.fetch(await signedRequest(changed), env(kv));
  assert.equal(response.status, 409);
  assert.equal(kv.puts, 1);
});

test("rejects a second same-session revision", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  const firstRevision = await makeSnapshot(
    "2026-08-18",
    "2026-08-18",
    "IN",
    "2026-08-18T14:00:00Z",
  );
  const firstMarkets = firstRevision.markets as Record<string, Record<string, unknown>>;
  const firstIndia = firstMarkets.IN.timeframes as Record<string, Record<string, unknown>>;
  (firstIndia.daily.rows as unknown[][])[0][EXPECTED_COLUMNS.indexOf("symbol")] =
    "FIRST";
  firstRevision.snapshot_sha256 = await semanticDigest(firstRevision);
  await worker.fetch(await signedRequest(firstRevision), env(kv));

  const secondRevision = await makeSnapshot(
    "2026-08-18",
    "2026-08-18",
    "IN",
    "2026-08-18T16:00:00Z",
  );
  const secondMarkets = secondRevision.markets as Record<string, Record<string, unknown>>;
  const secondIndia = secondMarkets.IN.timeframes as Record<string, Record<string, unknown>>;
  (secondIndia.daily.rows as unknown[][])[0][EXPECTED_COLUMNS.indexOf("symbol")] =
    "SECOND";
  secondRevision.snapshot_sha256 = await semanticDigest(secondRevision);
  const response = await worker.fetch(await signedRequest(secondRevision), env(kv));
  assert.equal(response.status, 409);
  assert.equal(kv.puts, 2);
});

test("session advance resets the declared market revision allowance", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  const firstRevision = await makeSnapshot(
    "2026-08-18",
    "2026-08-18",
    "IN",
    "2026-08-18T14:00:00Z",
  );
  const firstMarkets = firstRevision.markets as Record<string, Record<string, unknown>>;
  const firstIndia = firstMarkets.IN.timeframes as Record<string, Record<string, unknown>>;
  (firstIndia.daily.rows as unknown[][])[0][EXPECTED_COLUMNS.indexOf("symbol")] =
    "FIRST";
  firstRevision.snapshot_sha256 = await semanticDigest(firstRevision);
  await worker.fetch(await signedRequest(firstRevision), env(kv));

  await worker.fetch(
    await signedRequest(
      await makeSnapshot(
        "2026-08-19",
        "2026-08-18",
        "IN",
        "2026-08-18T16:00:00Z",
      ),
    ),
    env(kv),
  );
  const nextRevision = await makeSnapshot(
    "2026-08-19",
    "2026-08-18",
    "IN",
    "2026-08-18T18:00:00Z",
  );
  const nextMarkets = nextRevision.markets as Record<string, Record<string, unknown>>;
  const nextIndia = nextMarkets.IN.timeframes as Record<string, Record<string, unknown>>;
  (nextIndia.daily.rows as unknown[][])[0][EXPECTED_COLUMNS.indexOf("symbol")] =
    "NEXT";
  nextRevision.snapshot_sha256 = await semanticDigest(nextRevision);
  const response = await worker.fetch(await signedRequest(nextRevision), env(kv));

  assert.equal(response.status, 202);
  assert.equal(kv.puts, 4);
  assert.equal(kv.metadata?.in_session_revision, 1);
});

test("other market advance preserves an exhausted revision allowance", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  const indiaRevision = await makeSnapshot(
    "2026-08-18",
    "2026-08-18",
    "IN",
    "2026-08-18T14:00:00Z",
  );
  const indiaRevisionMarkets = indiaRevision.markets as Record<
    string,
    Record<string, unknown>
  >;
  const indiaRevisionFrames = indiaRevisionMarkets.IN.timeframes as Record<
    string,
    Record<string, unknown>
  >;
  (indiaRevisionFrames.daily.rows as unknown[][])[0][
    EXPECTED_COLUMNS.indexOf("symbol")
  ] = "FIRST";
  indiaRevision.snapshot_sha256 = await semanticDigest(indiaRevision);
  await worker.fetch(await signedRequest(indiaRevision), env(kv));

  const usAdvance = await makeSnapshot(
    "2026-08-18",
    "2026-08-19",
    "US",
    "2026-08-18T16:00:00Z",
  );
  const usAdvanceMarkets = usAdvance.markets as Record<string, unknown>;
  usAdvanceMarkets.IN = indiaRevisionMarkets.IN;
  usAdvance.snapshot_sha256 = await semanticDigest(usAdvance);
  await worker.fetch(await signedRequest(usAdvance), env(kv));
  const secondIndiaRevision = await makeSnapshot(
    "2026-08-18",
    "2026-08-19",
    "IN",
    "2026-08-18T18:00:00Z",
  );
  const secondMarkets = secondIndiaRevision.markets as Record<
    string,
    Record<string, unknown>
  >;
  const secondFrames = secondMarkets.IN.timeframes as Record<
    string,
    Record<string, unknown>
  >;
  (secondFrames.daily.rows as unknown[][])[0][EXPECTED_COLUMNS.indexOf("symbol")] =
    "SECOND";
  secondIndiaRevision.snapshot_sha256 = await semanticDigest(secondIndiaRevision);
  const response = await worker.fetch(
    await signedRequest(secondIndiaRevision),
    env(kv),
  );

  assert.equal(response.status, 409);
  assert.equal(kv.puts, 3);
  assert.equal(kv.metadata?.in_session_revision, 1);
});

test("rejects a same-session change outside the declared update market", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  const changed = await makeSnapshot(
    "2026-08-18",
    "2026-08-18",
    "IN",
    "2026-08-18T14:00:00Z",
  );
  const markets = changed.markets as Record<string, Record<string, unknown>>;
  const unitedStates = markets.US.timeframes as Record<string, Record<string, unknown>>;
  const rows = unitedStates.daily.rows as unknown[][];
  rows[0][EXPECTED_COLUMNS.indexOf("symbol")] = "CHANGED";
  changed.snapshot_sha256 = await semanticDigest(changed);
  const response = await worker.fetch(await signedRequest(changed), env(kv));
  assert.equal(response.status, 409);
  assert.equal(kv.puts, 1);
});

test("accepts one additive history bootstrap across both markets", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  assert.ok(kv.metadata);
  kv.metadata.in_session_revision = 1;
  kv.metadata.us_session_revision = 1;

  const response = await worker.fetch(
    await signedRequest(await makeHistoryBootstrap()),
    env(kv),
  );

  assert.equal(response.status, 202);
  assert.equal(kv.puts, 2);
  assert.equal(kv.metadata?.in_session_revision, 1);
  assert.equal(kv.metadata?.us_session_revision, 1);
});

test("history bootstrap consumes only a changed update-market revision", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  assert.ok(kv.metadata);
  kv.metadata.in_session_revision = 1;
  const changed = await makeCoreChangingHistoryBootstrap();

  const response = await worker.fetch(await signedRequest(changed), env(kv));

  assert.equal(response.status, 202);
  assert.equal(kv.puts, 2);
  assert.equal(kv.metadata?.in_session_revision, 1);
  assert.equal(kv.metadata?.us_session_revision, 1);
});

test("history bootstrap rejects a non-update core change", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  const changed = await makeSnapshot(
    "2026-08-18",
    "2026-08-18",
    "US",
    "2026-08-18T14:00:00Z",
  );
  const markets = changed.markets as Record<string, Record<string, unknown>>;
  const india = markets.IN.timeframes as Record<string, Record<string, unknown>>;
  india.daily.universe_size = 11;
  addHistory(changed);
  changed.snapshot_sha256 = await semanticDigest(changed);

  const response = await worker.fetch(await signedRequest(changed), env(kv));

  assert.equal(response.status, 409);
  assert.equal(kv.puts, 1);
});

test("history bootstrap rejects an exhausted update-market revision", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  assert.ok(kv.metadata);
  kv.metadata.us_session_revision = 1;

  const response = await worker.fetch(
    await signedRequest(await makeCoreChangingHistoryBootstrap()),
    env(kv),
  );

  assert.equal(response.status, 409);
  assert.equal(kv.puts, 1);
});

test("consumed bootstrap revision rejects a later same-session change", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  await worker.fetch(
    await signedRequest(await makeCoreChangingHistoryBootstrap()),
    env(kv),
  );
  assert.ok(kv.value);
  const later = structuredClone(kv.value);
  later.generated_at_utc = "2026-08-18T16:00:00Z";
  const markets = later.markets as Record<string, Record<string, unknown>>;
  const us = markets.US.timeframes as Record<string, Record<string, unknown>>;
  us.daily.universe_size = 12;
  later.snapshot_sha256 = await semanticDigest(later);

  const response = await worker.fetch(await signedRequest(later), env(kv));

  assert.equal(response.status, 409);
  assert.equal(kv.puts, 2);
});

test("allows one write-neutral ignition bootstrap across every HT bucket", async () => {
  const kv = new FakeKV();
  const incoming = await makeHistoryBootstrap("2026-08-18T16:00:00Z");
  const previous = await withoutIgnition(incoming);
  previous.generated_at_utc = "2026-08-18T14:00:00Z";
  kv.value = previous;
  kv.metadata = {
    write_day_ist: new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Kolkata",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date()),
    write_count: 4,
    in_session_revision: 1,
    us_session_revision: 1,
  };

  const response = await worker.fetch(await signedRequest(incoming), env(kv));

  assert.equal(response.status, 202);
  assert.equal(kv.puts, 1);
  assert.equal(kv.metadata?.write_count, 4);
  assert.equal(kv.metadata?.in_session_revision, 1);
  assert.equal(kv.metadata?.us_session_revision, 1);
});

test("rejects a later ignition change after the bootstrap", async () => {
  const kv = new FakeKV();
  const incoming = await makeHistoryBootstrap("2026-08-18T16:00:00Z");
  kv.value = incoming;
  kv.metadata = { write_count: 1, in_session_revision: 1, us_session_revision: 1 };
  const changed = structuredClone(incoming);
  changed.generated_at_utc = "2026-08-18T17:00:00Z";
  const markets = changed.markets as Record<string, Record<string, unknown>>;
  const india = markets.IN.timeframes as Record<string, Record<string, unknown>>;
  const dailyRows = india.daily.rows as unknown[][];
  dailyRows[0][columnIndex("ignition_reason")] = "fast_sha_bounce_signal";
  const history = india.daily.history as Record<string, unknown>;
  const historyRows = (
    (history.periods as Array<Record<string, unknown>>).at(-1)?.rows as unknown[][]
  );
  historyRows[0][HISTORY_ROW_COLUMNS.indexOf("ignition_reason")] =
    "fast_sha_bounce_signal";
  changed.snapshot_sha256 = await semanticDigest(changed);

  const response = await worker.fetch(await signedRequest(changed), env(kv));

  assert.equal(response.status, 409);
  assert.equal(kv.puts, 0);
});

test("rejects malformed history", async () => {
  const kv = new FakeKV();
  const malformed = await makeHistoryBootstrap();
  const markets = malformed.markets as Record<string, Record<string, unknown>>;
  const india = markets.IN.timeframes as Record<string, Record<string, unknown>>;
  const history = india.daily.history as Record<string, unknown>;
  const periods = history.periods as Array<Record<string, unknown>>;
  (periods.at(-1)?.rows as unknown[][])[0][0] = 99;
  malformed.snapshot_sha256 = await semanticDigest(malformed);

  const response = await worker.fetch(await signedRequest(malformed), env(kv));

  assert.equal(response.status, 400);
  assert.equal(kv.puts, 0);
  assert.match(
    String(((await response.json()) as Record<string, unknown>).error),
    /instrument index invalid/,
  );
});

test("validates every bounded history contract field", async () => {
  const cases: Array<{
    name: string;
    error: RegExp;
    mutate: (history: Record<string, unknown>) => void;
  }> = [
    {
      name: "schema version",
      error: /schema version mismatch/,
      mutate: (history) => {
        history.schema_version = "ht-history.v2";
      },
    },
    {
      name: "instrument columns",
      error: /instrument columns mismatch/,
      mutate: (history) => {
        history.instrument_columns = ["exchange", "symbol", "asset_type", "sector"];
      },
    },
    {
      name: "row columns",
      error: /row columns mismatch/,
      mutate: (history) => {
        history.row_columns = [...HISTORY_ROW_COLUMNS].reverse();
      },
    },
    {
      name: "period limit",
      error: /periods invalid/,
      mutate: (history) => {
        history.periods = Array.from({ length: 14 }, (_, index) => ({
          date: `2026-08-${String(index + 5).padStart(2, "0")}`,
          source: "replay",
          rows:
            index === 13
              ? [[0, 1, "HMM", 1, 1, 1, 1, true, "first_bullish_stack_signal"]]
              : [],
        }));
      },
    },
    {
      name: "period source",
      error: /period invalid/,
      mutate: (history) => {
        const periods = history.periods as Array<Record<string, unknown>>;
        periods[0].source = "current";
      },
    },
    {
      name: "period order",
      error: /periods must be sorted and unique/,
      mutate: (history) => {
        const periods = history.periods as Array<Record<string, unknown>>;
        periods.reverse();
      },
    },
    {
      name: "calendar date",
      error: /period invalid/,
      mutate: (history) => {
        const periods = history.periods as Array<Record<string, unknown>>;
        periods[0].date = "2026-02-30";
      },
    },
    {
      name: "instrument index",
      error: /instrument index invalid/,
      mutate: (history) => {
        const periods = history.periods as Array<Record<string, unknown>>;
        (periods.at(-1)?.rows as unknown[][])[0][0] = -1;
      },
    },
    {
      name: "finite dynamics",
      error: /row value invalid/,
      mutate: (history) => {
        const periods = history.periods as Array<Record<string, unknown>>;
        (periods.at(-1)?.rows as unknown[][])[0][3] = null;
      },
    },
    {
      name: "integer turnover",
      error: /row value invalid/,
      mutate: (history) => {
        const periods = history.periods as Array<Record<string, unknown>>;
        (periods.at(-1)?.rows as unknown[][])[0][6] = 1.25;
      },
    },
    {
      name: "duplicate rows",
      error: /duplicate row/,
      mutate: (history) => {
        const periods = history.periods as Array<Record<string, unknown>>;
        const rows = periods.at(-1)?.rows as unknown[][];
        rows.push([...rows[0]]);
      },
    },
    {
      name: "latest period",
      error: /latest period mismatch/,
      mutate: (history) => {
        const periods = history.periods as Array<Record<string, unknown>>;
        const latest = periods.at(-1) as Record<string, unknown>;
        latest.date = "2026-08-19";
      },
    },
    {
      name: "latest values",
      error: /latest rows mismatch/,
      mutate: (history) => {
        const periods = history.periods as Array<Record<string, unknown>>;
        (periods.at(-1)?.rows as unknown[][])[0][5] = 999;
      },
    },
  ];

  for (const fixture of cases) {
    const snapshot = await makeHistoryBootstrap();
    const markets = snapshot.markets as Record<string, Record<string, unknown>>;
    const india = markets.IN.timeframes as Record<string, Record<string, unknown>>;
    fixture.mutate(india.daily.history as Record<string, unknown>);
    snapshot.snapshot_sha256 = await semanticDigest(snapshot);
    await assert.rejects(
      validateSnapshot(snapshot),
      fixture.error,
      fixture.name,
    );
  }
});

test("skips replay-row traversal after validating period descriptors", async () => {
  const snapshot = await makeHistoryBootstrap();
  const markets = snapshot.markets as Record<string, Record<string, unknown>>;
  const india = markets.IN.timeframes as Record<string, Record<string, unknown>>;
  const history = india.daily.history as Record<string, unknown>;
  const periods = history.periods as Array<Record<string, unknown>>;
  periods[0].rows = [[999, "producer-validated replay row"]];
  snapshot.snapshot_sha256 = await semanticDigest(snapshot);

  await validateSnapshot(snapshot);
});

test("latest history equality uses compact numeric tolerances", async () => {
  const cases = [
    { column: "fast_body_pct", delta: 0.00005, accepted: true },
    { column: "close", delta: 0.00005, accepted: true },
    { column: "median_dollar_turnover_20", delta: 0.5, accepted: true },
    { column: "slow_body_pct", delta: 0.000051, accepted: false },
    { column: "median_dollar_turnover_20", delta: 0.50001, accepted: false },
  ];

  for (const fixture of cases) {
    const snapshot = await makeHistoryBootstrap();
    const markets = snapshot.markets as Record<string, Record<string, unknown>>;
    const india = markets.IN.timeframes as Record<string, Record<string, unknown>>;
    const history = india.daily.history as Record<string, unknown>;
    const periods = history.periods as Array<Record<string, unknown>>;
    const historyRow = (periods.at(-1)?.rows as unknown[][])[0];
    const historyIndex = (HISTORY_ROW_COLUMNS as readonly string[]).indexOf(
      fixture.column,
    );
    const latestRow = (india.daily.rows as unknown[][])[0];
    latestRow[columnIndex(fixture.column)] =
      Number(historyRow[historyIndex]) + fixture.delta;
    snapshot.snapshot_sha256 = await semanticDigest(snapshot);

    if (fixture.accepted) {
      await validateSnapshot(snapshot);
    } else {
      await assert.rejects(validateSnapshot(snapshot), /latest rows mismatch/);
    }
  }
});

test("rejects a second both-market history change", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
  await worker.fetch(
    await signedRequest(await makeHistoryBootstrap("2026-08-18T14:00:00Z")),
    env(kv),
  );
  const second = await makeHistoryBootstrap("2026-08-18T16:00:00Z");
  const markets = second.markets as Record<string, Record<string, unknown>>;
  for (const market of ["IN", "US"]) {
    const timeframes = markets[market].timeframes as Record<
      string,
      Record<string, unknown>
    >;
    for (const timeframe of ["daily", "weekly"]) {
      const history = timeframes[timeframe].history as Record<string, unknown>;
      const periods = history.periods as Array<Record<string, unknown>>;
      (periods.at(-1) as Record<string, unknown>).source = "replay";
    }
  }
  second.snapshot_sha256 = await semanticDigest(second);

  const response = await worker.fetch(await signedRequest(second), env(kv));

  assert.equal(response.status, 409);
  assert.equal(kv.puts, 2);
});

test("history bootstrap requires a later generation", async () => {
  const kv = new FakeKV();
  await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));

  const response = await worker.fetch(
    await signedRequest(await makeHistoryBootstrap("2026-08-18T12:00:00Z")),
    env(kv),
  );

  assert.equal(response.status, 409);
  assert.equal(kv.puts, 1);
});

test("rejects corrupted stored snapshot headers", async () => {
  const cases: Array<(stored: Record<string, unknown>) => void> = [
    (stored) => {
      stored.schema_version = "corrupt";
    },
    (stored) => {
      const markets = stored.markets as Record<string, unknown>;
      delete markets.US;
    },
    (stored) => {
      const markets = stored.markets as Record<string, Record<string, unknown>>;
      markets.IN.data_session = "not-a-date";
    },
  ];

  for (const mutate of cases) {
    const kv = new FakeKV();
    await worker.fetch(await signedRequest(await makeSnapshot()), env(kv));
    assert.ok(kv.value);
    mutate(kv.value);
    const next = await makeSnapshot(
      "2026-08-19",
      "2026-08-18",
      "IN",
      "2026-08-19T12:00:00Z",
    );

    const response = await worker.fetch(await signedRequest(next), env(kv));

    assert.equal(response.status, 500);
    assert.equal(kv.puts, 1);
    assert.equal(
      ((await response.json()) as Record<string, unknown>).error,
      "stored snapshot invalid",
    );
  }
});

test("refuses a fifth sequential IST-day write", async () => {
  const kv = new FakeKV();
  kv.value = await makeSnapshot("2026-08-17", "2026-08-18", "IN");
  kv.metadata = {
    write_day_ist: new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Kolkata",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date()),
    write_count: 4,
  };
  const response = await worker.fetch(
    await signedRequest(
      await makeSnapshot(
        "2026-08-18",
        "2026-08-18",
        "IN",
        "2026-08-18T14:00:00Z",
      ),
    ),
    env(kv),
  );
  assert.equal(response.status, 429);
  assert.equal(kv.puts, 0);
});

test("accepts one US Trend Bounce snapshot", async () => {
  const kv = new FakeKV();
  const snapshot = await makeTrendBounceSnapshot();

  await validateTrendBounceSnapshot(snapshot);
  const response = await worker.fetch(
    await trendBounceSignedRequest(snapshot),
    env(kv),
  );

  assert.equal(response.status, 202);
  assert.equal(kv.reads, 1);
  assert.equal(kv.puts, 1);
  assert.equal(
    ((await response.json()) as Record<string, unknown>).write_performed,
    true,
  );
});

test("rejects US Trend Bounce filter members outside the primary signal", async () => {
  const kv = new FakeKV();
  const snapshot = await makeTrendBounceSnapshot();
  const pages = snapshot.pages as Record<string, Record<string, unknown>>;
  const weeklyFilter = pages.weekly.filter as Record<string, unknown>;
  weeklyFilter.weeks = { "2026-08-17": ["NOT_PRIMARY"] };
  snapshot.snapshot_sha256 = await trendBounceSemanticDigest(snapshot);

  const response = await worker.fetch(
    await trendBounceSignedRequest(snapshot),
    env(kv),
  );

  assert.equal(response.status, 400);
  assert.equal(kv.puts, 0);
  assert.match(
    String(((await response.json()) as Record<string, unknown>).error),
    /weekly filter invalid/,
  );
});

test("rejects US rotation totals that disagree with classified counts", async () => {
  const kv = new FakeKV();
  const snapshot = await makeTrendBounceSnapshot();
  const rotation = snapshot.rotation as Record<string, unknown>;
  rotation.totals = [0];
  snapshot.snapshot_sha256 = await trendBounceSemanticDigest(snapshot);

  const response = await worker.fetch(
    await trendBounceSignedRequest(snapshot),
    env(kv),
  );

  assert.equal(response.status, 400);
  assert.equal(kv.puts, 0);
  assert.match(
    String(((await response.json()) as Record<string, unknown>).error),
    /US rotation totals invalid/,
  );
});

test("US Trend Bounce identical retry performs no second write", async () => {
  const kv = new FakeKV();
  const snapshot = await makeTrendBounceSnapshot();

  const first = await worker.fetch(
    await trendBounceSignedRequest(snapshot),
    env(kv),
  );
  const second = await worker.fetch(
    await trendBounceSignedRequest(snapshot),
    env(kv),
  );

  assert.equal(first.status, 202);
  assert.equal(second.status, 200);
  assert.equal(kv.puts, 1);
});

test("allows one US rotation bootstrap after the session revision", async () => {
  const kv = new FakeKV();
  const previous = await makeTrendBounceSnapshot();
  delete previous.rotation;
  const previousPages = previous.pages as Record<string, Record<string, unknown>>;
  delete previousPages.daily.rotation;
  delete previousPages.weekly.rotation;
  previous.snapshot_sha256 = "0".repeat(64);
  kv.value = previous;
  kv.metadata = {
    write_day_ist: new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Kolkata",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date()),
    write_count: 2,
    session_revision: 1,
  };
  const snapshot = await makeTrendBounceSnapshot();

  const response = await worker.fetch(
    await trendBounceSignedRequest(snapshot),
    env(kv),
  );

  assert.equal(response.status, 202);
  assert.equal(kv.puts, 1);
  assert.equal(kv.metadata?.write_count, 2);
  assert.equal(kv.metadata?.session_revision, 1);
});

test("rejects a further US rotation change after the session revision", async () => {
  const kv = new FakeKV();
  const previous = await makeTrendBounceSnapshot();
  kv.value = previous;
  kv.metadata = { write_count: 1, session_revision: 1 };
  const snapshot = await makeTrendBounceSnapshot();
  snapshot.generated_at_utc = "2026-08-18T23:00:00Z";
  const rotation = snapshot.rotation as Record<string, unknown>;
  rotation.requested_asof = "2026-08-19";
  snapshot.snapshot_sha256 = await trendBounceSemanticDigest(snapshot);

  const response = await worker.fetch(
    await trendBounceSignedRequest(snapshot),
    env(kv),
  );

  assert.equal(response.status, 409);
  assert.equal(kv.puts, 0);
});

test("accepts one US complete-history market-events snapshot", async () => {
  const kv = new FakeKV();
  const snapshot = await makeMarketEventsSnapshot();

  await validateMarketEventsSnapshot(snapshot);
  const response = await worker.fetch(
    await marketEventsSignedRequest(snapshot),
    env(kv),
  );

  assert.equal(response.status, 202);
  assert.equal(kv.reads, 1);
  assert.equal(kv.puts, 1);
});

test("market-events identical retry performs no second write", async () => {
  const kv = new FakeKV();
  const snapshot = await makeMarketEventsSnapshot("IN");

  const first = await worker.fetch(await marketEventsSignedRequest(snapshot), env(kv));
  const second = await worker.fetch(await marketEventsSignedRequest(snapshot), env(kv));

  assert.equal(first.status, 202);
  assert.equal(second.status, 200);
  assert.equal(kv.puts, 1);
});

test("accepts a lower India count when its rolling window advances", async () => {
  const kv = new FakeKV();
  const first = await makeMarketEventsSnapshot("IN");
  const firstRecords = first.records as Record<string, Record<string, unknown>>;
  firstRecords["M&M"].count = 2;
  first.row_count = 2;
  first.snapshot_sha256 = await marketEventsSemanticDigest(first);
  await worker.fetch(await marketEventsSignedRequest(first), env(kv));
  const advanced = await makeMarketEventsSnapshot("IN");
  advanced.generated_at_utc = "2026-08-21T01:00:00Z";

  const response = await worker.fetch(
    await marketEventsSignedRequest(advanced),
    env(kv),
  );

  assert.equal(response.status, 202);
  assert.equal(kv.puts, 2);
});

test("allows one India scope migration after the daily write budget", async () => {
  const kv = new FakeKV();
  const previous = await makeMarketEventsSnapshot("IN");
  previous.history_scope = "complete";
  previous.generated_at_utc = "2026-08-20T00:00:00Z";
  previous.snapshot_sha256 = await marketEventsSemanticDigest(previous);
  kv.value = previous;
  kv.metadata = {
    write_day_ist: new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Kolkata",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date()),
    write_count: 2,
  };
  const rolling = await makeMarketEventsSnapshot("IN");
  rolling.generated_at_utc = "2026-08-20T02:00:00Z";
  rolling.snapshot_sha256 = await marketEventsSemanticDigest(rolling);

  const response = await worker.fetch(
    await marketEventsSignedRequest(rolling),
    env(kv),
  );

  assert.equal(response.status, 202);
  assert.equal(kv.puts, 1);
  assert.equal(kv.metadata?.write_count, 3);
});

test("rejects a complete-history India market-events snapshot", async () => {
  const snapshot = await makeMarketEventsSnapshot("IN");
  snapshot.history_scope = "complete";
  snapshot.snapshot_sha256 = await marketEventsSemanticDigest(snapshot);

  await assert.rejects(
    validateMarketEventsSnapshot(snapshot),
    /event set identity mismatch/,
  );
});

test("rejects an India snapshot without its insider event set", async () => {
  const snapshot = await makeMarketEventsSnapshot("IN");
  delete snapshot.related_event_sets;
  snapshot.snapshot_sha256 = await marketEventsSemanticDigest(snapshot);

  await assert.rejects(
    validateMarketEventsSnapshot(snapshot),
    /India insider event set missing/,
  );
});

test("rejects an India event outside its trailing-year window", async () => {
  const snapshot = await makeMarketEventsSnapshot("IN");
  const records = snapshot.records as Record<string, Record<string, unknown>>;
  const record = records["M&M"];
  const events = record.events as unknown[][];
  events[0][0] = "2025-08-19";
  record.first_date = "2025-08-19";
  record.last_date = "2025-08-19";
  snapshot.source_cutoff = "2025-08-19";
  snapshot.snapshot_sha256 = await marketEventsSemanticDigest(snapshot);

  await assert.rejects(
    validateMarketEventsSnapshot(snapshot),
    /event record invalid/,
  );
});

test("rejects a market-events history regression", async () => {
  const kv = new FakeKV();
  const first = await makeMarketEventsSnapshot();
  const firstRecords = first.records as Record<string, Record<string, unknown>>;
  firstRecords.MRNA.count = 2;
  first.row_count = 2;
  first.snapshot_sha256 = await marketEventsSemanticDigest(first);
  await worker.fetch(await marketEventsSignedRequest(first), env(kv));
  const regressed = await makeMarketEventsSnapshot();
  regressed.generated_at_utc = "2026-08-20T02:00:00Z";

  const response = await worker.fetch(
    await marketEventsSignedRequest(regressed),
    env(kv),
  );

  assert.equal(response.status, 409);
  assert.equal(kv.puts, 1);
  assert.match(
    String(((await response.json()) as Record<string, unknown>).error),
    /history regressed/,
  );
});

test("exports no scheduled handler", () => {
  assert.equal("scheduled" in worker, false);
});
