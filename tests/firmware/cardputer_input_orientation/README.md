# Cardputer-ADV original keyboard and display contract

This bounded Arduino probe uses the unmodified official M5Cardputer
`bf64d3178ab43928fa02365fbe3937cec99716ad` library, M5Unified 0.2.28 and
M5GFX 0.2.35. `M5Cardputer.begin()` selects the board and initializes the native
TCA8418 reader. The loop calls the ordinary `M5Cardputer.update()`; it does not
invoke the private IRQ handler, set its flag, substitute a keyboard state or
poll the controller on the host. Firmware artifacts are not committed.

Real keyboard Enter edges advance rotations 0, 1, 2 and 3. Each rotation draws distinct
red/green/blue/yellow corner markers and then changes only an 8×8 rectangle.
The guest waits between stages; no elapsed-time assumption joins an asynchronous
serial marker to a frame. The latter must not change the controller's orientation. It then returns to
rotation 1 and reports physical key positions, original decoded modifiers,
navigation flags and character bytes. A browser test drives the actual model
keys and focused PC input; no UART input is used to manufacture key events.
RGB888 colors are explicitly `uint32_t`: the pinned M5GFX overload interprets
signed `int32_t` values as RGB565. The original display depth is recorded,
without forcing a test-only depth or COLMOD mode.

Build using PlatformIO 6.1.18 and two compiler jobs:

```sh
pio run -d tests/firmware/cardputer_input_orientation -j 2
```

The observed complete image is 8 MiB, chip ESP32-S3, bootloader at `0`,
partition table at `0x8000`, framework `boot_app0.bin` at `0xe000` and the
application at `0x10000`. Use the framework's matching esptool `merge_bin`
with `--fill-flash-size 8MB`. The exact observed artifact hashes are in
`sources.lock.json`; a rebuild must record its own identities and cannot
inherit a guest PASS. Portable config differences are explicitly recorded.

Run only against an explicit isolated exported site and your actual image:

```sh
M5_PUBLIC_SITE=/path/to/reviewed/export \
M5_CARDPUTER_IMAGE=/path/to/merged.bin \
M5_CARDPUTER_IMAGE_SHA256=<actual-full-image-sha256> \
M5_CARDPUTER_WASM_SHA256=<reviewed-wasm-sha256> \
M5_CARDPUTER_OUT=.work/cardputer-input-display-new-run \
node platform/tests/test_public_qemu_cardputer_input_display.mjs
```

Each output directory must be new. The test records serial, inputs, native
frame markers, model texture binding and normal Worker cleanup before closing
the browser context. The C getter regression independently replays the actual
locked source and retains the old partial-window failure. Host C/build checks
and virtual guest validation are separate; physical hardware is NOT RUN.

Official sources: [M5Cardputer library](https://github.com/m5stack/M5Cardputer/tree/bf64d3178ab43928fa02365fbe3937cec99716ad),
[TCA8418 reader](https://github.com/m5stack/M5Cardputer/blob/bf64d3178ab43928fa02365fbe3937cec99716ad/src/utility/Keyboard/KeyboardReader/TCA8418.cpp),
and [pinned UIFlow2 KeyboardI2C](https://github.com/m5stack/uiflow-micropython/blob/50e440780492aa847378c7d3477ab912f7063bac/m5stack/libs/hardware/keyboard/__init__.py).
