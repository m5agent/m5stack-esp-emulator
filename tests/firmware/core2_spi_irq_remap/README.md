# Core2 pending SPI IRQ remap

Status: independent SPI/INTMATRIX defect `FIXED`; legacy UIFlow
`RUNTIME-03` remains `OPEN`.

This ESP-IDF 5.5.4 probe queues a 16-byte SPI3 transaction through
`spi_master`, then requires both the guest `post_cb` and
`spi_device_get_trans_result()` to complete.

## Root cause

The guest temporarily allocates the SPI3 source to CPU interrupt 5, clears
the mapping to the QEMU "unconnected" value, raises
`SPI_SLAVE.TRANS_DONE` with `TRANS_INTEN=1`, and finally writes the mapping
back to 5.

The old interrupt-matrix model forwarded a source only when its input level
changed. Writing the mapping while that source was already high did not
re-evaluate the pending level, so the SPI ISR never ran.

`0064-esp32-intmatrix-pending-irq-remap.patch`:

- stores each of the 69 matrix input levels;
- recomputes each CPU external-interrupt output from all mapped inputs;
- recomputes outputs whenever either an input level or a mapping changes;
- models `SPI_SLAVE.TRANS_DONE` and `TRANS_INTEN` as stored state and drives
  the SPI IRQ as their logical AND.

The output recomputation also ORs multiple inputs mapped to the same CPU
interrupt instead of letting the last input unconditionally overwrite it.

## Evidence

The same final firmware and ELF were run before and after the patch:

- Pre-fix QEMU `03ae86b5…`: queue observed, callback timeout, `FAIL`;
- Fixed QEMU `22bf9dba…`: `3/3 PASS`, one callback and one result per run.

Artifact-bound results are in
[`evidence-2026-10-28-core2-spi-irq-remap.json`](evidence-2026-10-28-core2-spi-irq-remap.json)
and the matching negative control is in
[`evidence-2026-10-28-core2-spi-irq-remap-control.json`](evidence-2026-10-28-core2-spi-irq-remap-control.json).

## Build

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
```

## Run

```bash
python3 tests/firmware/core2_spi_irq_remap/run_test.py \
  --image .work/core2-spi-irq-remap-16m.bin \
  --elf .work/core2-spi-irq-remap-build/core2_spi_irq_remap.elf \
  --attempts 3 \
  --out-dir /tmp/core2-spi-irq-remap
```

## Boundary

This is virtual-device validation. It proves the guest SPI completion and
interrupt-matrix path. It does not prove physical ESP32 timing, electrical
behavior or a successful legacy UIFlow application boot.
