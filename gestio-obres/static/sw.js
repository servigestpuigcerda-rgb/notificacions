// Service worker: guarda la interfície per obrir-la ràpid i amb mala cobertura.
// Les dades (API) sempre van a la xarxa.
const CACHE = "obres-v2";
const SHELL = ["/", "/static/styles.css", "/static/js/app.js", "/static/js/core.js", "/static/js/forms.js",
  "/static/js/v-inici.js", "/static/js/v-feines.js", "/static/js/v-pressupost.js", "/static/js/v-captura.js",
  "/static/js/v-factures.js", "/static/js/v-altres.js", "/static/js/assistent.js", "/static/js/render3d.js",
  "/static/js/v-render.js", "/static/js/v-feina-extra.js",
  "/static/vendor/three/three.module.min.js", "/static/vendor/three/OrbitControls.js", "/static/icon.svg", "/static/manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname === "/" || url.pathname.startsWith("/static/")) {
    // Xarxa primer, memòria cau si no hi ha connexió
    e.respondWith(fetch(e.request).then((r) => {
      const copia = r.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copia));
      return r;
    }).catch(() => caches.match(e.request)));
  }
});
