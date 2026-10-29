# Per-board browser display probe

This source runs the original UIFlow2 `M5.begin`, `M5.Display`, `M5.update`
and `BtnA` or `Touch` driver in the guest. It is a small controller-path probe,
not an LVGL, networking, audio or hardware equivalence claim. It draws a red
corner marker, then changes that marker to green when the guest receives an
input. Serial `M5_BROWSER_PROBE` JSON binds board, display size, input edges,
counter and heartbeat to the same guest.

`platform/web/qemu-browser-profiles.json` binds each candidate's official
reference URL/hash, merged image layout, actual VFS partition, eFuse package,
rotation, source hashes, generated `browser_probe_config.py` and composed
firmware hash. The generic source is intentionally not installed on other
boards without their own fixture entry. QEMU frame/input coordinates remain
physical framebuffer coordinates; the host does not repeat the guest rotation.
Core2 uses the separately pinned `core2_boot.py` as `boot.py`, retaining its
firmware-owned console. The S3 UART redirection is not installed on Core2:
that exact firmware rejects reinitializing UART0 before `main.py` runs.

`composeQemuProbeFirmware` uses the separately source-built LittleFS WASM.
It parses exactly one unencrypted `vfs` partition before mounting, never
formats, writes only three reviewed Python paths, remounts and reads them
back, and requires the complete resulting Flash hash to match the independently
verified Python `uiflow_source` composition. That independent composition
verifies every pre-existing file and all bytes outside the VFS.

Rebuild and run packaging verification with explicit, locally obtained inputs:

```sh
python3 scripts/browser-littlefs/build.py --emcc /path/to/emcc \
  --output .work/browser-littlefs-multiboard
node platform/tests/test_public_qemu_probe_firmware.mjs \
  --runtime .work/browser-littlefs-multiboard \
  --base /path/to/hash-matching-official-base.bin --device atoms3r \
  --out-dir .work/atoms3r-composition
```

This command executes only LittleFS in Chromium; it does not execute a guest.
Real board acceptance must additionally use an explicit candidate static
export, load the composed image, inspect nonempty native frame pixels,
exercise input press/release and guest counter changes, and record clean stop
and Worker/iframe disposal. Candidate metadata and packaging success never
grant public browser admission.

The frame oracle requires the full native 8x8 red marker to change to green
at the same pixel locations, with no old red pixels remaining. It also records
the marker's offset from the guest coordinates. AtomS3R currently has an
observed +2 physical-row offset; functional input/frame acceptance leaves
that display-coordinate calibration boundary open. Public admission, when
granted with matching guest evidence, covers the recorded firmware and input
path rather than complete pixel calibration or all board peripherals.

API references checked before creating the probe:
`uiflow2-coder/docs/hardware/display.md`, `hardware/button.md`, and
`hardware/touch.md`; existing repository device-local probes provide the
board rotation and original driver path.
