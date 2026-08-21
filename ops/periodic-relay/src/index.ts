import { timingSafeEqual } from "node:crypto";

const MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024;
const MAX_WRITES_PER_IST_DAY = 4;
const SNAPSHOT_KEY = "tsha-hbcs:v1:latest";
const MAX_TREND_BOUNCE_BYTES = 8 * 1024 * 1024;
const MAX_TREND_BOUNCE_WRITES_PER_IST_DAY = 2;
const TREND_BOUNCE_KEY = "us-trend-bounce:v1:latest";
const TREND_BOUNCE_SCHEMA_VERSION = "us-trend-bounce.snapshot.v1";
const TREND_BOUNCE_PAGE_SCHEMA_VERSION = "us-trend-bounce.page.v1";
const TREND_BOUNCE_ALGORITHM_VERSION = "chartink-trend-bounce-translation.v1";
const US_ROTATION_SCHEMA_VERSION = "us-sector-rotation.v1";
const US_ROTATION_METHOD_VERSION = "trend-bounce-membership-sec-sic-proxy.v1";
const US_ROTATION_GROUPS = [
  "Agribusiness",
  "Metals and mining",
  "Energy",
  "Materials",
  "Home construction",
  "Consumer staples",
  "Consumer discretionary",
  "Industrials",
  "Technology",
  "Health care",
  "Transportation",
  "Communication services",
  "Utilities",
  "Retail",
  "Financials",
  "Real estate",
] as const;
const MAX_MARKET_EVENTS_BYTES = 8 * 1024 * 1024;
const MAX_MARKET_EVENT_WRITES_PER_IST_DAY = 2;
const MARKET_EVENTS_KEY_PREFIX = "market-events:v1:";
const MARKET_EVENTS_SCHEMA_VERSION = "market-events.snapshot.v1";
const MARKET_EVENTS_ALGORITHM_VERSION = "market-events-normalization.v1";
const SCHEMA_VERSION = "tsha-hbcs.snapshot.v1";
const ALGORITHM_VERSION = "tsha-hbcs-confluence.v1";
const HISTORY_SCHEMA_VERSION = "ht-history.v1";
const MAX_HISTORY_PERIODS = 13;
const FOUR_DECIMAL_TOLERANCE = 0.000050000001;
const INTEGER_TOLERANCE = 0.500000001;
const MARKETS = ["IN", "US"] as const;
const TIMEFRAMES = ["daily", "weekly"] as const;
const MARKET_EVENT_COLUMNS = [
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
] as const;

export const HISTORY_INSTRUMENT_COLUMNS = [
  "symbol",
  "exchange",
  "asset_type",
  "sector",
] as const;

export const HISTORY_ROW_COLUMNS = [
  "instrument_index",
  "hbcs_bull_component_count",
  "hbcs_components",
  "fast_body_pct",
  "slow_body_pct",
  "close",
  "median_dollar_turnover_20",
  "ignition",
  "ignition_reason",
] as const;

export const LEGACY_EXPECTED_COLUMNS = [
  "market",
  "timeframe",
  "signal_date",
  "symbol",
  "name",
  "exchange",
  "asset_type",
  "sector",
  "industry",
  "close",
  "volume",
  "median_dollar_turnover_20",
  "fast_open",
  "fast_close",
  "fast_body_pct",
  "slow_open",
  "slow_close",
  "slow_body_pct",
  "tsha_fast_bull",
  "tsha_slow_bull",
  "tsha_bull",
  "hbcs_any_bull",
  "hbcs_fresh_any_bull",
  "hbcs_bull_component_count",
  "hbcs_components",
  "hmm_bull",
  "ballista_bull",
  "cts_bull",
  "gts_bull",
  "fresh_hmm_bull",
  "fresh_ballista_bull",
  "fresh_cts_bull",
  "fresh_gts_bull",
] as const;

export const EXPECTED_COLUMNS = [
  ...LEGACY_EXPECTED_COLUMNS,
  "ignition",
  "ignition_reason",
] as const;

const MARKET_COLUMN_INDEX = EXPECTED_COLUMNS.indexOf("market");
const TIMEFRAME_COLUMN_INDEX = EXPECTED_COLUMNS.indexOf("timeframe");
const SIGNAL_DATE_COLUMN_INDEX = EXPECTED_COLUMNS.indexOf("signal_date");
const SYMBOL_COLUMN_INDEX = EXPECTED_COLUMNS.indexOf("symbol");
const EXCHANGE_COLUMN_INDEX = EXPECTED_COLUMNS.indexOf("exchange");
const HBCS_COMPONENT_COUNT_COLUMN_INDEX = EXPECTED_COLUMNS.indexOf(
  "hbcs_bull_component_count",
);
const HBCS_COMPONENTS_COLUMN_INDEX = EXPECTED_COLUMNS.indexOf("hbcs_components");
const FAST_BODY_COLUMN_INDEX = EXPECTED_COLUMNS.indexOf("fast_body_pct");
const SLOW_BODY_COLUMN_INDEX = EXPECTED_COLUMNS.indexOf("slow_body_pct");
const CLOSE_COLUMN_INDEX = EXPECTED_COLUMNS.indexOf("close");
const TURNOVER_COLUMN_INDEX = EXPECTED_COLUMNS.indexOf(
  "median_dollar_turnover_20",
);
const IGNITION_COLUMN_INDEX = EXPECTED_COLUMNS.indexOf("ignition");
const IGNITION_REASON_COLUMN_INDEX = EXPECTED_COLUMNS.indexOf("ignition_reason");
const HISTORY_INSTRUMENT_COLUMN_INDEXES = HISTORY_INSTRUMENT_COLUMNS.map(
  (column) => EXPECTED_COLUMNS.indexOf(column),
);

type JsonObject = Record<string, unknown>;
type WriteMetadata = {
  bytes: number;
  received_at: string;
  sha256: string;
  snapshot_sha256: string;
  write_day_ist: string;
  write_count: number;
  in_session: string;
  in_session_revision?: number;
  us_session: string;
  us_session_revision?: number;
};

type TrendBounceWriteMetadata = {
  bytes: number;
  received_at: string;
  sha256: string;
  snapshot_sha256: string;
  write_day_ist: string;
  write_count: number;
  data_session: string;
  weekly_session: string;
  session_revision: number;
};

type MarketEventsWriteMetadata = {
  bytes: number;
  received_at: string;
  sha256: string;
  snapshot_sha256: string;
  write_day_ist: string;
  write_count: number;
  market: (typeof MARKETS)[number];
  source_cutoff: string;
  row_count: number;
};

function json(body: JsonObject, status = 200): Response {
  return Response.json(body, {
    status,
    headers: { "cache-control": "no-store" },
  });
}

function encode(value: string): Uint8Array {
  return new TextEncoder().encode(value);
}

function authorized(request: Request, token: string): boolean {
  const supplied = request.headers.get("authorization") ?? "";
  const expected = `Bearer ${token}`;
  const suppliedBytes = encode(supplied);
  const expectedBytes = encode(expected);
  if (suppliedBytes.byteLength !== expectedBytes.byteLength) return false;
  return timingSafeEqual(suppliedBytes, expectedBytes);
}

