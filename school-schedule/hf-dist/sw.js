const CACHE='schedule-v308';
const FILES=['./','index.html','manifest.json','icon.svg','icon-192.png','icon-512.png','apple-touch-icon.png','offline-data.js','config.js','ai-schedule.json','sheet-data.json','assets/fonts/manrope-cyrillic-400-800-normal.woff2','assets/fonts/manrope-latin-400-800-normal.woff2'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>Promise.allSettled(FILES.map(f=>c.add(f)))).then(()=>self.skipWaiting()));});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE&&/^schedule|^sch[-_]/.test(k)).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
/* Работает даже при глушении/отключении мобильного интернета (БПЛА-атака):
   - статика (шрифты, иконки) отдаётся мгновенно из кэша;
   - страница и данные расписания ждут сеть не больше 1.5 сек, затем мгновенно
     отдают сохранённую копию из кэша, а при появлении сети обновляют кэш в фоне. */
const DYNAMIC=/\/index\.html$|\/(ai-schedule\.json|sheet-data\.json|offline-data\.js|config\.js)$/;
function cleanReq(req){const u=new URL(req.url);u.search='';return new Request(u.href,{method:'GET'});}
function netWithTimeout(req,ms){
  return new Promise((resolve,reject)=>{
    const c=typeof AbortController==='function'?new AbortController():null;
    const t=setTimeout(()=>{if(c)try{c.abort();}catch(e){}reject(new Error('timeout'));},ms);
    fetch(req,{cache:'no-store',signal:c?c.signal:undefined}).then(r=>{clearTimeout(t);resolve(r);},err=>{clearTimeout(t);reject(err);});
  });
}
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(e.request.method!=='GET'||u.origin!==self.location.origin||u.pathname.indexOf('/api/')!==-1)return;
  const isNav=e.request.mode==='navigate';
  const isDyn=isNav||DYNAMIC.test(u.pathname);
  const key=isNav?new Request(new URL('index.html',self.registration.scope).href):cleanReq(e.request);
  if(!isDyn){
    e.respondWith(caches.match(key,{ignoreSearch:true}).then(cached=>{
      const bg=fetch(e.request).then(r=>{if(r.ok){const cp=r.clone();caches.open(CACHE).then(c=>c.put(key,cp));}return r;}).catch(()=>null);
      if(cached){e.waitUntil(bg);return cached;}
      return bg.then(r=>r||Response.error());
    }));
    return;
  }
  e.respondWith(netWithTimeout(e.request,isNav?2000:3500).then(r=>{
    if(r&&r.ok){const cp=r.clone();e.waitUntil(caches.open(CACHE).then(c=>c.put(key,cp)));}
    return r;
  }).catch(()=>caches.match(key,{ignoreSearch:true}).then(r=>r||(isNav?caches.match('index.html'):Response.error()))));
});
self.addEventListener('push',e=>{let d={};try{d=e.data.json();}catch(x){d={body:e.data?e.data.text():''};}
 const home=new URL('./',self.registration.scope);let target=new URL(d.url||'./',home);if(target.origin!==home.origin||!target.pathname.startsWith(home.pathname))target=home;
 e.waitUntil(self.registration.showNotification(d.title||'Расписание',{body:d.body||'Расписание обновилось',icon:new URL('icon-192.png',home).href,badge:new URL('icon-192.png',home).href,tag:d.tag||'schedule',renotify:true,vibrate:[150,70,150],data:{url:target.href}}));
});
self.addEventListener('notificationclick',e=>{e.notification.close();const u=e.notification.data&&e.notification.data.url||self.registration.scope;e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(cs=>{for(const c of cs)if(c.url===u&&'focus' in c)return c.focus();return self.clients.openWindow(u);}));});
