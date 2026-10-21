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

## Vendored runtime

`platform/runtime/wasm/` contains the esp-emulator WebAssembly runtime and its
Apache-2.0 license. See `platform/runtime/wasm/LICENSE`.

## Firmware and ROM images

Official UIFlow2 firmware, third-party demo firmware, and Espressif ROM images
are not redistributed by this repository. `platform/tools/fetch_firmware.py`
downloads firmware from M5Stack's public firmware CDN into an ignored local
cache. QEMU/Espressif ROM files must be obtained from their upstream
distributions.

## Product names and reference images

M5Stack product names, product photos, reference cutouts, and device trade
dress are used for identification and interoperability documentation. They are
not covered by the root MIT license and remain the property of their respective
owners.
