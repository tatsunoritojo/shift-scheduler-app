const CACHE_NAME = 'shift-mgmt-v1';
const STATIC_ASSETS = [
    '/static/css/common.css',
    '/static/css/worker.css',
    '/static/css/admin.css',
    '/static/css/owner.css',
    '/static/js/modules/api-client.js',
    '/static/js/modules/calendar-grid.js',
    '/static/js/modules/time-utils.js',
    '/static/js/modules/shift-calculator.js',
    '/static/js/modules/notification.js',
    '/static/js/worker-app.js',
    '/static/js/admin-app.js',
    '/static/js/owner-app.js',
    '/static/manifest.json',
];

// Install: cache static assets
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
    );
    self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

// Fetch: cache-first for static, network-first for API
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    // API calls: network first
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/')) {
        event.respondWith(
            fetch(event.request).catch(() => caches.match(event.request))
        );
        return;
    }

    // Static assets: cache first
    event.respondWith(
        caches.match(event.request).then(cached => {
            return cached || fetch(event.request).then(response => {
                if (response.ok && url.pathname.startsWith('/static/')) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
                }
                return response;
            });
        })
    );
});
