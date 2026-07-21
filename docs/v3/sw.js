const VERSION = new URL(self.location.href).searchParams.get('v') || 'development'
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
  if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) return
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).then(response => {
      const copy = response.clone()
      caches.open(CACHE).then(cache => cache.put(new URL('./index.html', BASE), copy))
      return response
    }).catch(() => caches.match(new URL('./index.html', BASE))))
    return
  }
  event.respondWith(caches.match(request).then(cached => cached || fetch(request).then(response => {
    if (response.ok) caches.open(CACHE).then(cache => cache.put(request, response.clone()))
    return response
  })))
})
