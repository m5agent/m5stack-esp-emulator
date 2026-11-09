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
