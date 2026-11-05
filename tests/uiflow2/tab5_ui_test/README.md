# Tab5 virtual UI test

This checked-in regression has two distinct execution modes:

- A serial probe may execute an admitted official image without an ELF. It
  requires an actual guest marker and provides no framebuffer or touch PASS.
- The full UI/touch lane requires the exact emulator-build ELF recorded in the
  running application's descriptor. That build exports a PSRAM framebuffer and
  GDB touch mailbox. The mailbox is not a controller-level ST7123 model, and
  another ELF's addresses must never be used to observe an official image.

## Image composition

`make_image.py` reads the actual partition table, overlays the probe's boot/main
in LittleFS and preserves every other stock file and every byte outside VFS.
Its `composition.json` records the original application partition/segment hashes
and verifies that the application bytes did not change. A trimmed merged image
is padded to 16 MiB. An entirely erased VFS in the emulator build may be
initialized; a populated filesystem that cannot be mounted is rejected.

```sh
PYTHONPATH=platform/tools:.work/py python3 tests/uiflow2/tab5_ui_test/make_image.py \
  --base /path/to/admitted-tab5.bin --out /path/to/tab5-test.bin
```

The old emulator image uses VFS `0x610000/0x1e0000`. The official v2.5.4 image
uses `0xaa0000/0x4c0000`; its application segments extend to `0x78db24`.
Formatting the old VFS location in that new image corrupts its application.
Optional `--vfs-offset`/`--vfs-size` are declarations: drift uses the actual
partition table by default, or fails with `--layout-policy strict`.

Pass an already composed image with both `--base ORIGINAL.bin` and
`--prebuilt-image DERIVED.bin` to skip composition. The runner still rejects
application changes and a stale ELF before launching virtual devices.

The `esptool` transport covers every populated sector, including system and VFS
partitions. The current esp-emu 0.50.0 P4 download lane is limited to populated
addresses below 8 MiB, so a new official layout with a high VFS must use the
`host-image` lane. That lane still executes the ROM and bootloader; it does not
claim an esptool download. No bootloader or application validation is bypassed.

## Official v2.5.4 boundary

The original `Factory app partition is not bootable` result came from a test
adapter that composed VFS twice and overwrote `0x610000` inside the application.
Correct composition preserves the latest application's bytes and removes that
particular bootloader rejection. This fixes the test input, not all production
P4 controller behavior.

The latest official app descriptor requires ELF SHA-256
`0bb5647cd2dd4136c3b0ef41ce1e84f50d87d98dfdac621768cfeb606f194fbb`.
The old emulator ELF is
`b02f850429014de264138b56babc2bdf263fc9cf66b0b014551f4eca90a59886`.
They are incompatible. The corrected official-image probe still has no proven
Python/UI/touch result on the current closed P4 backend; retain `PARTIAL` and its
serial/CPU evidence. An old merged-image UI/touch PASS does not transfer to it.

Future closure requires that same official app to reach its guest markers and
an actual supported display/input data plane, or a separately identified
compatibility build. Rebuilding the application with emulator hooks changes its
identity and must not be described as running the unchanged official binary.
Physical screen, touch, electrical and other hardware properties are untested.

The backend saves its `--efuse` file on normal exit. The runner therefore copies
the caller's input seed into the owned output directory and uses that mutable
copy for both download and execution, recording the input hash. The seed remains
read-only from the test's perspective.