function toHex(value: ArrayBuffer): string {
  return Array.from(new Uint8Array(value), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

function isObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isIsoDate(value: unknown): value is string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function isCalendarDate(value: unknown): value is string {
  if (!isIsoDate(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function mondayOf(value: string): string | null {
  if (!isCalendarDate(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  const daysSinceMonday = (parsed.getUTCDay() + 6) % 7;
  parsed.setUTCDate(parsed.getUTCDate() - daysSinceMonday);
  return parsed.toISOString().slice(0, 10);
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (isObject(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

async function sha256(value: string | ArrayBuffer): Promise<string> {
  const bytes = typeof value === "string" ? encode(value) : value;
  return toHex(await crypto.subtle.digest("SHA-256", bytes));
}

function semanticPayload(snapshot: JsonObject): JsonObject {
  return {
    schema_version: snapshot.schema_version,
    algorithm_version: snapshot.algorithm_version,
    columns: snapshot.columns,
    markets: snapshot.markets,
  };
}

export async function semanticDigest(snapshot: JsonObject): Promise<string> {
  return sha256(canonical(semanticPayload(snapshot)));
}

async function semanticDigestFromCanonicalWire(value: string): Promise<string | null> {
  // The publisher emits sorted, compact JSON. Other encodings use semanticDigest.
  const algorithmMarker = '{"algorithm_version":';
  const columnsMarker = ',"columns":';
  const generatedMarker = ',"generated_at_utc":';
  const marketsMarker = ',"markets":';
  const producerMarker = ',"producer_commit":';
  const schemaMarker = ',"schema_version":';
  const digestMarker = ',"snapshot_sha256":';
  if (!value.startsWith(algorithmMarker)) return null;
  const columnsAt = value.indexOf(columnsMarker, algorithmMarker.length);
  const generatedAt = value.indexOf(generatedMarker, columnsAt + columnsMarker.length);
  const marketsAt = value.indexOf(marketsMarker, generatedAt + generatedMarker.length);
  const producerAt = value.indexOf(producerMarker, marketsAt + marketsMarker.length);
  const schemaAt = value.indexOf(schemaMarker, producerAt + producerMarker.length);
  const digestAt = value.indexOf(digestMarker, schemaAt + schemaMarker.length);
  if (
    columnsAt < 0 ||
    generatedAt < 0 ||
    marketsAt < 0 ||
    producerAt < 0 ||
    schemaAt < 0 ||
    digestAt < 0
  ) {
    return null;
  }
  const semantic =
    `${algorithmMarker}${value.slice(algorithmMarker.length, columnsAt)}` +
    `${columnsMarker}${value.slice(columnsAt + columnsMarker.length, generatedAt)}` +
    `${marketsMarker}${value.slice(marketsAt + marketsMarker.length, producerAt)}` +
    `${schemaMarker}${value.slice(schemaAt + schemaMarker.length, digestAt)}}`;
  return sha256(semantic);
}

function requireExactColumns(value: unknown): string[] {
  if (!Array.isArray(value) || value.length !== EXPECTED_COLUMNS.length) {
    throw new Error("columns mismatch");
  }
  for (let index = 0; index < EXPECTED_COLUMNS.length; index += 1) {
    if (value[index] !== EXPECTED_COLUMNS[index]) throw new Error("columns mismatch");
  }
  return value as string[];
}

function hasExactColumns(value: unknown, expected: readonly string[]): boolean {
  return (
    Array.isArray(value) &&
    value.length === expected.length &&
    value.every((column, index) => column === expected[index])
  );
}

function requireExactStringArray(
  value: unknown,
  expected: readonly string[],
  error: string,
): void {
  if (!Array.isArray(value) || value.length !== expected.length) {
    throw new Error(error);
  }
  for (let index = 0; index < expected.length; index += 1) {
    if (value[index] !== expected[index]) throw new Error(error);
  }
}

function numericWithin(value: unknown, expected: unknown, tolerance: number): boolean {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    typeof expected === "number" &&
    Number.isFinite(expected) &&
    Math.abs(value - expected) <= tolerance
  );
}

function historyDynamicsMatch(
  historyRow: unknown[],
  latestRow: unknown[],
): boolean {
  if (
    historyRow[1] !== latestRow[HBCS_COMPONENT_COUNT_COLUMN_INDEX] ||
    historyRow[2] !== latestRow[HBCS_COMPONENTS_COLUMN_INDEX] ||
    historyRow[7] !== latestRow[IGNITION_COLUMN_INDEX] ||
    historyRow[8] !== latestRow[IGNITION_REASON_COLUMN_INDEX]
  ) {
    return false;
  }
  return (
    numericWithin(
      historyRow[3],
      latestRow[FAST_BODY_COLUMN_INDEX],
      FOUR_DECIMAL_TOLERANCE,
    ) &&
    numericWithin(
      historyRow[4],
      latestRow[SLOW_BODY_COLUMN_INDEX],
      FOUR_DECIMAL_TOLERANCE,
    ) &&
    numericWithin(
      historyRow[5],
      latestRow[CLOSE_COLUMN_INDEX],
      FOUR_DECIMAL_TOLERANCE,
    ) &&
    numericWithin(
      historyRow[6],
      latestRow[TURNOVER_COLUMN_INDEX],
      INTEGER_TOLERANCE,
    )
  );
}

function validateHistory(
  market: string,
  timeframe: string,
  value: unknown,
  signalDate: string,
  latestRows: unknown[][],
): void {
  const prefix = `${market} ${timeframe} history`;
  if (!isObject(value)) throw new Error(`${prefix} invalid`);
  if (value.schema_version !== HISTORY_SCHEMA_VERSION) {
    throw new Error(`${prefix} schema version mismatch`);
  }
  requireExactStringArray(
    value.instrument_columns,
    HISTORY_INSTRUMENT_COLUMNS,
    `${prefix} instrument columns mismatch`,
  );
  requireExactStringArray(
    value.row_columns,
    HISTORY_ROW_COLUMNS,
    `${prefix} row columns mismatch`,
  );
  if (!Array.isArray(value.instruments)) {
    throw new Error(`${prefix} instruments invalid`);
  }
  if (
    !Array.isArray(value.periods) ||
    value.periods.length < 1 ||
    value.periods.length > MAX_HISTORY_PERIODS
  ) {
    throw new Error(`${prefix} periods invalid`);
  }
  let previousDate = "";
  // Replay rows are producer-validated; the relay bounds CPU by scanning descriptors only.
  for (const period of value.periods) {
    if (
      !isObject(period) ||
      !isCalendarDate(period.date) ||
      !["stored", "replay"].includes(period.source as string) ||
      !Array.isArray(period.rows)
    ) {
      throw new Error(`${prefix} period invalid`);
    }
    if (period.date <= previousDate) {
      throw new Error(`${prefix} periods must be sorted and unique`);
    }
    previousDate = period.date;
  }
  if (previousDate !== signalDate) {
    throw new Error(`${prefix} latest period mismatch`);
  }
  const latestPeriod = value.periods[value.periods.length - 1] as JsonObject;
  const latestPeriodRows = latestPeriod.rows as unknown[][];
  const usedInstrumentIndexes = new Set<number>();
  const referencedInstruments = new Set<string>();
  for (const row of latestPeriodRows) {
    if (!Array.isArray(row) || row.length !== HISTORY_ROW_COLUMNS.length) {
      throw new Error(`${prefix} row shape mismatch`);
    }
    const instrumentIndex = row[0];
    if (
      !Number.isSafeInteger(instrumentIndex) ||
      Number(instrumentIndex) < 0 ||
      Number(instrumentIndex) >= value.instruments.length
    ) {
      throw new Error(`${prefix} instrument index invalid`);
    }
    const numericInstrumentIndex = Number(instrumentIndex);
    if (usedInstrumentIndexes.has(numericInstrumentIndex)) {
      throw new Error(`${prefix} duplicate row`);
    }
    usedInstrumentIndexes.add(numericInstrumentIndex);
    const instrument = value.instruments[numericInstrumentIndex];
    if (
      !Array.isArray(instrument) ||
      instrument.length !== HISTORY_INSTRUMENT_COLUMNS.length ||
      !instrument.every((field) => typeof field === "string") ||
      instrument[0].length === 0
    ) {
      throw new Error(`${prefix} instrument invalid`);
    }
    const instrumentKey = JSON.stringify(instrument);
    if (referencedInstruments.has(instrumentKey)) {
      throw new Error(`${prefix} duplicate instrument`);
    }
    referencedInstruments.add(instrumentKey);
    const componentCount = row[1];
    const turnover = row[6];
    if (
      !Number.isSafeInteger(componentCount) ||
      Number(componentCount) < 0 ||
      typeof row[2] !== "string" ||
      !Number.isSafeInteger(turnover) ||
      typeof row[3] !== "number" ||
      !Number.isFinite(row[3]) ||
      typeof row[4] !== "number" ||
      !Number.isFinite(row[4]) ||
      typeof row[5] !== "number" ||
      !Number.isFinite(row[5]) ||
      typeof row[7] !== "boolean" ||
      typeof row[8] !== "string" ||
      !["", "first_bullish_stack_signal", "fast_sha_bounce_signal"].includes(
        row[8] as string,
      ) ||
      (row[7] ? row[8] === "" : row[8] !== "")
    ) {
      throw new Error(`${prefix} row value invalid`);
    }
  }
  const latestBySymbol = new Map<string, unknown[]>();
  for (const row of latestRows) {
    const symbol = row[SYMBOL_COLUMN_INDEX];
    if (typeof symbol !== "string" || latestBySymbol.has(symbol)) {
      throw new Error(`${prefix} latest symbols invalid`);
    }
    latestBySymbol.set(symbol, row);
  }
  if (latestPeriodRows.length !== latestBySymbol.size) {
    throw new Error(`${prefix} latest rows mismatch`);
  }
  for (const historyRow of latestPeriodRows) {
    const instrument = value.instruments[Number(historyRow[0])] as unknown[];
    const symbol = instrument[0] as string;
    const latestRow = latestBySymbol.get(symbol);
    if (!latestRow) throw new Error(`${prefix} latest rows mismatch`);
    const instrumentMatches = instrument.every(
      (field, index) => field === latestRow[HISTORY_INSTRUMENT_COLUMN_INDEXES[index]],
    );
    if (!instrumentMatches || !historyDynamicsMatch(historyRow, latestRow)) {
      throw new Error(`${prefix} latest rows mismatch`);
    }
  }
}

function serialisedEqual(left: unknown, right: unknown): boolean {
  // Admitted publisher payloads use canonical key order; inequality is conservative.
  return JSON.stringify(left) === JSON.stringify(right);
}

function ignitionComparisonMarkets(snapshot: JsonObject): JsonObject | null {
  if (!isObject(snapshot.markets) || !Array.isArray(snapshot.columns)) return null;
  const ignitionIndex = snapshot.columns.indexOf("ignition");
  const ignitionReasonIndex = snapshot.columns.indexOf("ignition_reason");
  const hasIgnition = ignitionIndex >= 0 || ignitionReasonIndex >= 0;
  if (hasIgnition && (ignitionIndex < 0 || ignitionReasonIndex < 0)) return null;
  const markets = structuredClone(snapshot.markets) as JsonObject;
  for (const market of MARKETS) {
    const marketValue = markets[market];
    if (!isObject(marketValue) || !isObject(marketValue.timeframes)) return null;
    for (const timeframe of TIMEFRAMES) {
      const bucket = marketValue.timeframes[timeframe];
      if (!isObject(bucket) || !Array.isArray(bucket.rows)) return null;
      if (hasIgnition) {
        bucket.rows = bucket.rows.map((row) => {
          if (!Array.isArray(row)) return row;
          return row.filter(
            (_, index) => index !== ignitionIndex && index !== ignitionReasonIndex,
          );
        });
      }
      if (!isObject(bucket.history)) continue;
      const history = bucket.history;
      if (!Array.isArray(history.row_columns) || !Array.isArray(history.periods)) {
        return null;
      }
      const historyIgnitionIndex = history.row_columns.indexOf("ignition");
      const historyReasonIndex = history.row_columns.indexOf("ignition_reason");
      const historyHasIgnition = historyIgnitionIndex >= 0 || historyReasonIndex >= 0;
      if (
        historyHasIgnition &&
        (historyIgnitionIndex < 0 || historyReasonIndex < 0)
      ) {
        return null;
      }
      if (historyHasIgnition) {
        history.row_columns = history.row_columns.filter(
          (_, index) =>
            index !== historyIgnitionIndex && index !== historyReasonIndex,
        );
      }
      history.periods = history.periods.map((period) => {
        if (!isObject(period) || !Array.isArray(period.rows)) return period;
        const normalised = { ...period };
        delete normalised.source;
        if (historyHasIgnition) {
          normalised.rows = period.rows.map((row) => {
            if (!Array.isArray(row)) return row;
            return row.filter(
              (_, index) =>
                index !== historyIgnitionIndex && index !== historyReasonIndex,
            );
          });
        }
        return normalised;
      });
    }
  }
  return markets;
}

function classifyIgnitionBootstrap(
  previous: JsonObject,
  next: JsonObject,
): boolean {
  if (
    !hasExactColumns(previous.columns, LEGACY_EXPECTED_COLUMNS) ||
    !hasExactColumns(next.columns, EXPECTED_COLUMNS)
  ) {
    return false;
  }
  const previousMarkets = ignitionComparisonMarkets(previous);
  const nextMarkets = ignitionComparisonMarkets(next);
  return (
    previousMarkets !== null &&
    nextMarkets !== null &&
    canonical(previousMarkets) === canonical(nextMarkets)
  );
}

function bucketCoreChanged(left: JsonObject, right: JsonObject): boolean {
  const coreKeys = (value: JsonObject): string[] =>
    Object.keys(value)
      .filter(
        (key) =>
          key !== "history" &&
          key !== "appearance_periods" &&
          key !== "appearance_bits",
      )
      .sort();
  const leftKeys = coreKeys(left);
  const rightKeys = coreKeys(right);
  if (!serialisedEqual(leftKeys, rightKeys)) return true;
  for (const key of leftKeys) {
    if (key !== "rows" && !serialisedEqual(left[key], right[key])) return true;
  }
  return !serialisedEqual(left.rows, right.rows);
}

type HistoryBootstrap = { updateCoreChanged: boolean };

function classifyHistoryBootstrap(
  previousMarkets: JsonObject,
  nextMarkets: JsonObject,
  updateMarket: (typeof MARKETS)[number],
): HistoryBootstrap | null {
  let updateCoreChanged = false;
  for (const market of MARKETS) {
    const previousMarket = previousMarkets[market];
    const nextMarket = nextMarkets[market];
    if (!isObject(previousMarket) || !isObject(nextMarket)) return null;
    if (previousMarket.data_session !== nextMarket.data_session) return null;
    if (!isObject(previousMarket.timeframes) || !isObject(nextMarket.timeframes)) {
      return null;
    }
    const previousMarketCore = { ...previousMarket };
    const nextMarketCore = { ...nextMarket };
    delete previousMarketCore.timeframes;
    delete nextMarketCore.timeframes;
    if (!serialisedEqual(previousMarketCore, nextMarketCore)) return null;
    for (const timeframe of TIMEFRAMES) {
      const previousBucket = previousMarket.timeframes[timeframe];
      const nextBucket = nextMarket.timeframes[timeframe];
      if (!isObject(previousBucket) || !isObject(nextBucket)) return null;
      if (
        Object.hasOwn(previousBucket, "history") ||
        !Object.hasOwn(nextBucket, "history")
      ) {
        return null;
      }
      const coreChanged = bucketCoreChanged(previousBucket, nextBucket);
      if (coreChanged && market !== updateMarket) return null;
      if (coreChanged) updateCoreChanged = true;
    }
  }
  return { updateCoreChanged };
}

function marketContentChanged(
  previousMarket: JsonObject,
  nextMarket: JsonObject,
): boolean {
  const previousCore = { ...previousMarket };
  const nextCore = { ...nextMarket };
  delete previousCore.timeframes;
  delete nextCore.timeframes;
  if (!serialisedEqual(previousCore, nextCore)) return true;
  if (!isObject(previousMarket.timeframes) || !isObject(nextMarket.timeframes)) {
    return true;
  }
  for (const timeframe of TIMEFRAMES) {
    const previousBucket = previousMarket.timeframes[timeframe];
    const nextBucket = nextMarket.timeframes[timeframe];
    if (!isObject(previousBucket) || !isObject(nextBucket)) return true;
    if (bucketCoreChanged(previousBucket, nextBucket)) return true;
    for (const field of ["appearance_periods", "appearance_bits"]) {
      if (!serialisedEqual(previousBucket[field], nextBucket[field])) return true;
    }
    const previousHasHistory = Object.hasOwn(previousBucket, "history");
    const nextHasHistory = Object.hasOwn(nextBucket, "history");
    if (previousHasHistory !== nextHasHistory) return true;
    if (
      previousHasHistory &&
      canonical(previousBucket.history) !== canonical(nextBucket.history)
    ) {
      return true;
    }
  }
  return false;
}

function validateBucket(
  market: string,
  timeframe: string,
  value: unknown,
  columns: string[],
): { signalDate: string; rowCount: number } {
  if (!isObject(value)) throw new Error(`${market} ${timeframe} bucket missing`);
  if (!isIsoDate(value.signal_date)) throw new Error(`${market} ${timeframe} date invalid`);
  if (!Number.isSafeInteger(value.shortlist_size) || Number(value.shortlist_size) < 0) {
    throw new Error(`${market} ${timeframe} shortlist size invalid`);
  }
  if (!Array.isArray(value.rows) || value.rows.length !== value.shortlist_size) {
    throw new Error(`${market} ${timeframe} row count mismatch`);
  }
  const keys = new Set<string>();
  for (const row of value.rows) {
    if (!Array.isArray(row) || row.length !== columns.length) {
      throw new Error(`${market} ${timeframe} row shape mismatch`);
    }
    if (
      row[MARKET_COLUMN_INDEX] !== market ||
      row[TIMEFRAME_COLUMN_INDEX] !== timeframe ||
      row[SIGNAL_DATE_COLUMN_INDEX] !== value.signal_date
    ) {
      throw new Error(`${market} ${timeframe} row identity mismatch`);
    }
    const key = [
      row[MARKET_COLUMN_INDEX],
      row[TIMEFRAME_COLUMN_INDEX],
      row[SIGNAL_DATE_COLUMN_INDEX],
      row[EXCHANGE_COLUMN_INDEX],
      row[SYMBOL_COLUMN_INDEX],
    ].join("|");
    if (keys.has(key)) throw new Error(`${market} ${timeframe} duplicate row key`);
    keys.add(key);
  }
  if (Object.hasOwn(value, "history")) {
    validateHistory(
      market,
      timeframe,
      value.history,
      value.signal_date,
      value.rows,
    );
  }
  return { signalDate: value.signal_date, rowCount: value.rows.length };
}

export async function validateSnapshot(
  value: unknown,
  precomputedSemanticDigest?: string,
): Promise<JsonObject> {
  if (!isObject(value)) throw new Error("snapshot root must be an object");
  if (value.schema_version !== SCHEMA_VERSION) throw new Error("schema version mismatch");
  if (value.algorithm_version !== ALGORITHM_VERSION) {
    throw new Error("algorithm version mismatch");
  }
  if (!MARKETS.includes(value.update_market as (typeof MARKETS)[number])) {
    throw new Error("update market invalid");
  }
  if (!isIsoDate(value.target_session)) throw new Error("target session invalid");
  if (typeof value.producer_commit !== "string" || value.producer_commit.length < 7) {
    throw new Error("producer commit invalid");
  }
  if (
    typeof value.generated_at_utc !== "string" ||
    !Number.isFinite(Date.parse(value.generated_at_utc))
  ) {
    throw new Error("generated timestamp invalid");
  }
  const columns = requireExactColumns(value.columns);
  if (!isObject(value.markets)) throw new Error("markets missing");
  let rowCount = 0;
  for (const market of MARKETS) {
    const marketValue = value.markets[market];
    if (!isObject(marketValue) || !isObject(marketValue.timeframes)) {
      throw new Error(`${market} market payload missing`);
    }
    const buckets: Record<string, { signalDate: string; rowCount: number }> = {};
    for (const timeframe of TIMEFRAMES) {
      buckets[timeframe] = validateBucket(
        market,
        timeframe,
        marketValue.timeframes[timeframe],
        columns,
      );
      rowCount += buckets[timeframe].rowCount;
    }
    if (marketValue.data_session !== buckets.daily.signalDate) {
      throw new Error(`${market} data session mismatch`);
    }
    const activeWeek = mondayOf(buckets.daily.signalDate);
    if (activeWeek === null || buckets.weekly.signalDate !== activeWeek) {
      throw new Error(`${market} weekly session does not match active week`);
    }
  }
  const updatedMarket = value.update_market as string;
  const updated = value.markets[updatedMarket] as JsonObject;
  if (updated.data_session !== value.target_session) {
    throw new Error("updated market target mismatch");
  }
  if (value.row_count !== rowCount) throw new Error("total row count mismatch");
  if (typeof value.snapshot_sha256 !== "string") throw new Error("snapshot digest missing");
  const calculatedDigest =
    precomputedSemanticDigest ?? (await semanticDigest(value));
  if (calculatedDigest !== value.snapshot_sha256) {
    throw new Error("snapshot digest mismatch");
  }
  return value;
}

function validateStoredSnapshotHeader(value: unknown): JsonObject {
  if (!isObject(value)) throw new Error("stored snapshot root invalid");
  if (
    value.schema_version !== SCHEMA_VERSION ||
    value.algorithm_version !== ALGORITHM_VERSION
  ) {
    throw new Error("stored snapshot schema invalid");
  }
  if (
    !hasExactColumns(value.columns, EXPECTED_COLUMNS) &&
    !hasExactColumns(value.columns, LEGACY_EXPECTED_COLUMNS)
  ) {
    throw new Error("stored snapshot columns invalid");
  }
  if (
    typeof value.generated_at_utc !== "string" ||
    !Number.isFinite(Date.parse(value.generated_at_utc)) ||
    typeof value.snapshot_sha256 !== "string" ||
    !/^[a-f0-9]{64}$/.test(value.snapshot_sha256) ||
    !isObject(value.markets)
  ) {
    throw new Error("stored snapshot header invalid");
  }
  for (const market of MARKETS) {
    const marketValue = value.markets[market];
    if (
      !isObject(marketValue) ||
      !isCalendarDate(marketValue.data_session) ||
      !isObject(marketValue.timeframes)
    ) {
      throw new Error(`stored ${market} market invalid`);
    }
    const daily = marketValue.timeframes.daily;
    const weekly = marketValue.timeframes.weekly;
    if (
      !isObject(daily) ||
      !isCalendarDate(daily.signal_date) ||
      daily.signal_date !== marketValue.data_session ||
      !isObject(weekly) ||
      !isCalendarDate(weekly.signal_date) ||
      weekly.signal_date > daily.signal_date
    ) {
      throw new Error(`stored ${market} sessions invalid`);
    }
  }
  return value;
}

function istDay(now: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

async function receiveSnapshot(request: Request, env: Env): Promise<Response> {
  if (!env.INGEST_TOKEN || !authorized(request, env.INGEST_TOKEN)) {
    return json({ status: "rejected" }, 401);
  }
  if (!(request.headers.get("content-type") ?? "").startsWith("application/json")) {
    return json({ status: "rejected", error: "content-type" }, 415);
  }
  const rawLength = request.headers.get("content-length");
  const contentLength = rawLength === null ? NaN : Number(rawLength);
  if (
    !Number.isSafeInteger(contentLength) ||
    contentLength < 1 ||
    contentLength > MAX_SNAPSHOT_BYTES
  ) {
    return json({ status: "rejected", error: "size" }, 413);
  }
  const claimedDigest = request.headers.get("x-content-sha256") ?? "";
  if (!/^[a-f0-9]{64}$/.test(claimedDigest)) {
    return json({ status: "rejected", error: "digest" }, 400);
  }
  const raw = await request.arrayBuffer();
  if (raw.byteLength !== contentLength || (await sha256(raw)) !== claimedDigest) {
    return json({ status: "rejected", error: "digest" }, 400);
  }
  let snapshot: JsonObject;
  try {
    const decoded = new TextDecoder().decode(raw);
    const parsed = JSON.parse(decoded);
    const wireDigest = await semanticDigestFromCanonicalWire(decoded);
    snapshot = await validateSnapshot(parsed, wireDigest ?? undefined);
  } catch (error) {
    return json(
      { status: "rejected", error: error instanceof Error ? error.message : "invalid" },
      400,
    );
  }

  const current = await env.BUNDLES.getWithMetadata<unknown, WriteMetadata>(SNAPSHOT_KEY, {
    type: "json",
  });
  let previousSnapshot: JsonObject | null = null;
  let historyBootstrap: HistoryBootstrap | null = null;
  let ignitionBootstrap = false;
  const changedMarkets = new Set<(typeof MARKETS)[number]>();
  if (current.value !== null) {
    let previous: JsonObject;
    try {
      previous = validateStoredSnapshotHeader(current.value);
    } catch {
      return json({ status: "error", error: "stored snapshot invalid" }, 500);
    }
    previousSnapshot = previous;
    if (previous.snapshot_sha256 === snapshot.snapshot_sha256) {
      return json({ status: "unchanged", write_performed: false }, 200);
    }
    const previousMarkets = previous.markets as JsonObject;
    const nextMarkets = snapshot.markets as JsonObject;
    let allSessionsSame = true;
    for (const market of MARKETS) {
      const previousMarket = previousMarkets[market] as JsonObject;
      const nextMarket = nextMarkets[market] as JsonObject;
      const previousSession = previousMarket.data_session as string;
      const nextSession = nextMarket.data_session as string;
      if (nextSession < previousSession) {
        return json({ status: "conflict", error: `${market} session regressed` }, 409);
      }
      if (nextSession !== previousSession) {
        allSessionsSame = false;
        changedMarkets.add(market);
      }
    }
    if (allSessionsSame) {
      ignitionBootstrap = classifyIgnitionBootstrap(previous, snapshot);
    }
    if (allSessionsSame && !ignitionBootstrap) {
      historyBootstrap = classifyHistoryBootstrap(
        previousMarkets,
        nextMarkets,
        snapshot.update_market as (typeof MARKETS)[number],
      );
    }
    if (ignitionBootstrap) {
      for (const market of MARKETS) changedMarkets.add(market);
    } else if (historyBootstrap) {
      for (const market of MARKETS) changedMarkets.add(market);
    } else {
      for (const market of MARKETS) {
        if (changedMarkets.has(market)) continue;
        if (
          marketContentChanged(
            previousMarkets[market] as JsonObject,
            nextMarkets[market] as JsonObject,
          )
        ) {
          changedMarkets.add(market);
        }
      }
    }
    const sameSessionChanges = [...changedMarkets].filter((market) => {
      const previousSession = (previousMarkets[market] as JsonObject)
        .data_session as string;
      const nextSession = (nextMarkets[market] as JsonObject).data_session as string;
      return nextSession === previousSession;
    });
    if (
      !historyBootstrap &&
      !ignitionBootstrap &&
      (sameSessionChanges.length > 1 ||
        (sameSessionChanges.length === 1 &&
          sameSessionChanges[0] !== snapshot.update_market))
    ) {
      return json(
        { status: "conflict", error: "content changed outside update market" },
        409,
      );
    }
    const previousGenerated = Date.parse(previous.generated_at_utc as string);
    const nextGenerated = Date.parse(snapshot.generated_at_utc as string);
    if (nextGenerated <= previousGenerated) {
      return json({ status: "conflict", error: "generation did not advance" }, 409);
    }
  }

  const now = new Date();
  const day = istDay(now);
  const previousCount =
    current.metadata?.write_day_ist === day ? Number(current.metadata.write_count) : 0;
  if (!Number.isSafeInteger(previousCount) || previousCount < 0) {
    return json({ status: "error", error: "stored write budget invalid" }, 500);
  }
  if (previousCount >= MAX_WRITES_PER_IST_DAY && !ignitionBootstrap) {
    return json({ status: "budget_exhausted", write_performed: false }, 429);
  }
  const markets = snapshot.markets as JsonObject;
  const previousMarkets = previousSnapshot?.markets as JsonObject | undefined;
  const updateMarket = snapshot.update_market as (typeof MARKETS)[number];
  const revisions: Record<(typeof MARKETS)[number], number> = { IN: 0, US: 0 };
  for (const market of MARKETS) {
    const field = market === "IN" ? "in_session_revision" : "us_session_revision";
    const previousRevision = Number(current.metadata?.[field] ?? 0);
    if (!Number.isSafeInteger(previousRevision) || previousRevision < 0) {
      return json({ status: "error", error: "stored revision invalid" }, 500);
    }
    if (!previousMarkets) continue;
    if (ignitionBootstrap) {
      revisions[market] = previousRevision;
      continue;
    }
    const previousMarket = previousMarkets[market] as JsonObject;
    const nextMarket = markets[market] as JsonObject;
    const previousSession = previousMarket.data_session as string;
    const nextSession = nextMarket.data_session as string;
    if (nextSession > previousSession) continue;
    if (!changedMarkets.has(market)) {
      revisions[market] = previousRevision;
      continue;
    }
    if (historyBootstrap) {
      if (market === updateMarket && historyBootstrap.updateCoreChanged) {
        if (previousRevision >= 1) {
          return json(
            { status: "conflict", error: "session revision exhausted" },
            409,
          );
        }
        revisions[market] = previousRevision + 1;
      } else {
        revisions[market] = previousRevision;
      }
      continue;
    }
    if (market !== updateMarket) {
      return json(
        { status: "conflict", error: "content changed outside update market" },
        409,
      );
    }
    if (previousRevision >= 1) {
      return json({ status: "conflict", error: "session revision exhausted" }, 409);
    }
    revisions[market] = previousRevision + 1;
  }
  const metadata: WriteMetadata = {
    bytes: raw.byteLength,
    received_at: now.toISOString(),
    sha256: claimedDigest,
    snapshot_sha256: snapshot.snapshot_sha256 as string,
    write_day_ist: day,
    write_count: ignitionBootstrap ? previousCount : previousCount + 1,
    in_session: (markets.IN as JsonObject).data_session as string,
    in_session_revision: revisions.IN,
    us_session: (markets.US as JsonObject).data_session as string,
    us_session_revision: revisions.US,
  };
  await env.BUNDLES.put(SNAPSHOT_KEY, raw, { metadata });
  console.log(
    JSON.stringify({
      event: "tsha-hbcs-snapshot-accepted",
      bytes: raw.byteLength,
      in_session: metadata.in_session,
      us_session: metadata.us_session,
      write_count: metadata.write_count,
    }),
  );
  return json(
    {
      status: "accepted",
      write_performed: true,
      write_count: metadata.write_count,
    },
    202,
  );
}

function requireTrendBounceMembershipMap(
  value: unknown,
  periods: string[],
  primary: Map<string, Set<string>>,
  label: string,
): void {
  if (!isObject(value)) throw new Error(`${label} invalid`);
  const keys = Object.keys(value).sort();
  if (keys.length !== periods.length || keys.some((key, index) => key !== periods[index])) {
    throw new Error(`${label} periods mismatch`);
  }
  for (const period of periods) {
    const symbols = value[period];
    if (!Array.isArray(symbols)) throw new Error(`${label} invalid`);
    const typed = symbols.filter((symbol): symbol is string => typeof symbol === "string");
    if (
      typed.length !== symbols.length ||
      new Set(typed).size !== typed.length ||
      typed.some((symbol, index) => !symbol || symbol !== [...typed].sort()[index]) ||
      typed.some((symbol) => !primary.get(period)?.has(symbol))
    ) {
      throw new Error(`${label} invalid`);
    }
  }
}

function requireTrendBouncePage(
  value: unknown,
  timeframe: "daily" | "weekly",
  expectedDate: string,
): JsonObject {
  if (!isObject(value)) throw new Error(`${timeframe} page invalid`);
  if (
    value.schema_version !== TREND_BOUNCE_PAGE_SCHEMA_VERSION ||
    value.timeframe !== timeframe ||
    value.data_cutoff !== expectedDate
  ) {
    throw new Error(`${timeframe} page identity mismatch`);
  }
  const weeks = value.weeks;
  const maxPeriods = timeframe === "daily" ? 90 : 160;
  if (!Array.isArray(weeks) || weeks.length < 1 || weeks.length > maxPeriods) {
    throw new Error(`${timeframe} periods invalid`);
  }
  const periods: string[] = [];
  const primary = new Map<string, Set<string>>();
  const allSymbols = new Set<string>();
  for (const item of weeks) {
    if (!isObject(item) || !isCalendarDate(item.week) || !Array.isArray(item.tickers)) {
      throw new Error(`${timeframe} periods invalid`);
    }
    const period = item.week;
    const symbols: string[] = [];
    for (const ticker of item.tickers) {
      if (!isObject(ticker) || typeof ticker.symbol !== "string" || !ticker.symbol) {
        throw new Error(`${timeframe} tickers invalid`);
      }
      symbols.push(ticker.symbol);
    }
    if (
      new Set(symbols).size !== symbols.length ||
      symbols.some((symbol, index) => symbol !== [...symbols].sort()[index])
    ) {
      throw new Error(`${timeframe} tickers invalid`);
    }
    periods.push(period);
    primary.set(period, new Set(symbols));
    for (const symbol of symbols) allSymbols.add(symbol);
  }
  const sortedPeriods = [...periods].sort();
  if (
    new Set(periods).size !== periods.length ||
    periods.some((period, index) => period !== sortedPeriods[index]) ||
    periods.at(-1) !== expectedDate
  ) {
    throw new Error(`${timeframe} periods invalid`);
  }
  if (!isObject(value.instruments)) throw new Error(`${timeframe} instruments invalid`);
  const instrumentSymbols = Object.keys(value.instruments).sort();
  const expectedSymbols = [...allSymbols].sort();
  if (
    instrumentSymbols.length !== expectedSymbols.length ||
    instrumentSymbols.some((symbol, index) => symbol !== expectedSymbols[index])
  ) {
    throw new Error(`${timeframe} instruments mismatch`);
  }
  for (const symbol of instrumentSymbols) {
    const profile = value.instruments[symbol];
    if (
      !isObject(profile) ||
      typeof profile.name !== "string" ||
      typeof profile.exchange !== "string"
    ) {
      throw new Error(`${timeframe} instruments invalid`);
    }
  }
  if (!isObject(value.filter)) throw new Error(`${timeframe} filter invalid`);
  requireTrendBounceMembershipMap(
    value.filter.weeks,
    periods,
    primary,
    `${timeframe} filter`,
  );
  if (timeframe === "daily") {
    if (!isObject(value.signals)) throw new Error("daily signals invalid");
    for (const signal of ["pb", "mq"] as const) {
      const payload = value.signals[signal];
      if (!isObject(payload)) throw new Error(`daily ${signal} invalid`);
      requireTrendBounceMembershipMap(
        payload.weeks,
        periods,
        primary,
        `daily ${signal}`,
      );
    }
  }
  return value;
}

function requireUSRotation(
  value: unknown,
  expectedWeeklyDate: string,
): JsonObject {
  if (
    !isObject(value) ||
    value.schema_version !== US_ROTATION_SCHEMA_VERSION ||
    value.market !== "US" ||
    value.method_version !== US_ROTATION_METHOD_VERSION ||
    value.data_cutoff !== expectedWeeklyDate ||
    value.window !== 13
  ) {
    throw new Error("US rotation identity mismatch");
  }
  if (
    !Array.isArray(value.levels) ||
    canonical(value.levels) !== canonical([["sector", "Sector"]]) ||
    !Array.isArray(value.weeks) ||
    value.weeks.length < 1 ||
    value.weeks.length > 160
  ) {
    throw new Error("US rotation periods invalid");
  }
  const weeks = value.weeks.filter((period): period is string => typeof period === "string");
  const sortedWeeks = [...weeks].sort();
  if (
    weeks.length !== value.weeks.length ||
    weeks.some((period) => !isCalendarDate(period) || new Date(`${period}T00:00:00Z`).getUTCDay() !== 1) ||
    new Set(weeks).size !== weeks.length ||
    weeks.some((period, index) => period !== sortedWeeks[index]) ||
    weeks.at(-1) !== expectedWeeklyDate
  ) {
    throw new Error("US rotation periods invalid");
  }
  if (!isObject(value.counts) || !isObject(value.counts.sector)) {
    throw new Error("US rotation counts invalid");
  }
  const countGroups = Object.keys(value.counts.sector).sort();
  const expectedGroups = [...US_ROTATION_GROUPS].sort();
  if (
    countGroups.length !== expectedGroups.length ||
    countGroups.some((group, index) => group !== expectedGroups[index])
  ) {
    throw new Error("US rotation groups invalid");
  }
  const mappedByPeriod = new Array(weeks.length).fill(0);
  for (const group of US_ROTATION_GROUPS) {
    const values = value.counts.sector[group];
    if (
      !Array.isArray(values) ||
      values.length !== weeks.length ||
      values.some((count) => !Number.isSafeInteger(count) || count < 0)
    ) {
      throw new Error("US rotation counts invalid");
    }
    values.forEach((count, index) => mappedByPeriod[index] += count as number);
  }
  if (
    !Array.isArray(value.totals) ||
    value.totals.length !== weeks.length ||
    value.totals.some((count) => !Number.isSafeInteger(count) || count < 0) ||
    mappedByPeriod.some((count, index) => count > (value.totals as number[])[index])
  ) {
    throw new Error("US rotation totals invalid");
  }
  if (!isObject(value.coverage)) throw new Error("US rotation coverage invalid");
  const mapped = mappedByPeriod.reduce((total, count) => total + count, 0);
  const total = (value.totals as number[]).reduce((sum, count) => sum + count, 0);
  if (
    value.coverage.mapped !== mapped ||
    value.coverage.total !== total ||
    value.coverage.latest_mapped !== mappedByPeriod.at(-1) ||
    value.coverage.latest_total !== value.totals.at(-1)
  ) {
    throw new Error("US rotation coverage invalid");
  }
  if (!isObject(value.status) || !isObject(value.status.sector)) {
    throw new Error("US rotation status invalid");
  }
  const sectorStatus = value.status.sector;
  const statusGroups = Object.keys(sectorStatus).sort();
  if (
    statusGroups.length !== expectedGroups.length ||
    statusGroups.some((group, index) => group !== expectedGroups[index]) ||
    statusGroups.some((group) => ![-1, 0, 1].includes(sectorStatus[group] as number))
  ) {
    throw new Error("US rotation status invalid");
  }
  if (!isObject(value.of)) throw new Error("US rotation symbol map invalid");
  for (const groups of Object.values(value.of)) {
    if (
      !Array.isArray(groups) ||
      groups.length !== 1 ||
      !US_ROTATION_GROUPS.includes(groups[0] as typeof US_ROTATION_GROUPS[number])
    ) {
      throw new Error("US rotation symbol map invalid");
    }
  }
  return value;
}

function requirePageRotation(
  page: JsonObject,
  rotation: JsonObject,
): void {
  const value = page.rotation;
  if (
    !isObject(value) ||
    value.schema_version !== US_ROTATION_SCHEMA_VERSION ||
    value.window !== 13 ||
    value.updated_at !== rotation.data_cutoff ||
    canonical(value.levels) !== canonical(["sector"]) ||
    canonical(value.status) !== canonical(rotation.status) ||
    !isObject(value.of)
  ) {
    throw new Error("US page rotation invalid");
  }
  const instruments = page.instruments as JsonObject;
  const rootMap = rotation.of as JsonObject;
  const expectedMap = Object.fromEntries(
    Object.keys(instruments)
      .filter((symbol) => symbol in rootMap)
      .sort()
      .map((symbol) => [symbol, rootMap[symbol]]),
  );
  if (canonical(value.of) !== canonical(expectedMap)) {
    throw new Error("US page rotation symbol map invalid");
  }
}

function trendBounceSemantic(snapshot: JsonObject): JsonObject {
  return {
    schema_version: snapshot.schema_version,
    algorithm_version: snapshot.algorithm_version,
    market: snapshot.market,
    data_session: snapshot.data_session,
    weekly_session: snapshot.weekly_session,
    pages: snapshot.pages,
    rotation: snapshot.rotation,
  };
}

export async function trendBounceSemanticDigest(
  snapshot: JsonObject,
): Promise<string> {
  return sha256(canonical(trendBounceSemantic(snapshot)));
}

export async function validateTrendBounceSnapshot(value: unknown): Promise<JsonObject> {
  if (!isObject(value)) throw new Error("snapshot must be an object");
  if (
    value.schema_version !== TREND_BOUNCE_SCHEMA_VERSION ||
    value.algorithm_version !== TREND_BOUNCE_ALGORITHM_VERSION ||
    value.market !== "US" ||
    !isCalendarDate(value.data_session) ||
    !isCalendarDate(value.weekly_session) ||
    !isObject(value.pages)
  ) {
    throw new Error("snapshot identity mismatch");
  }
  const daily = requireTrendBouncePage(value.pages.daily, "daily", value.data_session);
  const weekly = requireTrendBouncePage(value.pages.weekly, "weekly", value.weekly_session);
  const rotation = requireUSRotation(value.rotation, value.weekly_session);
  requirePageRotation(daily, rotation);
  requirePageRotation(weekly, rotation);
  if (
    typeof value.snapshot_sha256 !== "string" ||
    !/^[a-f0-9]{64}$/.test(value.snapshot_sha256) ||
    (await trendBounceSemanticDigest(value)) !== value.snapshot_sha256
  ) {
    throw new Error("snapshot semantic digest mismatch");
  }
  return value;
}

async function receiveTrendBounceSnapshot(request: Request, env: Env): Promise<Response> {
  if (!env.INGEST_TOKEN || !authorized(request, env.INGEST_TOKEN)) {
    return json({ status: "rejected" }, 401);
  }
  if (!(request.headers.get("content-type") ?? "").startsWith("application/json")) {
    return json({ status: "rejected", error: "content-type" }, 415);
  }
  const rawLength = request.headers.get("content-length");
  const contentLength = rawLength === null ? NaN : Number(rawLength);
  if (
    !Number.isSafeInteger(contentLength) ||
    contentLength < 1 ||
    contentLength > MAX_TREND_BOUNCE_BYTES
  ) {
    return json({ status: "rejected", error: "size" }, 413);
  }
  const claimedDigest = request.headers.get("x-content-sha256") ?? "";
  if (!/^[a-f0-9]{64}$/.test(claimedDigest)) {
    return json({ status: "rejected", error: "digest" }, 400);
  }
  const raw = await request.arrayBuffer();
  if (raw.byteLength !== contentLength || (await sha256(raw)) !== claimedDigest) {
    return json({ status: "rejected", error: "digest" }, 400);
  }
  let snapshot: JsonObject;
  try {
    snapshot = await validateTrendBounceSnapshot(
      JSON.parse(new TextDecoder().decode(raw)),
    );
  } catch (error) {
    return json(
      { status: "rejected", error: error instanceof Error ? error.message : "invalid" },
      400,
    );
  }

  const dataSession = snapshot.data_session as string;
  const weeklySession = snapshot.weekly_session as string;

  const current = await env.BUNDLES.getWithMetadata<unknown, TrendBounceWriteMetadata>(
    TREND_BOUNCE_KEY,
    { type: "json" },
  );
  const rotationBootstrap =
    isObject(current.value) && !isObject(current.value.rotation);
  if (isObject(current.value)) {
    if (current.value.snapshot_sha256 === snapshot.snapshot_sha256) {
      return json({ status: "unchanged", write_performed: false }, 200);
    }
    if (
      typeof current.value.data_session !== "string" ||
      typeof current.value.weekly_session !== "string"
    ) {
      return json({ status: "error", error: "stored snapshot invalid" }, 500);
    }
    if (
      dataSession < current.value.data_session ||
      weeklySession < current.value.weekly_session
    ) {
      return json({ status: "conflict", error: "session regressed" }, 409);
    }
  }

  const now = new Date();
  const day = istDay(now);
  const previousCount =
    current.metadata?.write_day_ist === day ? Number(current.metadata.write_count) : 0;
  if (!Number.isSafeInteger(previousCount) || previousCount < 0) {
    return json({ status: "error", error: "stored write budget invalid" }, 500);
  }
  if (
    previousCount >= MAX_TREND_BOUNCE_WRITES_PER_IST_DAY &&
    !rotationBootstrap
  ) {
    return json({ status: "budget_exhausted", write_performed: false }, 429);
  }
  const sameSession =
    isObject(current.value) && current.value.data_session === dataSession;
  const previousRevision = Number(current.metadata?.session_revision ?? 0);
  if (!Number.isSafeInteger(previousRevision) || previousRevision < 0) {
    return json({ status: "error", error: "stored revision invalid" }, 500);
  }
  if (sameSession && previousRevision >= 1 && !rotationBootstrap) {
    return json({ status: "conflict", error: "session revision exhausted" }, 409);
  }
  const metadata: TrendBounceWriteMetadata = {
    bytes: raw.byteLength,
    received_at: now.toISOString(),
    sha256: claimedDigest,
    snapshot_sha256: snapshot.snapshot_sha256 as string,
    write_day_ist: day,
    write_count: rotationBootstrap ? previousCount : previousCount + 1,
    data_session: dataSession,
    weekly_session: weeklySession,
    session_revision: rotationBootstrap
      ? previousRevision
      : sameSession
        ? previousRevision + 1
        : 0,
  };
  await env.BUNDLES.put(TREND_BOUNCE_KEY, raw, { metadata });
  console.log(
    JSON.stringify({
      event: "us-trend-bounce-snapshot-accepted",
      bytes: raw.byteLength,
      data_session: metadata.data_session,
      weekly_session: metadata.weekly_session,
      write_count: metadata.write_count,
    }),
  );
  return json(
    { status: "accepted", write_performed: true, write_count: metadata.write_count },
    202,
  );
}

function marketEventsSemantic(snapshot: JsonObject): JsonObject {
  const semantic: JsonObject = {
    schema_version: snapshot.schema_version,
    algorithm_version: snapshot.algorithm_version,
    market: snapshot.market,
    event_type: snapshot.event_type,
    history_scope: snapshot.history_scope,
    detail_limit: snapshot.detail_limit,
    event_columns: snapshot.event_columns,
    records: snapshot.records,
  };
  if ("related_event_sets" in snapshot) {
    semantic.related_event_sets = snapshot.related_event_sets;
  }
  return semantic;
}

export async function marketEventsSemanticDigest(
  snapshot: JsonObject,
): Promise<string> {
  return sha256(canonical(marketEventsSemantic(snapshot)));
}

function nullableFiniteNonNegative(value: unknown): boolean {
  return value === null || (
    typeof value === "number" && Number.isFinite(value) && value >= 0
  );
}

function validateMarketEventRow(
  value: unknown,
  firstDate: string,
  lastDate: string,
): void {
  if (!Array.isArray(value) || value.length !== MARKET_EVENT_COLUMNS.length) {
    throw new Error("event row shape mismatch");
  }
  if (
    !isCalendarDate(value[0]) ||
    value[0] < firstDate ||
    value[0] > lastDate ||
    (value[1] !== null && (
      typeof value[1] !== "string" || !Number.isFinite(Date.parse(value[1]))
    )) ||
    typeof value[2] !== "string" ||
    value[2].length < 1 ||
    !["BUY", "SELL", null].includes(value[3] as string | null) ||
    !nullableFiniteNonNegative(value[4]) ||
    !nullableFiniteNonNegative(value[5]) ||
    !nullableFiniteNonNegative(value[6]) ||
    typeof value[7] !== "string" ||
    value[7].length < 1 ||
    (value[8] !== null && typeof value[8] !== "string") ||
    typeof value[9] !== "string"
  ) {
    throw new Error("event row value invalid");
  }
}

function validateMarketEventSet(
  value: JsonObject,
  market: (typeof MARKETS)[number],
  expectedEventType: string,
  generatedDate: string,
  indiaWindowStart: string,
  expectedDetailLimit?: number,
): void {
  if (
    value.event_type !== expectedEventType ||
    value.history_scope !== (market === "IN" ? "rolling_1_year" : "complete") ||
    !Number.isSafeInteger(value.detail_limit) ||
    Number(value.detail_limit) < 1 ||
    Number(value.detail_limit) > 50 ||
    (expectedDetailLimit !== undefined &&
      Number(value.detail_limit) !== expectedDetailLimit) ||
    !isObject(value.records) ||
    typeof value.source !== "string"
  ) {
    throw new Error("event set identity mismatch");
  }
  requireExactStringArray(
    value.event_columns,
    MARKET_EVENT_COLUMNS,
    "event columns mismatch",
  );
  const symbols = Object.keys(value.records).sort();
  const symbolPattern = market === "IN"
    ? /^[A-Z0-9][A-Z0-9.&-]{0,80}$/
    : /^[A-Z0-9][A-Z0-9.-]{0,80}$/;
  if (symbols.length < 1 || symbols.some((symbol) => !symbolPattern.test(symbol))) {
    throw new Error("record symbol invalid");
  }
  let rowCount = 0;
  let detailRowCount = 0;
  let sourceCutoff = "";
  for (const symbol of symbols) {
    const record = value.records[symbol];
    if (
      !isObject(record) ||
      !Number.isSafeInteger(record.count) ||
      Number(record.count) < 1 ||
      !isCalendarDate(record.first_date) ||
      !isCalendarDate(record.last_date) ||
      record.first_date > record.last_date ||
      (market === "IN" && record.first_date < indiaWindowStart) ||
      (market === "IN" && record.last_date > generatedDate) ||
      !Array.isArray(record.events) ||
      record.events.length < 1 ||
      record.events.length > Number(value.detail_limit) ||
      record.events.length > Number(record.count)
    ) {
      throw new Error("event record invalid");
    }
    let previousKey: string | null = null;
    for (const event of record.events) {
      validateMarketEventRow(event, record.first_date, record.last_date);
      const key = `${event[0]}|${event[1] ?? ""}|${event[8] ?? ""}`;
      if (
        previousKey !== null &&
        ((market === "IN" && key > previousKey) ||
          (market === "US" && key < previousKey))
      ) {
        throw new Error("event rows must be ordered");
      }
      previousKey = key;
    }
    const latestEvent = (
      market === "IN" ? record.events.at(0) : record.events.at(-1)
    ) as unknown[];
    if (latestEvent[0] !== record.last_date) {
      throw new Error("event record last date mismatch");
    }
    rowCount += Number(record.count);
    detailRowCount += record.events.length;
    if (record.last_date > sourceCutoff) sourceCutoff = record.last_date;
  }
  if (
    value.symbol_count !== symbols.length ||
    value.row_count !== rowCount ||
    value.detail_row_count !== detailRowCount ||
    value.source_cutoff !== sourceCutoff
  ) {
    throw new Error("snapshot counts mismatch");
  }
}

export async function validateMarketEventsSnapshot(value: unknown): Promise<JsonObject> {
  if (!isObject(value)) throw new Error("snapshot must be an object");
  if (
    value.schema_version !== MARKET_EVENTS_SCHEMA_VERSION ||
    value.algorithm_version !== MARKET_EVENTS_ALGORITHM_VERSION ||
    !MARKETS.includes(value.market as (typeof MARKETS)[number]) ||
    typeof value.producer_commit !== "string" ||
    value.producer_commit.length < 7 ||
    typeof value.generated_at_utc !== "string" ||
    !Number.isFinite(Date.parse(value.generated_at_utc))
  ) {
    throw new Error("snapshot identity mismatch");
  }
  const market = value.market as (typeof MARKETS)[number];
  const generated = new Date(value.generated_at_utc as string);
  const previousYear = generated.getUTCFullYear() - 1;
  const month = generated.getUTCMonth();
  const day = Math.min(
    generated.getUTCDate(),
    new Date(Date.UTC(previousYear, month + 1, 0)).getUTCDate(),
  );
  const indiaWindowStart = new Date(Date.UTC(previousYear, month, day))
    .toISOString()
    .slice(0, 10);
  const generatedDate = generated.toISOString().slice(0, 10);
  const primaryEventType = market === "IN" ? "bulk_deal" : "political_trade_report";
  validateMarketEventSet(
    value,
    market,
    primaryEventType,
    generatedDate,
    indiaWindowStart,
  );
  if (market === "IN") {
    if (
      !isObject(value.related_event_sets) ||
      Object.keys(value.related_event_sets).sort().join(",") !== "insider_trade" ||
      !isObject(value.related_event_sets.insider_trade)
    ) {
      throw new Error("India insider event set missing");
    }
    validateMarketEventSet(
      value.related_event_sets.insider_trade,
      market,
      "insider_trade",
      generatedDate,
      indiaWindowStart,
      Number(value.detail_limit),
    );
  } else if ("related_event_sets" in value) {
    throw new Error("US related event sets are unsupported");
  }
  if (
    typeof value.snapshot_sha256 !== "string" ||
    !/^[a-f0-9]{64}$/.test(value.snapshot_sha256) ||
    (await marketEventsSemanticDigest(value)) !== value.snapshot_sha256
  ) {
    throw new Error("snapshot semantic digest mismatch");
  }
  return value;
}

function validateStoredMarketEventsHeader(
  value: unknown,
  market: (typeof MARKETS)[number],
): JsonObject {
  if (
    !isObject(value) ||
    value.schema_version !== MARKET_EVENTS_SCHEMA_VERSION ||
    value.algorithm_version !== MARKET_EVENTS_ALGORITHM_VERSION ||
    value.market !== market ||
    !isCalendarDate(value.source_cutoff) ||
    !Number.isSafeInteger(value.row_count) ||
    Number(value.row_count) < 1 ||
    typeof value.generated_at_utc !== "string" ||
    !Number.isFinite(Date.parse(value.generated_at_utc)) ||
    typeof value.snapshot_sha256 !== "string" ||
    !/^[a-f0-9]{64}$/.test(value.snapshot_sha256)
  ) {
    throw new Error("stored market-events snapshot invalid");
  }
  return value;
}

async function receiveMarketEventsSnapshot(
  request: Request,
  env: Env,
): Promise<Response> {
  if (!env.INGEST_TOKEN || !authorized(request, env.INGEST_TOKEN)) {
    return json({ status: "rejected" }, 401);
  }
  if (!(request.headers.get("content-type") ?? "").startsWith("application/json")) {
    return json({ status: "rejected", error: "content-type" }, 415);
  }
  const rawLength = request.headers.get("content-length");
  const contentLength = rawLength === null ? NaN : Number(rawLength);
  if (
    !Number.isSafeInteger(contentLength) ||
    contentLength < 1 ||
    contentLength > MAX_MARKET_EVENTS_BYTES
  ) {
    return json({ status: "rejected", error: "size" }, 413);
  }
  const claimedDigest = request.headers.get("x-content-sha256") ?? "";
  if (!/^[a-f0-9]{64}$/.test(claimedDigest)) {
    return json({ status: "rejected", error: "digest" }, 400);
  }
  const raw = await request.arrayBuffer();
  if (raw.byteLength !== contentLength || (await sha256(raw)) !== claimedDigest) {
    return json({ status: "rejected", error: "digest" }, 400);
  }
  let snapshot: JsonObject;
  try {
    snapshot = await validateMarketEventsSnapshot(
      JSON.parse(new TextDecoder().decode(raw)),
    );
  } catch (error) {
    return json(
      { status: "rejected", error: error instanceof Error ? error.message : "invalid" },
      400,
    );
  }

  const market = snapshot.market as (typeof MARKETS)[number];
  const key = `${MARKET_EVENTS_KEY_PREFIX}${market}`;
  const current = await env.BUNDLES.getWithMetadata<unknown, MarketEventsWriteMetadata>(
    key,
    { type: "json" },
  );
  let indiaScopeMigration = false;
  if (current.value !== null) {
    let previous: JsonObject;
    try {
      previous = validateStoredMarketEventsHeader(current.value, market);
    } catch {
      return json({ status: "error", error: "stored snapshot invalid" }, 500);
    }
    indiaScopeMigration =
      market === "IN" &&
      previous.history_scope === "complete" &&
      snapshot.history_scope === "rolling_1_year";
    if (previous.snapshot_sha256 === snapshot.snapshot_sha256) {
      return json({ status: "unchanged", write_performed: false }, 200);
    }
    if (
      (snapshot.history_scope === "complete" &&
        Number(snapshot.row_count) < Number(previous.row_count)) ||
      String(snapshot.source_cutoff) < String(previous.source_cutoff)
    ) {
      return json({ status: "conflict", error: "history regressed" }, 409);
    }
    if (
      Date.parse(snapshot.generated_at_utc as string) <=
      Date.parse(previous.generated_at_utc as string)
    ) {
      return json({ status: "conflict", error: "generation did not advance" }, 409);
    }
  }

  const now = new Date();
  const day = istDay(now);
  const previousCount =
    current.metadata?.write_day_ist === day ? Number(current.metadata.write_count) : 0;
  if (!Number.isSafeInteger(previousCount) || previousCount < 0) {
    return json({ status: "error", error: "stored write budget invalid" }, 500);
  }
  if (
    previousCount >= MAX_MARKET_EVENT_WRITES_PER_IST_DAY &&
    !indiaScopeMigration
  ) {
    return json({ status: "budget_exhausted", write_performed: false }, 429);
  }
  const metadata: MarketEventsWriteMetadata = {
    bytes: raw.byteLength,
    received_at: now.toISOString(),
    sha256: claimedDigest,
    snapshot_sha256: snapshot.snapshot_sha256 as string,
    write_day_ist: day,
    write_count: previousCount + 1,
    market,
    source_cutoff: snapshot.source_cutoff as string,
    row_count: snapshot.row_count as number,
  };
  await env.BUNDLES.put(key, raw, { metadata });
  console.log(
    JSON.stringify({
      event: "market-events-snapshot-accepted",
      market,
      bytes: raw.byteLength,
      row_count: metadata.row_count,
      source_cutoff: metadata.source_cutoff,
      write_count: metadata.write_count,
    }),
  );
  return json(
    { status: "accepted", write_performed: true, write_count: metadata.write_count },
    202,
  );
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return json({ ready: true });
    }
    if (request.method === "POST" && url.pathname === "/v1/tsha-hbcs") {
      return receiveSnapshot(request, env);
    }
    if (request.method === "POST" && url.pathname === "/v1/us-trend-bounce") {
      return receiveTrendBounceSnapshot(request, env);
    }
    if (request.method === "POST" && url.pathname === "/v1/market-events") {
      return receiveMarketEventsSnapshot(request, env);
    }
    return json({ error: "not-found" }, 404);
  },
} satisfies ExportedHandler<Env>;
