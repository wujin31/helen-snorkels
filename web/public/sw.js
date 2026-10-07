// Network first, cache as the offline fallback: always fresh when online,
// and the last known answer (with its honest timestamp) when not.
// Entries are keyed without the query string, so the cache-busting
// `status.json?t=...` refresh keeps one copy instead of one per fetch.
const CACHE = "snorkel-status-v2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) =>
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  ),
);

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  url.search = "";
  const key = url.toString();
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(key, copy));
        }
        return response;
      })
      .catch(() => caches.match(key)),
  );
});
