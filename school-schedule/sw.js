const CACHE='schedule-v306';
const FILES=['./','index.html','manifest.json','icon-192.png','icon-512.png','offline-data.js','config.js','assets/fonts/manrope-cyrillic-400-800-normal.woff2','assets/fonts/manrope-latin-400-800-normal.woff2'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(FILES)).then(()=>self.skipWaiting()));});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE&&/^schedule|^sch[-_]/.test(k)).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
/* Свежесть важнее скорости: сначала сеть, кэш — только как запасной вариант.
   Сама страница и данные расписания никогда не должны «залипать» в кэше. */
const NEVER_CACHE=/\/index\.html$|\/(sheet-data\.json|offline-data\.js|config\.js)$/;
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET'||u.origin!==self.location.origin||u.pathname.indexOf('/api/')!==-1)return;
 const fresh=e.request.mode==='navigate'||NEVER_CACHE.test(u.pathname);
 e.respondWith(fetch(e.request,{cache:'no-store'}).then(r=>{if(r.ok&&!fresh){const copy=r.clone();e.waitUntil(caches.open(CACHE).then(c=>c.put(e.request,copy)));}return r;}).catch(()=>caches.match(e.request,{ignoreSearch:true}).then(r=>r||(e.request.mode==='navigate'?caches.match('index.html'):Response.error()))));
});
self.addEventListener('push',e=>{let d={};try{d=e.data.json();}catch(x){d={body:e.data?e.data.text():''};}
 const home=new URL('./',self.registration.scope);let target=new URL(d.url||'./',home);if(target.origin!==home.origin||!target.pathname.startsWith(home.pathname))target=home;
 e.waitUntil(self.registration.showNotification(d.title||'Расписание',{body:d.body||'Расписание обновилось',icon:new URL('icon-192.png',home).href,badge:new URL('icon-192.png',home).href,tag:d.tag||'schedule',data:{url:target.href}}));
});
self.addEventListener('notificationclick',e=>{e.notification.close();const u=e.notification.data&&e.notification.data.url||self.registration.scope;e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(cs=>{for(const c of cs)if(c.url===u&&'focus' in c)return c.focus();return self.clients.openWindow(u);}));});
