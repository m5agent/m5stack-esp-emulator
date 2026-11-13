# Core2 SPI SD read/write regression

This checked-in virtual-device regression uses the original UIFlow2 SDCard
API through classic ESP32 GP-SPI, DMA descriptors and the board SD model.
Core2 wires SCK/MOSI/MISO/CS to GPIO18/23/38/4. `slot=2` selects VSPI in the
bundled UIFlow2 driver; it shares the physical bus with the display.

Prerequisites: the pinned Core2 UIFlow2 image in the firmware cache, a native
Xtensa runtime containing patch 0192, ESP32 ROMs and the repository Python
image/Flash dependencies. Supply explicit runtime and ROM paths:

```sh
M5_QEMU_XTENSA="$qemu_binary" M5_QEMU_XTENSA_ROM_DIR="$rom_directory" \
  PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --case core2-sd --out-dir "$ignored_output"
```

The runner creates an isolated raw SD image. The guest writes sector 100 with
512 bytes of `(index * 7 + 0x31) & 255`, reads it back and compares every byte.
The independent host oracle also compares that sector to the expected pattern;
serial PASS markers and a green display bar must agree. No Python-level SD
emulation or direct buffer injection is used. This does not measure physical
card timing, signal integrity or endurance.

The initial slot=3 and missing RX-DMA controls fail; their records are retained
in the classic SPI SD evidence. Application testing uses dedicated Device
Service sessions instead of this direct regression runner.
