const V='sched-v2';
self.addEventListener('install',e=>{e.waitUntil(caches.open(V).then(c=>c.addAll(['/','/manifest.json','/icon.svg'])).then(()=>self.skipWaiting()).catch(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==V).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
  const r=e.request;
  if(r.method!=='GET')return;
  const u=new URL(r.url);
  if(u.origin!==location.origin)return;
  e.respondWith(fetch(r).then(resp=>{
    if(resp&&resp.ok){const cp=resp.clone();caches.open(V).then(c=>c.put(r,cp)).catch(()=>{});}
    return resp;
  }).catch(()=>caches.match(r).then(m=>m||(r.mode==='navigate'?caches.match('/'):null)).then(m=>m||Response.error())));
});
