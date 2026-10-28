# coi-serviceworker

Unmodified `coi-serviceworker.js` from [Guido Zuidhof and contributors](https://github.com/gzuidhof/coi-serviceworker/tree/7b1d2a092d0d2dd2b7270b6f12f13605de26f214), commit `7b1d2a092d0d2dd2b7270b6f12f13605de26f214`.

- License: MIT; see [LICENSE](LICENSE).
- Source SHA256: `e97bbac6017322d48aa54a5bc7ce473c725a4b7376ff245002e0ba71c3dcdd7e`.
- Local integration: `public-coi.js` owns registration, project scope, first-control waiting and one automatic reload. `public-coi-serviceworker.js` is exported at the project root and imports this file in Worker context.
- Policy: `require-corp` and `same-origin`; no credentialless downgrade, firmware cache or session persistence.

This bootstrap enables shared browser memory. It does not establish any firmware, device, peripheral, timing or hardware compatibility.
