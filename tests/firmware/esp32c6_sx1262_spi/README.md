# Nesso SX1262 shared hardware/GPIO SPI regression

This ESP-IDF 5.5.4 probe uses the public SPI master and GPIO drivers. It reads
the radio identity through SPI2, repeats the read as one-byte controller
transactions under a single chip select (the original RadioLib path), checks
packet-type configuration, then writes adjacent LoRa sync-word registers.
After releasing the SPI controller it reads those same bytes through GPIO SPI,
checking that both interfaces access one radio state.

Board wiring is SCK 20, MOSI 21, MISO 22 and CS 23. The independent identity
oracle is [RadioLib 7.6.0 SX1262.h](https://github.com/jgromes/RadioLib/blob/7.6.0/src/modules/SX126x/SX1262.h):
SX1262 silicon identifies as `SX1261` in the version register. The version is
returned by the modeled device's real SPI register read path. The firmware is
not patched, and no host API injects guest read results.

With ESP-IDF 5.5.4 activated:

```sh
idf.py -C tests/firmware/esp32c6_sx1262_spi -B .work/c6-radio-probe build
python -m esptool --chip esp32c6 merge_bin -o .work/c6-radio-probe/merged.bin \
  0x0 .work/c6-radio-probe/bootloader/bootloader.bin \
  0x8000 .work/c6-radio-probe/partition_table/partition-table.bin \
  0x10000 .work/c6-radio-probe/c6_sx1262_spi_probe.bin
```

Upload to a dedicated Device Service `nesso-n1`, `runtime=qemu` session with
`ready_marker=C6_SX1262_READY`. Require `ID_PASS`, `SPLIT_PASS`,
`PACKET_TYPE_PASS`, `HW_BURST_PASS`, `SHARED_STATE_PASS` with the
`C6_SX1262_` prefix, plus ready and no FAIL/panic. Collect its evidence ZIP
before stop with `purge=0`.

Negative runtime: C6 recipe through `0009-c6-qio-flash-header.patch`.
Candidate: adds `0010-c6-sx1262-hardware-spi.patch`. Also run the checked-in
`nesso-lora` UIFlow2 case to preserve the existing GPIO SPI loopback path.

[The dated evidence](evidence-2026-11-13.json) records the paired negative and
positive probe, the unchanged QIO regressions, and the original Meshtastic
command stream. Meshtastic's radio object survives initialization after the
fix, but a later TG0 watchdog still resets that application. Full Meshtastic
readiness remains FAIL.

Scope: virtual-device controller, chip-selection, register and shared-state
behavior. RF propagation, physical timing, RF power and interoperability with
an over-the-air Meshtastic network are NOT RUN.
