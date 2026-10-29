# Public visual model snapshot

Source: https://github.com/yuyun2000/m5stack-models

Commit: `4879ab51eb8bb11ce024e670ae6880529e3d0f42`

Copied from Git objects with explicit file/hash allowlists. Upstream worktree changes and private research are never copied. A separate reviewed local runtime patch layer preserves mainline pause/resume rendering on the upstream hidden-viewport fit fix. `vendor-manifest.json.local_runtime_patches` pins each upstream preimage, patch file and effective result; `files` hashes the effective bytes. Both upstream and patched runtime resource closures are checked. Reviewed public guide/provenance texts remain pinned separately at `3681a6482aff96501d44659ba5a1603246f1fe1f` and preserve their source bytes and close relative links in the bundled guides. `vendor-manifest.json` records each source file and the reviewed guide closure. The unchanged upstream `source-manifest.json` records provenance; its `sourceCommit` is a historical preparation baseline, not this snapshot Git pin.

Preserve `LICENSE`, `THIRD_PARTY_NOTICES.md` and `licenses/` when redistributing. Reviewed product sticker PNGs, including source-vector rasters and authorized reference redraws, retain the provider-permission notice and per-file hashes. Artwork and marks retain their original rights and are not relicensed as MIT; official remote photos, vectors and generators are not bundled. All models are visual shells: firmware, controller, bus and sensor evidence come from this project's Device Service.

This source uses the site's single Three.js 0.186.1 import-map instance. Load `src/loaders.js` to keep models lazy; do not import `src/index.js` in the first-screen bundle.

Update explicitly with the `sync_command` in the manifest, inspect its diff, then run `node platform/tests/test_model_shell.mjs` and the browser integration probe. Use `--check` to confirm a reproducible snapshot.
