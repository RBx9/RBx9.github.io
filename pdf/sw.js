// Offline cache for RBx9 PDF. Bump VERSION (and the ?v= in index.html/app.js)
// whenever app files change.
const VERSION = 'rbx9-pdf-v8';
const FILES = ['./', 'index.html', 'app.css?v=8', 'app.js?v=8', 'compress.js?v=8', 'docx.js?v=8', 'edit.html', 'edit.css?v=8', 'edit.js?v=8', 'icon.svg', 'icon-180.png', 'manifest.webmanifest',
  'vendor/pdf-lib.esm.min.js', 'vendor/pdf.min.mjs', 'vendor/pdf.worker.min.mjs'];

self.addEventListener('install', (e) => e.waitUntil(caches.open(VERSION).then((c) => c.addAll(FILES)).then(() => self.skipWaiting())));
self.addEventListener('activate', (e) => e.waitUntil(
  caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
// Network first, always revalidating with the server so a browser's HTTP cache
// can't serve a stale mix of old and new files; fall back to the cache offline.
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  const sameOrigin = new URL(e.request.url).origin === location.origin;
  e.respondWith(fetch(e.request, sameOrigin ? { cache: 'no-cache' } : undefined).then((res) => {
    if (res.ok || res.type === 'opaque') {
      const copy = res.clone();
      caches.open(VERSION).then((c) => c.put(e.request, copy));
    }
    return res;
  }).catch(() => caches.match(e.request).then((hit) => hit || caches.match(e.request, { ignoreSearch: true }))));
});
