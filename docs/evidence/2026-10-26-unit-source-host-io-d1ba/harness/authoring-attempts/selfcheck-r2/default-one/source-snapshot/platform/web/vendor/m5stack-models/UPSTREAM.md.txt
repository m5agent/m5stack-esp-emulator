# Public visual model snapshot

Source: https://github.com/yuyun2000/m5stack-models

Commit: `48ab992f5ff63c1a91296051e1afcb5959877903`

Copied from Git objects with an explicit allowlist. Local changes and private research are never copied. `vendor-manifest.json` records every source file's SHA-256. The original `source-manifest.json` records geometry provenance.

Preserve `LICENSE`, `THIRD_PARTY_NOTICES.md` and `licenses/` when redistributing. Official remote photos are not bundled or relicensed. All models are visual shells: firmware, controller, bus and sensor evidence come from this project's Device Service.

This source uses the site's single Three.js 0.186.1 import-map instance. Load `src/loaders.js` to keep models lazy; do not import `src/index.js` in the first-screen bundle.

Update explicitly with the `sync_command` in the manifest, inspect its diff, then run `node platform/tests/test_model_shell.mjs` and the browser integration probe. Use `--check` to confirm a reproducible snapshot.
