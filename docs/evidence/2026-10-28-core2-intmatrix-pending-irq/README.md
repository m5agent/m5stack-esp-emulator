# Core2 pending SPI IRQ remap

Date: `2026-10-28`

Validation: `virtual-device validation`

Hardware validation: `NOT RUN`

## Result

Patch `0064` fixes a classic ESP32 interrupt-matrix defect that could lose a
pending level interrupt when the guest changed its source mapping.

The same ESP-IDF 5.5.4 Core2 firmware and ELF were exercised before and after
the patch:

- pre-fix QEMU `03ae86b5…`: SPI queue completed setup, but the guest callback
  timed out and no queued result was returned;
- fixed QEMU `22bf9dba…`: three independent runs passed, each with one guest
  `post_cb` and one `spi_device_get_trans_result()` completion.

The fixed runtime also passed the Core2 UIFlow2 device group `6/6` with one
attempt per case and no retry:

- FT5x06-compatible touch, PCF8563 RTC and PWR;
- ESP32 I2S speaker and microphone;
- INA3221 power monitor;
- MPU6886 IMU;
- AXP192 power path.

## Root cause

The guest allocates SPI3 to a CPU interrupt, raises
`SPI_SLAVE.TRANS_DONE` with `TRANS_INTEN=1`, and writes the final
interrupt-matrix mapping while the source level is already high. The old
matrix model forwarded only input level edges. A mapping write therefore did
not recompute the CPU interrupt output, leaving the SPI ISR pending forever.

`0064` retains all 69 source levels, recomputes each CPU output from all
mapped sources, and applies the same recomputation on input or mapping
changes. Multiple inputs mapped to one CPU interrupt are ORed. The patch also
models `SPI_SLAVE.TRANS_DONE/TRANS_INTEN` state and drives the SPI line as
their logical AND.

## Reproduction

Build and run:

```bash
source .work/esp-idf-v5.5.4/export.sh
idf.py -C tests/firmware/core2_spi_irq_remap \
  -B .work/core2-spi-irq-remap-build build
python -m esptool --chip esp32 merge_bin \
  --flash_mode dio --flash_freq 40m --flash_size 16MB \
  --fill-flash-size 16MB \
  -o .work/core2-spi-irq-remap-16m.bin \
  0x1000 .work/core2-spi-irq-remap-build/bootloader/bootloader.bin \
  0x8000 .work/core2-spi-irq-remap-build/partition_table/partition-table.bin \
  0x10000 .work/core2-spi-irq-remap-build/core2_spi_irq_remap.bin

python3 tests/firmware/core2_spi_irq_remap/run_test.py \
  --image .work/core2-spi-irq-remap-16m.bin \
  --elf .work/core2-spi-irq-remap-build/core2_spi_irq_remap.elf \
  --attempts 3 \
  --out-dir /tmp/core2-spi-irq-remap
```

## Artifacts

- firmware:
  `1f4d1b405425f093c40459e31e3e3c643e4ac49ccd529b9018a7dc346470faf9`
- ELF:
  `00d946fe3f6ca6a5bf431a609afa32beb8c71fc4ea753baa9e6920cb4ed3387d`
- fixed QEMU:
  `22bf9dba026ccb8a2d5f483de5917eb56433610d97709abe29122c49358d3d67`
- pre-fix QEMU:
  `03ae86b5ce2d2029bf68a1b0e9c89153447217a02938a556ea292066b222afaf`

Machine-readable fixed and control evidence is under
[`tests/firmware/core2_spi_irq_remap/`](../../../tests/firmware/core2_spi_irq_remap/).

## Boundary

This is virtual-device validation. The patch proves pending SPI level
delivery through the guest interrupt/queue path. It does not establish
physical ESP32 timing or electrical behavior, and it does not close legacy
UIFlow `RUNTIME-03`. The latest legacy `UIFlow_Core2 v1.15.4` trace still
resets or stops before display completion and still has no non-empty
application frame.
