const CACHE_NAME = "emaus-pwa-shell-v1";
const OFFLINE_PAGE = "/static/pwa/offline.html";
const SHELL_FILES = [
  OFFLINE_PAGE,
  "/static/pwa/offline.css",
  "/static/pwa/offline.js",
  "/static/pwa/manifest.webmanifest",
  "/static/pwa/icon.svg"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(SHELL_FILES))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(key => key.startsWith("emaus-pwa-shell-") && key !== CACHE_NAME)
          .map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Los recursos propios de la pantalla offline se sirven desde caché.
  if (url.pathname.startsWith("/static/pwa/")) {
    event.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
        }
        return response;
      }))
    );
    return;
  }

  // Nunca se guardan páginas HTML autenticadas ni respuestas de la API.
  // Si la navegación falla por falta de conexión, se muestra la pantalla offline.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match(OFFLINE_PAGE).then(cached =>
          cached || new Response(
            "No hay conexión y la pantalla offline aún no está disponible. Conéctate una vez a Internet para prepararla.",
            {status: 503, headers: {"Content-Type": "text/plain; charset=utf-8"}}
          )
        )
      )
    );
  }
});
