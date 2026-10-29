# Per-board browser display probe

These fixtures run the original UIFlow2 `M5.begin`, `M5.Display`, `M5.update`
and board input drivers in the guest. Serial `M5_BROWSER_PROBE` JSON binds the
board, logical display size, input edges, counter and heartbeat to the same
execution. LCD/OLED fixtures change a complete 8x8 red marker to green; EPD
fixtures change a 16x16 QUALITY-encoded black marker to white. They are bounded
controller-path probes: LVGL, networking, audio, unrelated Units and physical
hardware equivalence require separate evidence.

`platform/web/qemu-browser-profiles.json` binds each candidate's official
reference URL/hash, merged image layout, actual VFS partition, eFuse package,
rotation, source hashes, generated `browser_probe_config.py` and composed
firmware hash. The generic source is intentionally not installed on other
boards without their own fixture entry. QEMU frame/input coordinates remain
physical framebuffer coordinates; the host does not repeat the guest rotation.
Core2 uses the separately pinned `core2_boot.py` as `boot.py`, retaining its
firmware-owned console. S3 UART setup must not be inherited by Core2: that
exact firmware rejects reinitializing UART0 before `main.py` runs. Every boot
source and console route is pinned per fixture. A board that renders or boots
without the same guest's serial markers has not passed the acceptance gate;
changing the console setup requires a new composition and browser run.

## Board-specific source and input paths

| Device | Guest `main.py` source | Display and exercised input |
| --- | --- | --- |
| StopWatch | `stopwatch_main.py` | SDK logical 468x468, QEMU visible 466x466; screen touch; circular-safe marker `(120,88,8,8)` |
| StamPLC | `main.py` | 240x135 at guest rotation 1; original `M5.BtnA` |
| StackChan | `main.py` | 320x240 at guest rotation 1; screen `M5.Touch`, separate from the Si12T body-touch path |
| PaperColor | `papercolor_main.py` | 400x600; Spectra 6 EPD and front `M5.BtnA` |
| PaperMono | `papermono_main.py` | 480x800; SSD1677 four-gray EPD and `M5.Touch.getTouchPointRaw(0)` hitbox workaround |
| Cardputer-ADV | `cardputer_adv_main.py` | 240x135 at guest rotation 1; original `hardware.KeyboardI2C` over guest I2C/TCA8418 FIFO |

The EPD fixtures use the exposed `isEPD()`, `setEpdMode(EPDMode.EPD_QUALITY)`
and `getEpdMode()` APIs. One `startWrite()`/`endWrite()` transaction encloses
each complete page; the original EPD driver displays at the outermost
`endWrite()`. No unexposed Python `display()` call or host-generated frame is
substituted. Refresh duration is guest virtual time, not a physical waveform
or wall-clock latency measurement. Other modes and partial refresh need their
own tests. PaperMono accepts only `80 <= x < 400` and `600 <= y < 700`;
the candidate oracle exercises `(240,650)` and a rejected `(240,400)` touch.

PaperMono uses the official raw-point getter after the original `M5.update()`
and `M5.Touch.getCount()` path. Its `(x, y, size, id)` tuple supplies the hitbox
coordinates; the original logical `getX()`/`getY()` values are still emitted.
The same guest reports raw `(240,650,1,0)` but logical `(90,400)` for the
accepted input, so stock logical-coordinate calibration remains a known SDK
gap. The rejected input is raw `(240,400,1,0)`. This fixture covers those
single-touch inputs only. Release events retain the last pressed raw point
and explicitly report `coordinates_cached=true`; they are not new raw reads.

The reviewed `papermono_main.py` is 4,297 bytes, SHA-256
`9ec71a31dfe6ad2d359e48a9bc1bdd9ce5eccb0080271fe819e3cfce109d403e`;
its composed Flash SHA-256 is
`2b7311756055a6b508da9d4717b023149e3d2d1634ae54712aa1786486002f70`.
This raw-point workaround does not establish a stock logical-touch fix or
physical-hardware equivalence. A separate SDK `offset_rotation` change from
0 to 1 has only an extracted-source host C++ calibration proof; no candidate
firmware was rebuilt or run, so it has no firmware or hardware PASS.

Cardputer-ADV creates `KeyboardI2C` in `ASCII_MODE` at address `0x34`, with
SDA8/SCL9 on I2C1 and interrupt pin11. It polls the original driver's IRQ
handler over guest I2C, consumes its decoded events and observes releases
through `is_key_pressed()`. This proves FIFO decoding only when actually run;
it does not establish GPIO interrupt delivery. The candidate keyboard oracle
covers `a`, `z`, `q`, `b`, `n`, `m`, `1`, `0`, Enter, Space and Backspace.
Each key must increment the guest counter and change the real frame; the
separate 8x8 key-state marker must reflect press and release. General Fn or
simultaneous modifier combinations are outside that browser case.

StopWatch's panel address offset is 6 in the official driver and in QEMU's
visible-window origin, so it is not an extra host rotation or an assumed
six-pixel correction. QEMU also masks the circular glass. Logical dimensions,
actual surface dimensions and marker coordinates are checked independently;
the cropped edge and original-driver touch coordinates must be recorded.
Touch counts alone do not establish coordinate calibration, and the driver
raw range must not be converted by an assumed factor of two.

