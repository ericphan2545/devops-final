/* Network-first shell cache. API requests and POST mutations are never cached. */
const CACHE = 'todo-clean-v2-' + __APP_VERSION_LITERAL__;
const ASSETS = ['/', '/static/style.css', '/static/app.js'];
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cache.addAll(ASSETS);
    await self.skipWaiting();
  })());
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if ((key.startsWith('todo-workspace-') || key.startsWith('todo-clean-v2-')) && key !== CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname === '/health' || url.pathname === '/metrics') return;
  const navigation = event.request.mode === 'navigate';
  if (!navigation && !['/static/style.css', '/static/app.js'].includes(url.pathname)) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const key = navigation ? '/' : url.pathname;
    try {
      const response = await fetch(event.request);
      if (response.ok) { await cache.put(key, response.clone()); return response; }
      const stored = await cache.match(key);
      return stored || response;
    } catch (_) {
      const stored = await cache.match(key);
      if (stored) return stored;
      return new Response('Chưa có bản lưu trang. Hãy mở ứng dụng một lần khi có mạng.', {
        status: 503, headers: {'Content-Type':'text/plain; charset=utf-8'}
      });
    }
  })());
});
