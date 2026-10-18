/* Расписание 8Г — сервис-воркер: мгновенный запуск, свежие данные, работа офлайн. */
const V = 'sched-v12';
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

  // Статика: мгновенно из кэша, в фоне тихо обновляем.
  e.respondWith(
    caches.match(r, { ignoreSearch: true }).then(hit => {
      const net = fetch(r)
        .then(resp => put(r, resp))
        .catch(() => hit || (r.mode === 'navigate' ? caches.match('/') : null));
      return hit || net.then(m => m || Response.error());
    })
  );
});
