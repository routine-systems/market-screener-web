const SNAPSHOT_KEY = "tsha-hbcs:v1:latest";
const SNAPSHOT_VERSION = "tsha-hbcs.snapshot.v1";
const HISTORY_VERSION = "ht-history.v1";
const INSTRUMENT_COLUMNS = ["symbol", "exchange", "asset_type", "sector"];
const HISTORY_ROW_COLUMNS = [
  "instrument_index",
  "hbcs_bull_component_count",
  "hbcs_components",
  "fast_body_pct",
  "slow_body_pct",
  "close",
  "median_dollar_turnover_20",
];

function json(body, status = 200) {
  return Response.json(body, {
    status,
    headers: {
      "cache-control": status === 200 ? "private, max-age=300" : "no-store",
      "content-type": "application/json; charset=utf-8",
    },
  });
}

function sameColumns(value, expected) {
  return (
    Array.isArray(value) &&
    value.length === expected.length &&
    value.every((column, index) => column === expected[index])
  );
}

function validIsoDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function validHistory(value, signalDate) {
  if (
    !value ||
    typeof value !== "object" ||
    value.schema_version !== HISTORY_VERSION ||
    !sameColumns(value.instrument_columns, INSTRUMENT_COLUMNS) ||
    !sameColumns(value.row_columns, HISTORY_ROW_COLUMNS) ||
    !Array.isArray(value.instruments) ||
    !Array.isArray(value.periods) ||
    value.periods.length === 0 ||
    value.periods.length > 13
  ) {
    return false;
  }
  let previousDate = "";
  for (const period of value.periods) {
    if (
      !period ||
      typeof period !== "object" ||
      !validIsoDate(period.date) ||
      period.date <= previousDate ||
      !["stored", "replay"].includes(period.source) ||
      !Array.isArray(period.rows)
    ) {
      return false;
    }
    previousDate = period.date;
  }
  return value.periods[value.periods.length - 1].date === signalDate;
}

function validBucket(value) {
  return Boolean(
    value &&
      typeof value === "object" &&
      /^\d{4}-\d{2}-\d{2}$/.test(value.signal_date) &&
      Number.isSafeInteger(value.shortlist_size) &&
      value.shortlist_size >= 0 &&
      Array.isArray(value.rows) &&
      value.rows.length === value.shortlist_size &&
      (value.history === undefined || validHistory(value.history, value.signal_date)),
  );
}

function validSnapshot(value) {
  if (
    !value ||
    typeof value !== "object" ||
    value.schema_version !== SNAPSHOT_VERSION ||
    typeof value.snapshot_sha256 !== "string" ||
    !/^[a-f0-9]{64}$/.test(value.snapshot_sha256) ||
    !Array.isArray(value.columns) ||
    value.columns.length === 0 ||
    !value.markets ||
    typeof value.markets !== "object"
  ) {
    return false;
  }
  for (const market of ["IN", "US"]) {
    const payload = value.markets[market];
    if (
      !payload ||
      typeof payload !== "object" ||
      !/^\d{4}-\d{2}-\d{2}$/.test(payload.data_session) ||
      !payload.timeframes ||
      !validBucket(payload.timeframes.daily) ||
      !validBucket(payload.timeframes.weekly)
    ) {
      return false;
    }
  }
  return true;
}

export async function onRequestGet({ env }) {
  if (!env.SCANLINKS) {
    return json({ schema_version: "tsha-hbcs.api.v1", error: "snapshot store unavailable" }, 500);
  }
  try {
    const stored = await env.SCANLINKS.getWithMetadata(SNAPSHOT_KEY, {
      type: "json",
      cacheTtl: 300,
    });
    if (stored.value === null) {
      return json({ schema_version: "tsha-hbcs.api.v1", error: "snapshot unavailable" }, 503);
    }
    if (!validSnapshot(stored.value)) {
      return json({ schema_version: "tsha-hbcs.api.v1", error: "snapshot invalid" }, 500);
    }
    return json({
      schema_version: "tsha-hbcs.api.v1",
      snapshot: stored.value,
      publication: stored.metadata ?? {},
    });
  } catch {
    return json({ schema_version: "tsha-hbcs.api.v1", error: "snapshot read failed" }, 500);
  }
}
