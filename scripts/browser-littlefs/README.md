# Browser LittleFS fixture composer

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
rebuild an extracted archive, pass `--cache littlefs --fixture-dir fixture`.
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
