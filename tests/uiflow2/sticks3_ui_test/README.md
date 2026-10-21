# StickS3 UIFlow2 Local UI Test

Status: **WIP**. The test reaches UIFlow2 `main.py`, `M5.begin()` returns
success and M5GFX reports board 26 (`board_M5StickS3`), but the ST7789 panel
first frame is still black. The remaining blocker is the QEMU SPI panel
command/data/DC/MISO path.

## Why eFuse is needed

M5GFX selects the S3 autodetect branch from eFuse `PKG_VERSION`:

- QFN56 / StopWatch: `PKG_VERSION=0`
- PICO/LGA56 / StickS3: `PKG_VERSION=1`

The QEMU eFuse image generated here sets the ESP32-S3 `PKG_VERSION`
field in BLOCK1 to `1`:

```text
BLOCK1 word 3, bit 21 = 1
```

Without it, StickS3 firmware enters the QFN56 StopWatch/PaperMono probe branch.

## Build image

```bash
python3 -m pip install littlefs-python
python3 tests/uiflow2/sticks3_ui_test/make_image.py \
  --base /path/to/StickS3-8MiB.bin \
  --out /tmp/sticks3-ui-test.bin \
  --efuse-out /tmp/sticks3-efuse.bin
```

For the official 8 MiB image, use:

```bash
--vfs-offset 0x641000 --vfs-size 0x1BE000
```

## QEMU

```bash
qemu-system-xtensa -M m5sticks3 \
  -drive file=/tmp/sticks3-ui-test.bin,if=mtd,format=raw \
  -drive if=none,id=efuse,file=/tmp/sticks3-efuse.bin,format=raw \
  -global driver=nvram.esp32s3.efuse,property=drive,value=efuse \
  -L bin/Darwin-arm64 -display none
```

Expected serial markers:

```text
STICKS3_BOOT_FLAG
STICKS3_MAIN_START
STICKS3_M5_BEGIN_OK
STICKS3_BOARD 26
```

## Boundary

This is a StickS3-specific local test. It does not yet validate the first
frame, A/B button redraw, or touch (StickS3 has no touch panel).
