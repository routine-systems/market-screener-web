const API_SCHEMA_VERSION = 'shortlist-history.api.v1';
function json(value, status=200) {
  return new Response(JSON.stringify(value), {status, headers: {'content-type':'application/json; charset=utf-8','cache-control':'private, max-age=300'}});
}
export async function onRequestGet({env,request}) {
  const market = new URL(request.url).searchParams.get('market');
  if (!['IN','US'].includes(market)) return json({error:'Choose market IN or US'},400);
  if (!env.SCANLINKS) return json({error:'SCANLINKS KV not bound'},500);
  try {
    const snapshot = await env.SCANLINKS.get(`shortlist-history:v1:${market}`, {type:'json'});
    if (!snapshot) return json({error:'Shortlist history unavailable'},503);
    if (snapshot.schema_version!=='shortlist-history.snapshot.v1'||snapshot.market!==market||!snapshot.timeframes) return json({error:'Invalid Shortlist history'},502);
    return json({schema_version:API_SCHEMA_VERSION,snapshot});
  } catch {
    return json({error:'Shortlist history unavailable'},503);
  }
}
