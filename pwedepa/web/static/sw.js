const CACHE = "pwedepa-v4";
const ASSETS = [
  "/static/tokens.css",
  "/static/app.css",
  "/static/app.js",
  "/static/icons/icon-static.png",
  "/static/icons/icon-maskable-192.png",
  "/static/icons/icon-maskable-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // A page holds one person's work, so only our own static files are kept.
        const url = new URL(event.request.url);
        if (response.ok && url.origin === self.location.origin && url.pathname.startsWith("/static/")) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request)),
  );
});
