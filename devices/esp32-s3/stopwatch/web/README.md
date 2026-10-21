# StopWatch reference runtime

This page is the working reference device in the multi-device platform. It runs the
ported StopWatch UserDemo firmware and exposes `window.m5emu` for automation.

Shared runtime files live in `/platform/runtime/wasm/`. Firmware binaries are
not committed to the public repository. Download the official UIFlow2 image
with `python3 platform/tools/fetch_firmware.py stopwatch`, or select a local
merged ESP32-S3 image in the page.
