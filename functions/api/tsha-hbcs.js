const SNAPSHOT_KEY = "tsha-hbcs:v1:latest";
const API_SCHEMA_VERSION = "tsha-hbcs.api.v1";

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "private, max-age=300",
    },
  });
}

export async function onRequestGet({ env }) {
  if (!env.SCANLINKS) {
    return json({ error: "SCANLINKS KV not bound" }, 500);
  }
  try {
    const stored = await env.SCANLINKS.getWithMetadata(SNAPSHOT_KEY, {
      type: "json",
    });
    if (stored.value === null) {
      return json({ error: "HT snapshot unavailable" }, 503);
    }
    return json({
      schema_version: API_SCHEMA_VERSION,
      snapshot: stored.value,
      publication: stored.metadata || {},
    });
  } catch (error) {
    return json({ error: String(error) }, 500);
  }
}
