# Browser LittleFS fixture composer

The original `_m5_lfs_mount` remains restricted to the reviewed CoreS3 VFS.
The additional `_m5_lfs_mount_sized` accepts an aligned, bounded region only;
the per-board caller first parses and verifies the actual unencrypted UIFlow2
`vfs` partition and its pinned base image. Neither entry point formats a failed
mount. Writes remain limited to `boot.py`, `main.py` and the explicit
`browser_probe_config.py` and `candidate_lvgl_loop.py` paths.

Candidate per-board composition uses `composeQemuProbeFirmware` in
`platform/web/public-qemu-probe-firmware.js` and the source/whole-Flash
identities in `qemu-browser-profiles.json`. Its real Chromium packaging test is
`platform/tests/test_public_qemu_probe_firmware.mjs`; firmware execution is a
separate explicit board-guest gate. See
[`board_display`](../../tests/browser-qemu/board_display/README.md).

This builds a small independent WebAssembly module from official littlefs
v2.11.3, commit `6cb4e86540eca0d9ba62500a298385c9d863c8be`. That is the exact
submodule pinned by littlefs-python v0.19.0. Each fetched source file has a
reviewed SHA256 in `build.py`. littlefs uses BSD-3-Clause; the adapter uses MIT.

```sh
python3 scripts/browser-littlefs/build.py \
  --emcc .work/qemu-browser-probe/emsdk/upstream/emscripten/emcc \
  --output .work/browser-littlefs
```

Emscripten 3.1.50 is required. `--offline` requires the already verified source
cache. The output contains `littlefs.mjs`, `littlefs.wasm`, `LICENSE.littlefs`,
`LICENSE.composer`, `LICENSE.emscripten`, `LICENSE.musl`, `source.zip`, fixture
`boot.py`/`main.py`, and `manifest.json`. The archive holds
the pinned littlefs sources, adapter/build sources, and fixture sources. To
rebuild an extracted archive, pass `--cache littlefs --fixture-dir fixture
--wallclock-fixture-dir wallclock-fixture`.
The builder never downloads or bundles firmware or ROMs and never runs a guest.

`platform/web/public-demo-firmware.js` exports `DEMO_FIRMWARE` and
`composeDemoFirmware({baseBytes, baseURL, manifestURL, signal, onProgress})`.
Without `baseBytes`, the browser fetches the fixed official M5Burner CDN base;
an unavailable or CORS-blocked download can instead use user-selected bytes.
The default manifest location is `platform/runtime/littlefs/manifest.json`.
The public site exporter copies this independently built directory there.

The module verifies the raw base, normalized base, module/WASM/fixture assets,
and final image SHA256. It writes only the existing VFS partition, never formats
an unmountable image, preserves the rest of the Flash, and reads back both
fixture files after remounting. Its block/read/program/lookahead/cycle/cache
settings match `platform/tools/uiflow_source.py` and littlefs-python defaults.
Only the exact admitted CoreS3 base and two fixed source files are supported.
The final `78961297…` hash is required before bytes are returned. The result is
`{bytes, sha256, fileName, provenance}`; it is packaging evidence, not execution.

The separate `WALLCLOCK_DEMO_FIRMWARE` and
`composeWallclockDemoFirmware({...same options})` select the explicit
`sdk-python-single-schedule-v1` candidate. Its three sources live at
`fixtures/cores3-lvgl-wallclock/` in the generated composer output and are
declared under `manifest.fixtures["cores3-wasm-lvgl-wallclock-v1"]`; the original
top-level `fixture` and old API retain their exact `78961297…` identity.
The candidate returns only the reviewed `e9500994…` Flash after remounting and
reading back all three files, checking 18 files (17 base files plus the candidate
module), and verifying the complete output hash. Its provenance records the
source bundle, scheduler candidate and normal clock divisor 1. This adds an
explicit packaging option; it does not change the default UI or device profile.

This tool's BSD/MIT licenses do not grant redistribution rights to an imported
firmware image or ROM. Keep raw base, derived Flash, and ROM out of published
artifacts; composition happens locally in the user's browser memory.

An opt-in real Chromium packaging test covers both download and local import,
the exact composed hash, preserved files, cancellation and tampered inputs:

```sh
M5_WASM_NODE_MODULES=/path/to/node_modules \
node platform/tests/test_browser_littlefs.mjs \
  --runtime .work/browser-littlefs --base /path/to/official-raw-base.bin \
  --out-dir .work/littlefs-packaging-check
```

`M5_WASM_CHROME` optionally selects an installed Chromium executable. This
starts only an owned loopback static test server on an ephemeral port. It runs
no Device Service or guest and writes only a concise JSON report, never Flash.
