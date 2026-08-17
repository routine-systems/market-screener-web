// Cloudflare Pages Function: the fast scanlink-only refresh path.
//
//   GET  /api/scanlink  → the freshest weekly/daily scanlink hashes from KV. Pages fetch
//                         this on load and patch their in-scan ticker links, reviving any
//                         that expired since the last full scrape.
//   POST /api/scanlink  → dispatch the lightweight "scanlink" GitHub workflow, which
//                         re-extracts the scanlinks (no backtest download) and writes them
//                         back to this KV. ~1 min vs the ~10 min full refresh.
//
// Bindings/secrets: KV namespace SCANLINKS (wrangler.toml); GH_DISPATCH_TOKEN (a GitHub
// fine-grained PAT with Actions: read+write on the repo, set via wrangler pages secret).
// The whole hostname is behind Cloudflare Access, so only allow-listed users reach this.

const DEFAULT_REPO = "routine-systems/market-signals";
const WORKFLOW = "scanlink.yml";

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

export async function onRequestGet({ env }) {
  if (!env.SCANLINKS) return json({ ok: false, error: "SCANLINKS KV not bound" }, 500);
  try {
    const [weekly, daily, updated_at] = await Promise.all([
      env.SCANLINKS.get("weekly"),
      env.SCANLINKS.get("daily"),
      env.SCANLINKS.get("updated_at"),
    ]);
    return json({ ok: true, weekly, daily, updated_at });
  } catch (e) {
    return json({ ok: false, error: String(e) }, 500);
  }
}

export async function onRequestPost({ env }) {
  const token = env.GH_DISPATCH_TOKEN;
  if (!token) return json({ ok: false, error: "GH_DISPATCH_TOKEN not configured" }, 500);
  const repo = env.SIGNAL_REPO || DEFAULT_REPO;
  const r = await fetch(
    `https://api.github.com/repos/${repo}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        authorization: `Bearer ${token}`,
        accept: "application/vnd.github+json",
        "x-github-api-version": "2022-11-28",
        "user-agent": "screener-scanlink-fn",
        "content-type": "application/json",
      },
      body: JSON.stringify({ ref: "main" }),
    },
  );
  if (r.status === 204) return json({ ok: true, queued: true });
  const detail = (await r.text()).slice(0, 300);
  return json({ ok: false, status: r.status, error: detail }, 502);
}
