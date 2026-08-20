const API_SCHEMA_VERSION = "market-events.api.v1";
const MARKETS = new Set(["IN", "US"]);

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "private, max-age=300",
    },
  });
}

export async function onRequestGet({ env, request }) {
  const market = new URL(request.url).searchParams.get("market")?.toUpperCase();
  if (!MARKETS.has(market)) {
    return json({ error: "market must be IN or US" }, 400);
  }
  if (!env.SCANLINKS) {
    return json({ error: "SCANLINKS KV not bound" }, 500);
  }
  try {
    const stored = await env.SCANLINKS.getWithMetadata(
      `market-events:v1:${market}`,
      { type: "json" },
    );
    if (stored.value === null) {
      return json({ error: `${market} market-event snapshot unavailable` }, 503);
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
