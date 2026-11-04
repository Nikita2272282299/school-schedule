/* Scope-safe PWA for GitHub project Pages. */
importScripts('./config.js');
const BASE=new URL('./',self.location.href);
const API=((self.SCHEDULE_CONFIG&&self.SCHEDULE_CONFIG.apiBase)||self.location.origin).replace(/\/$/,'');
const PREFIX='schedule8g-'+BASE.pathname+'-';
const V=PREFIX+'v24';
const asset=p=>new URL(p,BASE).href;
const STATIC=['./','index.html','config.js','manifest.json','icon.svg','icon-192.png','icon-512.png','apple-touch-icon.png'].map(asset);
self.addEventListener('install',e=>e.waitUntil(caches.open(V).then(c=>c.addAll(STATIC)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k.startsWith(PREFIX)&&k!==V).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('push',e=>{
 let d={};try{d=e.data?e.data.json():{}}catch(_){d={body:e.data.text()}}
 const target=new URL('./',BASE);
 try{target.search=new URL(d.url||'./',BASE).search}catch(_){}
 e.waitUntil(self.registration.showNotification(d.title||'Расписание 8Г',{
  body:d.body||'Расписание обновилось',icon:asset('icon-192.png'),badge:asset('icon-192.png'),
  tag:d.tag||'schedule',renotify:true,lang:'ru',data:{url:target.href}
 }));
});
self.addEventListener('notificationclick',e=>{
 e.notification.close();
 const u=new URL((e.notification.data&&e.notification.data.url)||'./',BASE);
 if(u.origin!==BASE.origin||!u.pathname.startsWith(BASE.pathname))return;
 e.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(async ws=>{
  for(const w of ws)if(w.url===u.href&&'focus'in w)return w.focus();
  return clients.openWindow(u.href);
 }));
});
function b64u8(s){const b=atob(s.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-s.length%4)%4));return Uint8Array.from(b,c=>c.charCodeAt(0))}
self.addEventListener('pushsubscriptionchange',e=>e.waitUntil((async()=>{
 try{
  const r=await fetch(API+'/api/push/key');const j=await r.json();if(!j.supported||!j.key)return;
  const sub=await self.registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64u8(j.key)});
  await fetch(API+'/api/push/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({subscription:sub.toJSON()})});
 }catch(_){}
})()));
self.addEventListener('fetch',e=>{
 const r=e.request,u=new URL(r.url);
 if(r.method!=='GET'||u.origin!==BASE.origin||!u.pathname.startsWith(BASE.pathname)||u.pathname.includes('/api/'))return;
 e.respondWith(fetch(r).then(resp=>{
  if(resp.ok){const copy=resp.clone();caches.open(V).then(c=>c.put(r,copy)).catch(()=>{});}
  return resp;
 }).catch(async()=>{
  const hit=await caches.match(r,{ignoreSearch:true});
  return hit||(r.mode==='navigate'?await caches.match(asset('./')):null)||Response.error();
 }));
});
