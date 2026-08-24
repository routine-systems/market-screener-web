const SNAPSHOT_KEY = "forward-test:v1:latest";
const SNAPSHOT_VERSION = "forward-test.snapshot.v1";

function json(body, status = 200) {
  return Response.json(body, {
    status,
    headers: {
      "cache-control": status === 200 ? "private, max-age=300" : "no-store",
      "content-type": "application/json; charset=utf-8",
    },
  });
}

function validIsoDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function validSnapshot(value) {
  return Boolean(
    value &&
      typeof value === "object" &&
      value.schema_version === SNAPSHOT_VERSION &&
      validIsoDate(value.data_cutoff) &&
      typeof value.generated_at_utc === "string" &&
      Number.isFinite(new Date(value.generated_at_utc).valueOf()) &&
      typeof value.snapshot_sha256 === "string" &&
      /^[a-f0-9]{64}$/.test(value.snapshot_sha256) &&
      Number.isSafeInteger(value.row_count) &&
      value.row_count > 0 &&
      value.payload &&
      typeof value.payload === "object" &&
      value.payload.summary &&
      typeof value.payload.summary === "object" &&
      Array.isArray(value.payload.rows) &&
      value.payload.rows.length === value.row_count
  );
}

export async function onRequestGet({ env, request }) {
  if (!env.SCANLINKS) {
    return json({ schema_version: "forward-test.api.v1", error: "snapshot store unavailable" }, 500);
  }
  try {
    const stored = await env.SCANLINKS.getWithMetadata(SNAPSHOT_KEY, {
      type: "json",
      cacheTtl: 300,
    });
    if (stored.value === null) {
      return json({ schema_version: "forward-test.api.v1", error: "snapshot unavailable" }, 503);
    }
    if (!validSnapshot(stored.value)) {
      return json({ schema_version: "forward-test.api.v1", error: "snapshot invalid" }, 500);
    }
    const metaOnly = request?.url
      ? new URL(request.url).searchParams.get("meta") === "1"
      : false;
    if (metaOnly) {
      return json({
        schema_version: "forward-test.api.v1",
        snapshot: {
          generated_at_utc: stored.value.generated_at_utc,
          data_cutoff: stored.value.data_cutoff,
        },
        publication: stored.metadata ?? {},
      });
    }
    return json({
      schema_version: "forward-test.api.v1",
      snapshot: stored.value,
      publication: stored.metadata ?? {},
    });
  } catch {
    return json({ schema_version: "forward-test.api.v1", error: "snapshot read failed" }, 500);
  }
}

