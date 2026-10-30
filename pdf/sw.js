// Offline cache for RBx9 PDF. Bump VERSION whenever app files change.
const VERSION = 'rbx9-pdf-v1';
const FILES = ['./', 'index.html', 'app.css', 'app.js', 'icon.svg', 'icon-180.png', 'manifest.webmanifest',
  'vendor/pdf-lib.esm.min.js', 'vendor/pdf.min.mjs', 'vendor/pdf.worker.min.mjs'];

self.addEventListener('install', (e) => e.waitUntil(caches.open(VERSION).then((c) => c.addAll(FILES)).then(() => self.skipWaiting())));
self.addEventListener('activate', (e) => e.waitUntil(
  caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
// Network first so updates show up immediately; fall back to the cache offline.
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  e.respondWith(fetch(e.request).then((res) => {
    const copy = res.clone();
    caches.open(VERSION).then((c) => c.put(e.request, copy));
    return res;
  }).catch(() => caches.match(e.request, { ignoreSearch: true })));
});
