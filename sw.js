/* Расписание 8Г — сервис-воркер: мгновенный запуск, свежие данные, работа офлайн. */
const V = 'sched-v18';
const STATIC = ['/', '/index.html', '/manifest.json', '/icon.svg', '/icon-192.png', '/icon-512.png', '/apple-touch-icon.png'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(V)
      .then(c => c.addAll(STATIC))
      .catch(() => {})
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

const put = (req, resp) => {
  if (resp && resp.ok) {
    const cp = resp.clone();
    caches.open(V).then(c => c.put(req, cp)).catch(() => {});
  }
  return resp;
};

// Push от сервера: новое или изменённое расписание.
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { body: e.data ? e.data.text() : '' }; }
  const title = d.title || 'Расписание 8Г';
  e.waitUntil(self.registration.showNotification(title, {
    body: d.body || 'Расписание обновилось',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    tag: d.tag || 'schedule',
    renotify: true,
    lang: 'ru',
    data: { url: d.url || '/' }
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || '/', self.location.origin).href;
  e.waitUntil((async () => {
    const ws = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const w of ws) {
      if (w.url === url && 'focus' in w) return w.focus();
    }
    if (clients.openWindow) return clients.openWindow(url);
  })());
});

// Браузер обновил подписку — сообщаем серверу, чтобы уведомления не пропали.
self.addEventListener('pushsubscriptionchange', e => {
  e.waitUntil((async () => {
    try {
      const r = await fetch('/api/push/key');
      const j = await r.json();
      if (!j.key) return;
      const sub = await self.registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: b64u8(j.key)
      });
      await fetch('/api/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subscription: sub.toJSON() })
      });
    } catch (_) {}
  })());
});

function b64u8(s) {
  s = String(s).replace(/-/g, '+').replace(/_/g, '/');
  const pad = s.length % 4 ? '='.repeat(4 - s.length % 4) : '';
  const bin = atob(s + pad);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.method !== 'GET') return;
  const u = new URL(r.url);
  if (u.origin !== location.origin) return;

  // Данные: сначала сеть (расписание всегда свежее), при офлайне — последняя копия.
  if (u.pathname.startsWith('/api/')) {
    e.respondWith(
      fetch(r).then(resp => put(r, resp))
        .catch(() => caches.match(r).then(m => m || Response.error()))
    );
    return;
  }

  // Навигация (страница): сначала сеть — всегда показываем свежий HTML.
  // При офлайне — последняя сохранённая копия.
  if (r.mode === 'navigate') {
    e.respondWith(
      fetch(r)
        .then(resp => put(r, resp))
        .catch(() => caches.match(r, { ignoreSearch: true }).then(m => m || caches.match('/')))
    );
    return;
  }

  // Остальная статика: мгновенно из кэша, в фоне тихо обновляем.
  e.respondWith(
    caches.match(r, { ignoreSearch: true }).then(hit => {
      const net = fetch(r)
        .then(resp => put(r, resp))
        .catch(() => hit || (r.mode === 'navigate' ? caches.match('/') : null));
      return hit || net.then(m => m || Response.error());
    })
  );
});
