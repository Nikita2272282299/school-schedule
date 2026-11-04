/* Scope-safe PWA: офлайн-first. Статика и последний ответ API доступны без сети. */
importScripts('./config.js');
const BASE = new URL('./', self.location.href);
const API = ((self.SCHEDULE_CONFIG && self.SCHEDULE_CONFIG.apiBase) || self.location.origin).replace(/\/$/, '');
const PREFIX = 'schedule8g-' + BASE.pathname + '-';
const V = PREFIX + 'v26';
const asset = p => new URL(p, BASE).href;
const STATIC = [
  './', 'index.html', 'config.js', 'offline-data.js', 'manifest.json',
  'icon.svg', 'icon-192.png', 'icon-512.png', 'apple-touch-icon.png',
  'assets/fonts/manrope-cyrillic-400-800-normal.woff2',
  'assets/fonts/manrope-latin-400-800-normal.woff2'
].map(asset);

/* Не даём одному отсутствующему файлу уронить всю установку. */
self.addEventListener('install', e => e.waitUntil(
  caches.open(V).then(c => Promise.all(STATIC.map(u => c.add(u).catch(() => {}))))
    .then(() => self.skipWaiting())
));

self.addEventListener('activate', e => e.waitUntil(
  caches.keys()
    .then(ks => Promise.all(ks.filter(k => k.startsWith(PREFIX) && k !== V).map(k => caches.delete(k))))
    .then(() => self.clients.claim())
));

self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { body: e.data.text() }; }
  const target = new URL('./', BASE);
  try { target.search = new URL(d.url || './', BASE).search; } catch (_) {}
  e.waitUntil(self.registration.showNotification(d.title || 'Расписание 8Г', {
    body: d.body || 'Расписание обновилось',
    icon: asset('icon-192.png'), badge: asset('icon-192.png'),
    tag: d.tag || 'schedule', renotify: true, lang: 'ru', data: { url: target.href }
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const u = new URL((e.notification.data && e.notification.data.url) || './', BASE);
  if (u.origin !== BASE.origin || !u.pathname.startsWith(BASE.pathname)) return;
  e.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async ws => {
    for (const w of ws) if (w.url === u.href && 'focus' in w) return w.focus();
    return clients.openWindow(u.href);
  }));
});

function b64u8(s) {
  const b = atob(s.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - s.length % 4) % 4));
  return Uint8Array.from(b, c => c.charCodeAt(0));
}
self.addEventListener('pushsubscriptionchange', e => e.waitUntil((async () => {
  try {
    const r = await fetch(API + '/api/push/key');
    const j = await r.json();
    if (!j.supported || !j.key) return;
    const sub = await self.registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64u8(j.key) });
    await fetch(API + '/api/push/subscribe', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subscription: sub.toJSON() })
    });
  } catch (_) {}
})()));

function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error('timeout')), ms);
    promise.then(v => { clearTimeout(t); resolve(v); }, err => { clearTimeout(t); reject(err); });
  });
}
function put(r, resp) {
  if (resp && resp.ok) {
    const copy = resp.clone();
    caches.open(V).then(c => c.put(r, copy)).catch(() => {});
  }
}
function fromCache(r) {
  return caches.match(r, { ignoreSearch: true });
}

self.addEventListener('fetch', e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== 'GET') return;

  /* Последний успешный ответ расписания: сеть есть — обновляем, нет — отдаём кэш. */
  if (u.pathname.indexOf('/api/schedule') >= 0) {
    const key = new Request(u.origin + u.pathname);
    e.respondWith((async () => {
      try {
        const resp = await withTimeout(fetch(r), 5000);
        if (resp.ok) {
          const copy = resp.clone();
          caches.open(V).then(c => c.put(key, copy)).catch(() => {});
        }
        return resp;
      } catch (_) {
        const hit = await caches.match(key);
        return hit || Response.error();
      }
    })());
    return;
  }

  const same = u.origin === BASE.origin && u.pathname.startsWith(BASE.pathname);
  if (!same) return;

  /* Страница и конфиги: свежее из сети, офлайн — из кэша. */
  const navig = r.mode === 'navigate';
  const freshFirst = navig || /\/(index\.html|config\.js|offline-data\.js|manifest\.json|sw\.js)$/.test(u.pathname) || u.pathname === BASE.pathname;
  if (freshFirst) {
    e.respondWith((async () => {
      try {
        const resp = await withTimeout(fetch(r), 5000);
        put(r, resp);
        return resp;
      } catch (_) {
        const hit = await fromCache(r);
        return hit || (navig ? await caches.match(asset('./')) : null) || Response.error();
      }
    })());
    return;
  }

  /* Иконки и шрифты: мгновенно из кэша, обновление в фоне без ожидания. */
  e.respondWith((async () => {
    const hit = await fromCache(r);
    const net = fetch(r).then(resp => { put(r, resp); return resp; }).catch(() => null);
    return hit || await net || Response.error();
  })());
});
