# Native Core2 crash diagnostics

This ESP-IDF probe starts a task pinned to CPU1. The default build calls
`abort()`. With `CRASH_PROBE_WATCHDOG=ON` the task stops servicing the tick so
the normal interrupt watchdog reports its panic. Both builds emit the SDK UART
core-dump stream and halt after printing it.

Build with ESP-IDF v5.5.4 at `735507283d5b2f9fb363a1901172dbd9e847945d`. Run
`idf.py build` from this directory. For the watchdog build use a separate
`-B` path and `-DSDKCONFIG` path with `-DCRASH_PROBE_WATCHDOG=ON`. Merge the
listed bootloader, partition table and app using `flash_args` plus
`--fill-flash-size 16MB`. Keep each build's application ELF.

Start an owned Device Service on an isolated port and state directory with the
pinned native runtime and ROMs. Upload the merged artifact and both ELF files.
Register the image as a Core2 merged firmware and create a `runtime=qemu`
session. Wait for `CRASH_PROBE_ARMED cpu=1` and `CORE DUMP END` in serial.
Read `/api/v1/sessions/{id}/crash` without an ELF, with the matching ELF
artifact ID, and with the other build's ELF artifact ID. The watchdog
variant must report both tagged register PCs. The abort variant must report
its explicit call site and backtrace without a register PC claim. Both
matching ELF requests should resolve `trigger_fault`.

Request a ZIP with `include=serial,logs,crash&elf_artifact_id=<matching-id>`
before stopping. Check the receipt's console-offset SHA-256 against the
archived serial. Stop the guest with `purge=0&retain_flash=0` and check that
the process and lease are released. The two guests produce a complete
UART transfer marker. The service records that marker and raw data; it does
not validate the dump's internal CRC or reconstruct task state.

[Bounded virtual-device evidence](summary.json).

## Offline FreeRTOS task report

Run locally on macOS with trusted Espressif `esp-coredump` 1.17.2 and Xtensa
`xtensa-esp32-elf-gdb`. Provide the matching ELF used to generate the ZIP and
the exact full-size merged image registered for the session.

```sh
python3 platform/tools/decode_esp32_coredump.py \
  --evidence evidence.zip --firmware merged.bin --elf m5_crash_diagnostics.elf \
  --decoder /path/to/esp-coredump --gdb /path/to/xtensa-esp32-elf-gdb
```

The CLI checks the manifest and receipt digests, selects a single UART dump
following the reported panic, validates its CRC32 and Xtensa application ELF
note, then verifies the full application ELF digest against the merged image.
The vendor decoder runs in a network-denied macOS sandbox with writes limited
to a temporary directory. The report includes task names, priority, stack
usage and the crashed task. Keep it local if task names contain private data.

[Watchdog and abort results](offline-task-summary.json) cover Core2 native QEMU
with ESP-IDF 5.5.4 and the ELF CRC32 UART format `0x0102`. Other formats,
RISC-V, live inspection, and HTTP task decoding remain outside this CLI.
