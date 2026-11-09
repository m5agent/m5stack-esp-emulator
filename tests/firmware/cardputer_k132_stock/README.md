# Cardputer K132 stock firmware through Device Service

Use the original K132 machine `m5cardputer` and the native Xtensa build with
[patch 0169](../../../patches/qemu-m5stack-peripherals/0169-cardputer-k132-board.patch).
Start an isolated Device Service using that executable and its ESP32-S3 ROM
directory. The board profile uses 8 MiB flash, no PSRAM, a stock ESP32-S3 ROM,
a synthetic unprogrammed eFuse file and no radio peer.

Acquire the matching unmodified image from the official release:

- [Cardputer UserDemo V0.9](https://github.com/m5stack/M5Cardputer-UserDemo/releases/tag/V0.9)
- [Cardputer UserDemo V0.8](https://github.com/m5stack/M5Cardputer-UserDemo/releases/tag/V0.8)
- [Cardputer UIFlow2 v2.5.4](https://m5burner-cdn.m5stack.com/community/1/1897200000000000718/2116030814376202242/bin/2116030814376202243.bin)

Run a case with Python 3.12 or later and Pillow in the test environment:

```sh
python3 tests/firmware/cardputer_k132_stock/run_service.py \
  --service "$M5_TEST_SERVICE" --token-file "$M5_TEST_TOKEN_FILE" \
  --case factory-v09 --firmware "$K132_FIRMWARE_BIN" --out-dir "$K132_EVIDENCE_DIR"
```

The runner checks the pinned input hash, starts a private flash lease, captures
the original guest frame, sends the QMP-backed input through the service, and
checks the guest frame and applicable serial marker. The factory cases enter
the launcher through the real GPIO scan. V0.9 also records the Fn indicator
while held and after release. The UIFlow2 stock case observes the G0 transition
from the offline page to the application menu.

Inspect the screenshots for the expected views. Downloaded firmware, PNGs,
session logs and ZIPs stay outside Git. The runner requests the evidence ZIP
before stopping with history retained and mutable flash released.

The board's SPI microSD data, audio, IR, RGB, ADC calibration, USB, networking,
and power sequencing need separate evidence. A filesystem-composed v2.5.4
candidate reached ROM bootloader entry without a nonblank frame. The stock
result is scoped to the unmodified firmware.

## Browser WASM

Build and export the source-locked browser QEMU as described in
[Pages deployment](../../../docs/pages-deployment.md). Select the original
Cardputer with `--qemu-candidate-profile cardputer` while its profile has
candidate status. Use an isolated static export and a fresh output directory
under `.work/`. The runner verifies the exact merged image before uploading
through the Workbench and waits for the corresponding guest pixels in the 3D
model's texture.

```sh
M5_PUBLIC_SITE="$K132_BROWSER_EXPORT" \
M5_QEMU_UPLOAD="$K132_FACTORY_V09_BIN" \
M5_PUBLIC_QEMU_OUT="$PWD/.work/k132-factory-browser" \
node platform/tests/test_public_qemu_cardputer_k132_stock.mjs
```

The factory case presses and releases PC **A** to enter the menu. The released
edge is required by the [stock launcher](https://github.com/m5stack/M5Cardputer-UserDemo/blob/V0.9/main/apps/launcher/port/port.cpp).
A real pointer presses the visible **Fn** key and the guest must draw and clear
its Fn indicator. The launcher oracle checks the stable SCAN tile and exact Fn
glyph regions. The menu animation, RTC and battery bar are outside the oracle.
For the stock UIFlow2 case, set `M5_CARDPUTER_STOCK_CASE=uiflow2-v254`, supply the
unmodified UIFlow2 image, and use a separate output directory. That case checks
the offline badge and the application menu reached through PC **F12** (GPIO0).
Both cases require normal guest exit and zero live CDP Worker targets before
browser closure.
