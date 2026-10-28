# Third-party notices

The root MIT license covers original project code and documentation. The
following components, patches, assets, and references retain their own terms.

## Upstream source and patches

- [zqqf16/M5StopWatch-QEMU](https://github.com/zqqf16/M5StopWatch-QEMU) is a
  key reference for the StopWatch QEMU path. Its project code is MIT-licensed;
  its QEMU patches and QEMU binaries are GPL-2.0-or-later.
- [espressif/qemu](https://github.com/espressif/qemu) is the QEMU source base.
  QEMU patches in this repository remain GPL-2.0-or-later.
- [espressif/esp-emulator](https://github.com/espressif/esp-emulator) provides
  the RISC-V emulator and download/control interfaces. Its license is
  Apache-2.0.
- [m5stack/uiflow-micropython](https://github.com/m5stack/uiflow-micropython),
  [m5stack/M5GFX](https://github.com/m5stack/M5GFX), and
  [m5stack/M5Unified](https://github.com/m5stack/M5Unified) are MIT-licensed.
  This project ships patches and integration code for those upstreams, not
  their complete source trees.
- Selected font-source evidence retains the upstream terms of
  [tobozo/LGFX_Fonts at 253cf549](https://github.com/tobozo/LGFX_Fonts/tree/253cf549fe0b1aa932be68fe06a13c3077918d61).
  Its exact MIT notice is preserved in
  [LGFX_Fonts-253cf549.txt](third_party/licenses/LGFX_Fonts-253cf549.txt).
  The repository's root license does not relicense upstream font assets.

## Vendored runtime

`platform/runtime/wasm/` contains the esp-emulator WebAssembly runtime and its
Apache-2.0 license. See `platform/runtime/wasm/LICENSE`.

The independent browser backend uses the MIT-licensed `esp32sim` fork
[zhuzhe1983/esp-online-tester](https://github.com/zhuzhe1983/esp-online-tester)
at `3cd3db3b7202e9fc559328c7247c11134c0437f9`, derived from
[mikroverk/esp32sim](https://github.com/mikroverk/esp32sim). The unchanged
Worker/JavaScript glue, license and source hashes are in
`platform/web/vendor/esp32sim/`. `bootstrap_browser_runtime.py` builds the
WASM from pinned source and preserves source notices in the export;
the compiled WASM is not committed to source Git.

## Unit drivers, fixtures and visual assets

- Selected UIFlow2 Unit drivers under `tests/units/` retain their original MIT
  notices and bundled `LICENSE.MIT`. Source manifests bind the copied file
  hashes; newer IO/sensor manifests also resolve upstream commits. The older
  controls manifest records `master` source URLs with file hashes, without a
  resolved commit. They are not relicensed by this repository.
- `platform/tests/fixtures/uiflow-flash_light-2.5.3.py` is an unchanged MIT
  UIFlow2 source fixture. Its adjacent source manifest records the upstream
  commit, URL and hash; its original SPDX header and the driver license remain
  available. It is used for offline regression, not runtime evidence.
- The public MLX90640 example data exported under
  `platform/units/fixtures/mlx90640-public-example/` is from the Apache-2.0
  Pimoroni library example workbook. Its license, source commit, export changes
  and data provenance are retained in that directory's license and notice.
- S3 ADC eFuse definitions, calibration equations and fixed coefficients derive
  from Espressif ESP-IDF commit
  `b774170ff46c393eeb5e495ea37936038d3f4f4f`, Copyright 2019-2023 Espressif
  Systems, under Apache-2.0. The synthetic fixture, numeric reference helper and
  C oracle preserve this attribution; see
  `platform/units/fixtures/LICENSE.Espressif-ADC` and the fixture's source list.
  These are synthetic calibration inputs, not physical calibration records.
- `platform/web/vendor/m5stack-models/` is imported from the MIT-licensed
  `yuyun2000/m5stack-models` commit
  `c48940c3aad3f2e8e9b8906b82071a88f2a3de1e`; retain its `LICENSE`,
  `THIRD_PARTY_NOTICES.md` and source manifests. Three.js and the imported
  BufferGeometryUtils addon retain their upstream MIT terms and notices.
  Imported guides retain their separately recorded older source pin.

## Firmware and ROM images

Official UIFlow2 firmware, third-party demo firmware, and Espressif ROM images
are not committed to this repository's source Git. `platform/tools/fetch_firmware.py`
downloads firmware from M5Stack's public firmware CDN into an ignored local
cache. QEMU/Espressif ROM files must be obtained from their upstream
distributions. The optional browser-site export includes only the reviewed
ESP32-S3 ROM from Espressif's `esp-rom-elfs` release `20260528`, with its
Apache-2.0 license and a SHA-bound source receipt. The bootstrap script checks
both the release archive and extracted ROM. It does not package firmware.

## Product names and reference images

M5Stack product names, product photos, reference cutouts, and device trade
dress are used for identification and interoperability documentation. They are
not covered by the root MIT license and remain the property of their respective
owners.
