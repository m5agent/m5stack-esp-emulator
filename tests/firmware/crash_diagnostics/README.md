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

## Live Xtensa CPU PC sample

With the watchdog fixture and an owned native Core2 session, wait for
`CRASH_PROBE_BOOT` and read `GET /api/v1/sessions/{id}/crash/cpu-pc`. Confirm
both vCPU indices, the firmware SHA-256 and `running` on both sides of the
read. In an isolated test harness that owns QMP, pause the VM, take two API
samples and compare their PCs. Both receipts must report `paused` twice.
Resume from the harness and confirm `running`; the HTTP API itself has
no pause or resume control. The latest UART crash receipt must still be
empty at this point.

After the guest interrupt WDT and `CORE DUMP END`, inspect both the new live
sample and the separate panic-time PCs. Save the sample response alongside
the same-session evidence ZIP before stopping. The live endpoint must return
`409 session_not_running` after stop. Verify the ZIP and that the session
process, writable Flash and lease are released. See the
[bounded virtual-device result](live-cpu-pc-summary.json).

The earlier Xtensa-only endpoint returned `409 cpu_pc_not_supported` after
the Nesso N1 MWDT fixture reached its UART readiness marker on native C6. The Espressif RISC-V
`addr2line` tool separately resolved the known `setup()` symbol address
with the app ELF exactly matched to the normalized ESP32-C6 Flash descriptor.
That known address came from the ELF symbol table. The newer native C6 live PC
and same-session panic probes have their own [receipt](riscv_c6/live-cpu-pc-summary.json).

## ESP32-S3 watchdog timing

Prepare a fresh native Xtensa build with `scripts/bootstrap-unit-runtime.py`.
Copy this probe's `CMakeLists.txt`, `main/` and `sdkconfig.defaults` to owned
scratch space. Use ESP-IDF v6.1.1 with `-DIDF_TARGET=esp32s3` and
`-DCRASH_PROBE_WATCHDOG=ON`. Remove the ESP32 target assignment from the
copied defaults and select an 8 MiB flash. From the configured build directory
merge `@flash_args` with `esptool --chip esp32s3 merge-bin --fill-flash-size
8MB -o merged.bin @flash_args`.

Use separate owned Cardputer Device Service instances with the same patched
QEMU, ROM and firmware. Start the tracing instance with host environment
`M5SW_S3_IWDT_TRACE=1`. Wait for `CRASH_PROBE_ARMED cpu=1` and the guest's
CPU1 watchdog panic. Collect `include=serial,logs,crash` before stopping.
The tracing instance emits one `M5_S3_IWDT_STAGE0` line in native stderr
with `schema_version=1`. The default instance produces the same guest panic
without a timing receipt. Both test sessions release Flash and their lease.
Compare the timing payload with `backend_observations` from
`GET /api/v1/sessions/{id}/crash` and the same session's
`diagnostics/crash.json` in the evidence ZIP. The API and ZIP must retain
the same timing payload and the separate guest panic.

`acks` and `last_ack_ns` are indexed by vCPU and alarm target, in that order.
An acknowledgement counts a write that clears a pending raw alarm. It confirms
that the guest reached the acknowledgement, while execution of the later tick
hook is a separate event. `coalesced` counts callbacks that find the raw bit
already set. Feed timestamps and deadlines come from the model's existing
accepted-feed timer arm. An unavailable guest I/O timestamp is `-1`. CPU
register and route snapshots accompany observed WDT matrix assertion.

In ESP-IDF v5.4.1 the S3 FreeRTOS tick uses SYSTIMER. When the interrupt
watchdog checks both cores, CPU1's hook sets the pending tick flag and CPU0
feeds TIMERGROUP1 after seeing that flag.
[Tick selection](https://github.com/espressif/esp-idf/blob/v5.4.1/components/freertos/Kconfig)
· [Watchdog hook](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_system/int_wdt.c)

[Bounded on/off proof](s3-iwdt-timing-summary.json) uses one harmless probe and
one patched native executable. The original NC1020, other backends and
physical hardware were outside these runs.
