/**
 * PLAGENOR 4.0 - Service Worker
 * Progressive Web App (PWA) Support
 * 
 * Features:
 * - Offline support
 * - Cache management
 * - Push notifications (future)
 * - Background sync (future)
 */

const CACHE_NAME = 'plagenor-v4.0.0';
const STATIC_CACHE = 'plagenor-static-v4.0.0';
const DYNAMIC_CACHE = 'plagenor-dynamic-v4.0.0';

// Static assets to cache on install
const STATIC_ASSETS = [
    '/',
    '/accounts/login/',
    '/static/css/main.css',
    '/static/js/app.js',
    '/static/js/form-validation.js',
    '/static/icons/favicon.svg',
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
    console.log('[ServiceWorker] Installing...');
    
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then((cache) => {
                console.log('[ServiceWorker] Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => {
                console.log('[ServiceWorker] Install complete');
                return self.skipWaiting();
            })
            .catch((error) => {
                console.error('[ServiceWorker] Install failed:', error);
            })
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    console.log('[ServiceWorker] Activating...');
    
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames.map((cacheName) => {
                        if (cacheName !== STATIC_CACHE && cacheName !== DYNAMIC_CACHE) {
                            console.log('[ServiceWorker] Deleting old cache:', cacheName);
                            return caches.delete(cacheName);
                        }
                    })
                );
            })
            .then(() => {
                console.log('[ServiceWorker] Activation complete');
                return self.clients.claim();
            })
    );
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);
    
    // Skip non-GET requests
    if (request.method !== 'GET') {
        return;
    }
    
    // Skip API requests and POST forms
    if (url.pathname.startsWith('/api/') || 
        url.pathname.startsWith('/dashboard/api/') ||
        url.pathname.includes('login') && request.method === 'POST') {
        return;
    }
    
    // Skip external requests
    if (url.origin !== location.origin) {
        return;
    }
    
    // Handle navigation requests (HTML pages)
    if (request.mode === 'navigate') {
        event.respondWith(
            caches.match(request)
                .then((cachedResponse) => {
                    if (cachedResponse) {
                        // Return cached response and update cache in background
                        fetch(request)
                            .then((networkResponse) => {
                                caches.open(DYNAMIC_CACHE)
                                    .then((cache) => cache.put(request, networkResponse));
                            })
                            .catch(() => {});
                        return cachedResponse;
                    }
                    
                    // No cache, fetch from network
                    return fetch(request)
                        .then((networkResponse) => {
                            // Cache the response
                            caches.open(DYNAMIC_CACHE)
                                .then((cache) => cache.put(request, networkResponse.clone()));
                            return networkResponse;
                        })
                        .catch(() => {
                            // Offline fallback for navigation
                            return caches.match('/') || caches.match('/accounts/login/');
                        });
                })
        );
        return;
    }
    
    // Handle static assets (CSS, JS, images)
    if (url.pathname.startsWith('/static/') || 
        url.pathname.startsWith('/media/')) {
        event.respondWith(
            caches.match(request)
                .then((cachedResponse) => {
                    if (cachedResponse) {
                        return cachedResponse;
                    }
                    
                    return fetch(request)
                        .then((networkResponse) => {
                            caches.open(STATIC_CACHE)
                                .then((cache) => cache.put(request, networkResponse.clone()));
                            return networkResponse;
                        });
                })
        );
        return;
    }
    
    // Handle fonts and external CDN resources
    if (url.hostname === 'fonts.googleapis.com' || 
        url.hostname === 'fonts.gstatic.com' ||
        url.hostname === 'unpkg.com') {
        event.respondWith(
            caches.match(request)
                .then((cachedResponse) => {
                    if (cachedResponse) {
                        return cachedResponse;
                    }
                    
                    return fetch(request)
                        .then((networkResponse) => {
                            caches.open(DYNAMIC_CACHE)
                                .then((cache) => cache.put(request, networkResponse.clone()));
                            return networkResponse;
                        });
                })
        );
        return;
    }
    
    // Default: network-first strategy
    event.respondWith(
        fetch(request)
            .then((networkResponse) => {
                caches.open(DYNAMIC_CACHE)
                    .then((cache) => cache.put(request, networkResponse.clone()));
                return networkResponse;
            })
            .catch(() => {
                return caches.match(request);
            })
    );
});

// Background sync for offline form submissions (future)
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-forms') {
        console.log('[ServiceWorker] Background sync triggered');
        // Implement form data sync here
    }
});

// Push notifications (future implementation)
self.addEventListener('push', (event) => {
    if (!event.data) return;
    
    const data = event.data.json();
    const options = {
        body: data.body || 'New notification from PLAGENOR',
        icon: '/static/icons/favicon.svg',
        badge: '/static/icons/favicon.svg',
        vibrate: [100, 50, 100],
        data: {
            dateOfArrival: Date.now(),
            primaryKey: data.id,
        },
        actions: data.actions || [],
    };
    
    event.waitUntil(
        self.registration.showNotification(data.title || 'PLAGENOR', options)
    );
});

// Notification click handler
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then((clientList) => {
                // Focus existing window or open new one
                for (const client of clientList) {
                    if (client.url === '/' && 'focus' in client) {
                        return client.focus();
                    }
                }
                return clients.openWindow('/');
            })
    );
});

// Message handler for cache management
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
    
    if (event.data && event.data.type === 'CLEAR_CACHE') {
        caches.keys().then((cacheNames) => {
            return Promise.all(cacheNames.map((name) => caches.delete(name)));
        });
    }
    
    if (event.data && event.data.type === 'CACHE_URLS') {
        caches.open(DYNAMIC_CACHE).then((cache) => {
            cache.addAll(event.data.urls);
        });
    }
});
