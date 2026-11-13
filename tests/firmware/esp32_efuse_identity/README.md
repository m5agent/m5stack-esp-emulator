# Classic ESP32 eFuse identity probe

This ESP-IDF 5.5.4 application reads the factory field through the actual eFuse
controller, then calls `esp_efuse_mac_get_default` and `esp_read_mac`. It prints
the stored CRC and the result of `esp_rom_efuse_mac_address_crc8`. No guest MAC
is set by the application. The IDF field order and integrity check are defined
in the pinned source (`735507283d5b2f9fb363a1901172dbd9e847945d`):

- `components/efuse/esp32/esp_efuse_table.c` (MAC bytes: BLK0 bits 72,64,56,48,40,32;
  CRC: bits 80..87).
- `components/esp_hw_support/mac_addr.c` (`get_efuse_factory_mac`).

With the ESP-IDF 5.5.4 environment activated:

```sh
idf.py -C tests/firmware/esp32_efuse_identity -B .work/esp32-mac-probe build
python -m esptool --chip esp32 merge-bin --fill-flash-size 4MB \
  -o .work/esp32-mac-probe/merged.bin \
  0x1000 .work/esp32-mac-probe/bootloader/bootloader.bin \
  0x8000 .work/esp32-mac-probe/partition_table/partition-table.bin \
  0x10000 .work/esp32-mac-probe/esp32_mac_identity.bin
```

Upload the same merged BIN through a dedicated Device Service `/api/v1` session
for `atom-lite` and `atom-matrix`, `runtime=qemu`, readiness marker
`MAC_PROBE_READY`. Require all three `MAC_* rc=0` results to agree with
`Session.efuse_identity.mac`, a nonzero locally administered address, and equal
stored/computed CRC. `MAC_PROBE_READY` alone is not a successful test. Retain the
session evidence before stopping with `purge=0`.

For `core2` with no attached eFuse drive, require `efuse_identity.status` to be
`unprovisioned`, reason `efuse_drive_not_attached`; this probe still reads zeros.
The C6 metadata check uses the separate `esp32c6_aes` firmware and the same reason.
Do not report these profiles as provisioned.

Negative controls use the same original probe BIN with diagnostic eFuse fixture
preparation: a zero fixture returns all-zero addresses, while the former
`efuse[4:10] = mac` helper reverses the guest address and omits its CRC, causing
factory read error 265 and station read error -1. The final positive runs use
the normal service fixture preparation with no diagnostic wrapper.

Scope: virtual-device validation of fixture bytes, controller readout, public
ESP-IDF MAC APIs, API metadata and history. No physical hardware, Wi-Fi/RF,
application-display or NVS-calibration validity claim follows from this test.
Dated hashes and bounded outcomes are in [evidence-2026-11-13.json](evidence-2026-11-13.json).
