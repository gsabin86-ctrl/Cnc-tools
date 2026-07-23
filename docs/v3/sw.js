// Bump this when the cached application contract changes. Shell and JSON
// requests still refresh from the network whenever it is available.
const VERSION = '3.4.0-shell-7'
const CACHE = `cnc-toolbase-${VERSION}`
const BASE = new URL('./', self.location.href)
const PRECACHE = [
  './', './index.html', './app.css', './app.js', './manifest.webmanifest', './toolbase-card.png',
  './data/catalog-index.json', './data/catalog-details.json', './data/build-meta.json'
].map(path => new URL(path, BASE).href)

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PRECACHE)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key.startsWith('cnc-toolbase-') && key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', event => {
  const request = event.request
  const requestUrl = new URL(request.url)
  if (request.method !== 'GET' || requestUrl.origin !== self.location.origin) return
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).then(response => {
      const copy = response.clone()
      caches.open(CACHE).then(cache => cache.put(new URL('./index.html', BASE), copy))
      return response
    }).catch(() => caches.match(new URL('./index.html', BASE))))
    return
  }
  const refreshOnline = requestUrl.pathname.startsWith(BASE.pathname + 'data/') || [
    new URL('./app.css', BASE).pathname,
    new URL('./app.js', BASE).pathname,
    new URL('./manifest.webmanifest', BASE).pathname,
  ].includes(requestUrl.pathname)
  if (refreshOnline) {
    event.respondWith(fetch(request).then(response => {
      if (response.ok) caches.open(CACHE).then(cache => cache.put(request, response.clone()))
      return response
    }).catch(() => caches.match(request, { ignoreSearch: true })))
    return
  }
  event.respondWith(caches.match(request, { ignoreSearch: true }).then(cached => cached || fetch(request).then(response => {
    if (response.ok) caches.open(CACHE).then(cache => cache.put(request, response.clone()))
    return response
  })))
})
