const CACHE = 'parking-offline-v1';
const ASSETS = ['/acceso/dispositivo/', '/static/parking/style.css?v=8', '/static/parking/offline.js', '/static/parking/offline-store.js'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting())); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('parking-offline-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);
    if (url.origin !== self.location.origin || event.request.method !== 'GET') return;
    if (ASSETS.includes(url.pathname + url.search)) {
        event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
    } else if (event.request.mode === 'navigate' && url.pathname.startsWith('/acceso/')) {
        event.respondWith(fetch(event.request).catch(() => caches.match('/acceso/dispositivo/')));
    }
});
