# C6 SPI1 QIO Flash readback regression

This ESP-IDF 5.5.4 probe uses `esp_partition_erase_range`,
`esp_partition_write` and `esp_partition_read` through the guest Flash driver,
SPI1 controller and SSI Flash. It writes an independently specified 8192-byte
pattern, enables the ISSI chip driver for the 16 MiB profile, switches the public Flash configuration between DIO and QIO with
`esp_flash_init`, and compares whole and unaligned ranges across controller
FIFO, Flash page and sector boundaries. It also checks QIO erased bytes.

With ESP-IDF 5.5.4 activated:

```sh
idf.py -C tests/firmware/esp32c6_flash_qio -B .work/c6-flash-probe build
python -m esptool --chip esp32c6 merge_bin -o .work/c6-flash-probe/merged.bin \
  0x0 .work/c6-flash-probe/bootloader/bootloader.bin \
  0x8000 .work/c6-flash-probe/partition_table/partition-table.bin \
  0x10000 .work/c6-flash-probe/c6_flash_qio_probe.bin
```

Upload the merged image to a dedicated Device Service and create `runtime=qemu`
sessions for both `nesso-n1` (16 MiB ISSI) and `nanoc6` (4 MiB GigaDevice).
Set `ready_marker=C6_FLASH_READY`. Require the three `C6_FLASH_READ_PASS`
markers (`DIO`, `QIO`, `QIO-erased`), no FAIL/panic, and the ready marker.
Retain same-session serial and evidence ZIP before stop with `purge=0`.

The negative runtime is the C6 recipe through `0008-c6-aes-gdma-wiring.patch`.
The candidate adds `0009-c6-qio-flash-header.patch`. Preserve failures separately;
a build or intake success is not a guest PASS.

The guest configures C6 QIO with 32 address/configuration bits and four dummy
clocks; see ESP-IDF `components/hal/spi_flash_hal_common.inc`. The existing C6
SSI adapter carries four address bytes. Its QIO model header still needs three
bytes for ISSI or five for GigaDevice/Winbond. These are model transfer counts,
not physical timing measurements. The [ISSI IS25LP128 datasheet](https://www.issi.com/WW/pdf/IS25LP128.pdf)
describes the quad-I/O instruction and its six default mode/dummy clocks.

Scope: virtual-device Flash data-plane validation. This does not establish
physical Flash timing, endurance, all SPI modes, browser-WASM support or full
community-application readiness.

[The dated evidence](evidence-2026-11-13.json) binds both negative controls and
both passing models to the identical probe BIN. It also records the unchanged
original Bruce BIN reaching its main menu and remounting after an operator
reset. Meshtastic, RFID and Launcher remain separate acceptance boundaries.
