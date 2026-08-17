// Cloudflare Pages Function: POST /api/refresh → dispatch the public web repository's
// refresh workflow. That workflow checks out the signal producer, creates one immutable
// bundle, renders the site, and deploys the same build. The whole hostname is
// behind Cloudflare Access, so only the allow-listed users can reach this endpoint.
//
// Needs a project env secret GH_DISPATCH_TOKEN — a GitHub fine-grained PAT scoped to
// routine-systems/market-screener-web with Actions: Read and write. Set it with:
//   wrangler pages secret put GH_DISPATCH_TOKEN --project-name screener

const DEFAULT_REPO = "routine-systems/market-screener-web";
const DEFAULT_WORKFLOW = "refresh.yml";

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

export async function onRequestPost({ env }) {
  const token = env.GH_DISPATCH_TOKEN;
  if (!token) return json({ ok: false, error: "GH_DISPATCH_TOKEN not configured" }, 500);
  const repo = env.SIGNAL_REPO || DEFAULT_REPO;
  const workflow = env.SIGNAL_WORKFLOW || DEFAULT_WORKFLOW;
  const r = await fetch(
    `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        authorization: `Bearer ${token}`,
        accept: "application/vnd.github+json",
        "x-github-api-version": "2022-11-28",
        "user-agent": "screener-refresh-fn",
        "content-type": "application/json",
      },
      body: JSON.stringify({ ref: "main" }),
    },
  );
  if (r.status === 204) return json({ ok: true, queued: true });
  const detail = (await r.text()).slice(0, 300);
  return json({ ok: false, status: r.status, error: detail }, 502);
}

export async function onRequestGet() {
  return json({ ok: true, hint: "POST here to queue a new signal bundle" });
}
