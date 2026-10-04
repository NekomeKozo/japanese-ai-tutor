'use strict';
// Replaced by the server with a content version and three exact public URLs.
const CONFIG = __PWA_CONFIG__;
const CACHE_NAME = 'goigrow-public-v1-' + CONFIG.version;
const ALLOWED = new Set(CONFIG.assets.map(asset => new URL(asset.url, self.location.origin).href));
const OFFLINE_URL = new URL(CONFIG.offline, self.location.origin).href;

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    try {
      const cache = await caches.open(CACHE_NAME);
      for (const asset of CONFIG.assets) {
        // These exact public routes never set cookies. Fetch hides Set-Cookie
        // in browsers, so omit credentials and pin the authored body integrity.
        const request = new Request(new URL(asset.url, self.location.origin), {
          credentials: 'omit', cache: 'reload', redirect: 'error', integrity: asset.integrity
        });
        const response = await fetch(request);
        if (!response.ok || response.status !== 200 || response.redirected ||
            !['basic', 'default'].includes(response.type) || response.headers.has('set-cookie')) {
          throw new Error('Public offline asset unavailable');
        }
        await cache.put(request, response);
      }
    } catch (error) {
      await caches.delete(CACHE_NAME);
      throw error;
    }
    // No skipWaiting: let open learning sessions finish with their current worker.
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (/^goigrow-public-v1-[a-f0-9]{20}$/.test(name) && name !== CACHE_NAME) await caches.delete(name);
    }
    // No clients.claim or reload: a normal subsequent navigation adopts this worker.
  })());
});

async function offlineNavigation(request) {
  try { return await fetch(request); }
  catch {
    let fallback;
    try { fallback = await (await caches.open(CACHE_NAME)).match(OFFLINE_URL); } catch { /* Storage may be unavailable. */ }
    if (fallback) return new Response(fallback.body, {status:503, headers:fallback.headers});
    return new Response('<!doctype html><html lang="en"><meta charset="utf-8"><title>GoiGrow — Connection unavailable</title><h1>You’re offline</h1><p>GoiGrow needs an internet connection to access your learning progress and AI Tutor. Please reconnect and try again.</p><form action="/" method="get"><button type="submit">Try again</button></form></html>', {
      status:503, headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}
    });
  }
}

self.addEventListener('fetch', event => {
  const request = event.request, url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin || request.headers.has('authorization') || request.headers.has('range')) return;
  if (request.mode === 'navigate' && (url.pathname === '/' || url.pathname === '/access')) {
    // Always ask the server, including for sign-in redirects and error responses.
    event.respondWith(offlineNavigation(request));
  } else if (ALLOWED.has(url.href)) {
    event.respondWith((async () => {
      try {
        const cached = await (await caches.open(CACHE_NAME)).match(request.url);
        if (cached) return cached;
      } catch { /* Continue online when cache storage is unavailable. */ }
      // Runtime responses are never written, even for an approved public URL.
      return fetch(request);
    })());
  }
  // Everything else is the browser's ordinary network request. No API handling,
  // HTML snapshots, queues, retries, background sync, transcripts or recordings.
});
