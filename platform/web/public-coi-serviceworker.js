// Export as <project-root>/coi-serviceworker.js; scope stays inside the project.
// Adapted from coi-serviceworker v0.1.7, Guido Zuidhof and contributors (MIT).
// The pinned original, source notice and license remain in
// platform/web/vendor/coi-serviceworker/. This integration does not cache data.
let coepCredentialless = false;
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('message', event => {
  if (!event.data) return;
  if (event.data.type === 'deregister') {
    self.registration.unregister().then(() => self.clients.matchAll())
      .then(clients => clients.forEach(client => client.navigate(client.url)));
  } else if (event.data.type === 'coepCredentialless') {
    coepCredentialless = event.data.value;
  }
});

async function isolatedResponse(request) {
  const response = await fetch(request);
  if (response.status === 0) return response;
  const headers = new Headers(response.headers);
  headers.set('Cross-Origin-Embedder-Policy', coepCredentialless ? 'credentialless' : 'require-corp');
  if (!coepCredentialless) headers.set('Cross-Origin-Resource-Policy', 'cross-origin');
  headers.set('Cross-Origin-Opener-Policy', 'same-origin');
  // Chromium can expose an empty ReadableStream on a network 304. Supplying
  // that stream to Response is forbidden for null-body statuses and rejects
  // respondWith, turning a valid conditional frame into net::ERR_FAILED.
  const body = [204, 205, 304].includes(response.status) ? null : response.body;
  return new Response(body, {status: response.status, statusText: response.statusText, headers});
}

self.addEventListener('fetch', event => {
  const original = event.request;
  if (original.cache === 'only-if-cached' && original.mode !== 'same-origin') return;
  const request = coepCredentialless && original.mode === 'no-cors'
    ? new Request(original, {credentials: 'omit'}) : original;
  // Preserve network rejection; never fulfill respondWith with undefined.
  event.respondWith(isolatedResponse(request));
});
