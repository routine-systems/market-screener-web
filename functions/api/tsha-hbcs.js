const SNAPSHOT_KEY = "tsha-hbcs:v1:latest";
const SNAPSHOT_VERSION = "tsha-hbcs.snapshot.v1";

function json(body, status = 200) {
  return Response.json(body, {
    status,
    headers: {
      "cache-control": status === 200 ? "private, max-age=300" : "no-store",
      "content-type": "application/json; charset=utf-8",
    },
  });
}

function validBucket(value) {
  return Boolean(
    value &&
      typeof value === "object" &&
      /^\d{4}-\d{2}-\d{2}$/.test(value.signal_date) &&
      Number.isSafeInteger(value.shortlist_size) &&
      value.shortlist_size >= 0 &&
      Array.isArray(value.rows) &&
      value.rows.length === value.shortlist_size,
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
