const SNAPSHOT_KEY = "ichimoku:v1:latest";
export async function onRequestGet({env}) {
  const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{"content-type":"application/json; charset=utf-8","cache-control":"private, max-age=300"}});
  if(!env.SCANLINKS)return json({error:"SCANLINKS KV not bound"},500);
  try {
    const snapshot=await env.SCANLINKS.get(SNAPSHOT_KEY,{type:"json"});
    if(!snapshot)return json({error:"Ichimoku snapshot unavailable"},503);
    if(snapshot.schema_version!=="ichimoku.snapshot.v1")return json({error:"Invalid Ichimoku snapshot"},503);
    return json({schema_version:"ichimoku.api.v1",snapshot});
  } catch {return json({error:"Ichimoku snapshot could not be read"},500)}
}
