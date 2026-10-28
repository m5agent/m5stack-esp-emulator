// Export this entry as <project-root>/coi-serviceworker.js. Its natural scope
// then stays inside the Pages project without Service-Worker-Allowed headers.
// The pinned, unmodified MIT implementation adds require-corp/same-origin
// response headers; it does not cache firmware, sessions or user files.
importScripts(new URL('./platform/web/vendor/coi-serviceworker/coi-serviceworker.js', self.location.href).href);
