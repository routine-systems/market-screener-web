const TRUSTED_HOST = "screener.chiragpatnaik.com";

export async function onRequest(context) {
  let hostname;
  try {
    hostname = new URL(context.request.url).hostname.toLowerCase();
  } catch {
    return new Response("Forbidden", {
      status: 403,
      headers: { "cache-control": "no-store" },
    });
  }

  if (hostname !== TRUSTED_HOST) {
    return new Response("Forbidden", {
      status: 403,
      headers: { "cache-control": "no-store" },
    });
  }

  return context.next();
}