`composeQemuProbeFirmware` uses the separately source-built LittleFS WASM.
It parses exactly one unencrypted `vfs` partition before mounting, never
formats, writes only three reviewed Python paths, remounts and reads them
back, and requires the complete resulting Flash hash to match the independently
verified Python `uiflow_source` composition. That independent composition
verifies every pre-existing file and all bytes outside the VFS.

Rebuild and run packaging verification with explicit, locally obtained inputs:

```sh
python3 scripts/browser-littlefs/build.py --emcc /path/to/emcc \
  --output .work/browser-littlefs-wallclock-v1
node platform/tests/test_public_qemu_probe_firmware.mjs \
  --runtime .work/browser-littlefs-wallclock-v1 \
  --base /path/to/hash-matching-official-base.bin --device atoms3r \
  --out-dir .work/atoms3r-composition
```

This command executes only LittleFS in Chromium; it does not execute a guest.
Real board acceptance must additionally use an explicit candidate static
export, load the composed image, inspect nonempty native frame pixels,
exercise input press/release and guest counter changes, and record clean stop
and Worker/iframe disposal. Candidate metadata and packaging success never
grant public browser admission.

The LCD/OLED oracle requires the full native 8x8 red marker to change to green
at the same pixel locations, with no old red pixels remaining. The EPD oracle
instead checks each pixel against the fixed driver-generated QUALITY pattern
for its palette, 16x16 marker and 30x30 count bit. Both record the actual frame
source and marker coordinates. AtomS3R has an
observed +2 physical-row offset; functional input/frame acceptance leaves
that display-coordinate calibration boundary open. Public admission, when
granted with matching guest evidence, covers the recorded firmware and input
path rather than complete pixel calibration or all board peripherals.

The EPD patterns are declared in
[`browser_epd_quality_oracles.json`](../../../platform/tests/fixtures/browser_epd_quality_oracles.json).
They bind the two guest source hashes, rotation, official source hashes and
exact per-pixel `primary + exceptions` rules. PaperMono's gray inputs use the
original four-level Bayer conversion; PaperColor's QUALITY pair quantizer can
produce green pixels within an input-black region. Uniform source colors
therefore do not imply uniform controller pixels. Histograms supplement the
spatial pattern; they do not allow arbitrary pixel substitutions. Recompute
the source-derived expectation with the standalone stdlib tool:

```sh
python3 tests/browser-qemu/board_display/epd_oracle.py --check
```

This calculation is not guest execution or hardware evidence. Browser
acceptance must still bind the fixture and oracle identities, verify the
actual controller frame and input transitions, and retain a clean exit.
The separate counter-text ROI change check does not prove exact numeral
glyphs.

## Fixed official API sources

The new fixtures target UIFlow2 2.5.3, tag commit
[`50e440780492aa847378c7d3477ab912f7063bac`](https://github.com/m5stack/uiflow-micropython/tree/50e440780492aa847378c7d3477ab912f7063bac).
Its M5Unified submodule is `8530f5377d782e4a25a6c482de2e71c3f75ca8eb`
and M5GFX submodule is `9bcedf4e19d4cab7a0793de0598ae5390b4689fe`.
Relevant sources are the fixed
[M5GFX board configuration](https://github.com/m5stack/M5GFX/blob/9bcedf4e19d4cab7a0793de0598ae5390b4689fe/src/M5GFX.cpp),
[EPD transaction API](https://github.com/m5stack/M5GFX/blob/9bcedf4e19d4cab7a0793de0598ae5390b4689fe/src/lgfx/v1/LGFXBase.hpp#L137-L147)
and [KeyboardI2C decoder/matrix](https://github.com/m5stack/uiflow-micropython/blob/50e440780492aa847378c7d3477ab912f7063bac/m5stack/libs/hardware/keyboard/__init__.py).
PaperMono's raw API is pinned to the tag's
[Python binding](https://github.com/m5stack/uiflow-micropython/blob/50e440780492aa847378c7d3477ab912f7063bac/m5stack/components/M5Unified/mpy_m5touch.cpp#L61-L79)
and [Touch type registration](https://github.com/m5stack/uiflow-micropython/blob/50e440780492aa847378c7d3477ab912f7063bac/m5stack/cmodules/m5unified/m5unified_touch.c#L14-L21).
The binding returns `(x, y, size, id)` with index 0 by default.
[M5Unified's raw getter](https://github.com/m5stack/M5Unified/blob/8530f5377d782e4a25a6c482de2e71c3f75ca8eb/src/utility/Touch_Class.hpp#L102)
reads `_touch_raw`, which the
[original update path](https://github.com/m5stack/M5Unified/blob/8530f5377d782e4a25a6c482de2e71c3f75ca8eb/src/utility/Touch_Class.cpp#L23-L31)
fills before converting a copy to logical coordinates. The pinned
[FT5x06 driver](https://github.com/m5stack/M5GFX/blob/9bcedf4e19d4cab7a0793de0598ae5390b4689fe/src/lgfx/v1/touch/Touch_FT5x06.cpp#L139-L172)
reads the original I2C point registers and sets `size=1`.
The bundled official `uiflow2-coder` display, button and touch references and
existing device-local probes were also checked. Firmware bytes, source pins
and test inputs remain authoritative in the profile registry; these source
references and a packaging result do not grant browser admission.
