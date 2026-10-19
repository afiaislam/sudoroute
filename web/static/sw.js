// SudoRoute service worker: makes the site installable and shows a friendly page when offline.
// It never caches API responses or account data — money screens always come from the server.
const SHELL = "sudoroute-shell-v1";
self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(["/offline"])).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  if (e.request.mode !== "navigate") return;  // everything else goes straight to the network
  e.respondWith(fetch(e.request).catch(() => caches.match("/offline")));
});
