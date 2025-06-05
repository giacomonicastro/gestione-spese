// service-worker.js
const CACHE_NAME = 'gestione-spese-cache-v1';

// Lista delle pagine e delle risorse principali da salvare subito.
const urlsToCache = [
  '/',
  '/statistiche',
  '/static/manifest.json',
  '/static/icon-192x192.png',
  '/static/icon-512x512.png',
  'https://cdn.jsdelivr.net/npm/chart.js'
];

// Evento di installazione: apre la cache e aggiunge le risorse di base.
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        console.log('Cache aperta e file di base aggiunti');
        return cache.addAll(urlsToCache);
      })
  );
});

// Evento fetch: intercetta ogni richiesta dalla pagina.
// Prova prima a cercare nella cache. Se non trova nulla, va in rete.
self.addEventListener('fetch', function(event) {
  event.respondWith(
    caches.match(event.request)
      .then(function(response) {
        if (response) {
          // Se la risorsa è in cache, la restituisce
          return response;
        }
        // Altrimenti, la richiede alla rete
        return fetch(event.request);
      }
    )
  );
});