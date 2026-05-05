// Auto-generiert von generate_report.py — Service Worker
// Cache-Version: 20260505-1401 (wird bei jedem Daily-Run aktualisiert)
const CACHE_NAME = 'squeeze-20260505-1401';
const URLS = [
  './',
  './index.html',
  './score_history.json',
  './agent_signals.json',
  './app_data.json',
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(URLS).catch(() => null)));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  // Nur Same-Origin und unsere 4 gecachten Pfade
  if (url.origin !== self.location.origin) return;
  const path = url.pathname.split('/').pop();
  if (!['index.html', '', 'score_history.json', 'agent_signals.json', 'app_data.json'].includes(path)) return;
  event.respondWith((async () => {
    try {
      const fresh = await fetch(req);
      if (fresh && fresh.status === 200) {
        const cache = await caches.open(CACHE_NAME);
        cache.put(req, fresh.clone()).catch(() => null);
      }
      return fresh;
    } catch (err) {
      const cached = await caches.match(req);
      if (cached) return cached;
      throw err;
    }
  })());
});
