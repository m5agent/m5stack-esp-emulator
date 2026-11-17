# Native ESP32-C6 crash symbols

This benign probe on Nesso N1 prints a readiness marker and calls `abort()`
from a named function. ESP-IDF prints the abort call site and the Core 0
`MEPC` register, then halts. The binary, variant, merged Flash and ELF must
belong to the same build.

Build with ESP-IDF v5.5.4 at `735507283d5b2f9fb363a1901172dbd9e847945d`.
Use an absolute build path and SDKCONFIG path. From this directory run

```sh
idf.py -B "$BUILD_DIR" -DSDKCONFIG="$BUILD_DIR/sdkconfig" -DIDF_TARGET=esp32c6 build
cd "$BUILD_DIR"
python -m esptool --chip esp32c6 merge_bin --fill-flash-size 16MB -o merged.bin @flash_args
```

Start an isolated Device Service with native C6 QEMU and matching ROM.
Upload `merged.bin`, the exact application ELF, and a different C6 build's
ELF. Register the merged firmware for `nesso-n1` and create a native
`runtime=qemu` session. Confirm `RISCV_C6_CRASH_PROBE_BOOT`,
`RISCV_C6_CRASH_PROBE_ARMED`, and the guest's abort and MEPC lines.

Read `/api/v1/sessions/{id}/crash` with `elf_artifact_id` referencing the
matching ELF. Compare the full app descriptor digest, panic prefix and
uploaded artifact hash. The matching report should identify both the guest
abort site and `MEPC`, with symbol names consistent with
`riscv32-esp-elf-addr2line -f -e m5_riscv_c6_crash.elf <pc>`.
Repeat without an ELF and with the other ELF. Both receipts should contain
no decoded addresses.

Download the same-session ZIP with
`include=serial,logs,crash&elf_artifact_id=<matching-elf-digest>`. Check the
archive integrity and match its crash receipt and bounded serial digest.
Stop with `purge=0&retain_flash=0`. Check the retained crash receipt,
released Flash, and absence of an active process or lease.

[Bounded virtual-device results](summary.json) record the unchanged-
artifact baseline and candidate. The probe qualifies little-endian RISC-V
ELF32 ILP32 soft-float executable symbols on native ESP32-C6. Stack memory
printed by the panic handler is not unwound by the service.

## Live native C6 PC

Use the same owned service and `nesso-n1` `runtime=qemu` session. After the
abort marker appears, GET `/api/v1/sessions/{id}/crash/cpu-pc`. Confirm
`Cache-Control: no-store`, the same session and Flash SHA-256, `target=riscv32`,
`machine_type=esp32c6-machine`, and `cpu_model=espressif-riscv-cpu`. The
response contains CPU0's current PC and both QEMU run-state checks. Read the
guest-reported `MEPC` independently with the matching ELF as above. Save the
live response beside the same-session ZIP.

For the pause check, register the existing benign MWDT fixture with the
source SHA-256 in the [live receipt](live-cpu-pc-summary.json). Wait for
`MWDT_PROBE_READY` and sample while running. Use only the owned private QMP
test harness to pause before taking two samples. Confirm identical PCs and
`paused` across both reads, then resume from the harness and sample again.
The HTTP handler only issues `query-status`, `query-cpus-fast`, fixed QOM
type reads and `info registers -a`. Stop with `purge=0&retain_flash=0`, verify
Flash and lease release, then require HTTP `409 session_not_running`.

The receipt also covers a post-ROM sample of the original Meshtastic RFID
Demo image and a two-core native Core2 watchdog regression. RFID application
functionality, other RISC-V runtimes, browser WASM and physical hardware are
`NOT RUN` for these checks.

## ELF32 UART core dump

Build and merge the same probe with the CRC32 or SHA-256 UART option. Run the
following from the fixture directory, using a different build and sdkconfig for
each selection.

```sh
kind=crc32
idf.py -B "$BUILD_DIR" -DSDKCONFIG="$BUILD_DIR/sdkconfig" \
  "-DSDKCONFIG_DEFAULTS=$PWD/sdkconfig.defaults;$PWD/sdkconfig.coredump-$kind" \
  -DIDF_TARGET=esp32c6 build
(cd "$BUILD_DIR" && python -m esptool --chip esp32c6 merge_bin \
  --fill-flash-size 16MB -o merged.bin @flash_args)
```

Repeat with `kind=sha256`. Use the same isolated Nesso N1 service flow.
Wait for `CORE DUMP END` on the default UART. Confirm the receipt's format,
embedded checksum, full dump SHA-256 and the three saved contexts. The matching
ELF resolves the crashed PC to `panic_abort`. Compare the reported PC/SP
and task count with the same emitted ELF dump loaded in RISC-V GDB. Both an
absent ELF and the other build's ELF leave the contexts available without
task symbols. Check equality between the live receipt and its ZIP, then stop
and restart the isolated service and read the retained receipt again.

[Same-session CRC32 and SHA-256 evidence](session-core-dump-summary.json)

This path reports saved task contexts. It does not unwind the RISC-V stack or
recover task names or priorities. The two tested builds use the same abort
probe and ESP-IDF version.


## Nesso N1 RV32 FreeRTOS task metadata

Use the same two fixed native UART probe builds and their own matching
application ELF. Include the optional `pyelftools` package in the Device
Service Python environment. After the completed UART transfer, read the
existing crash endpoint with each probe's owning ELF, no ELF, and the
other ELF. The matching receipt reports names, priorities and saved stack
distances for all three tasks. Compare the matching receipt to the same
session's diagnostic ZIP and to `esp-coredump info_corefile` with the
Espressif RV32 GDB. The crashed `main` task has priority 1/1 and saved stack
distances of 288 bytes used and 3,804 bytes free for both builds. Retain the
session history and recheck after stopping and restarting the service.

[Scoped evidence](session-task-metadata-summary.json) records the
same-artifact comparison. The metadata lookup exercises native
`nesso-n1` and the two existing ELF32 UART integrity options. Other
native ESP32-C6 boards keep the existing register-only task contexts.

## Nesso N1 saved RV32 task backtraces

Use the same two native UART probes and matching application ELFs as for
task metadata. Read the retained API or same-session ZIP after the UART
transfer. On a supported matched ELF the captured task rows may include
`saved_backtrace`, with saved PC/SP pairs and an explicit termination reason.
The lookup is limited to unaugmented RV32 ELF32 `.debug_frame` rules with an
SP-relative canonical frame address. It reads return words from the
SDK-emitted stack segment paired to that task's TCB. The first frame may use
the saved link register. It follows at most 16 frames and stops on unsupported,
ambiguous or missing evidence. An explicit undefined return register marks
the completed end of a chain.

Run Espressif RV32 GDB with the same application ELF and ELF body from the
validated UART dump. With executable auto-loading disabled, use
`thread apply all bt 17`. Compare each frame's `$pc` and `$sp` with the
matching task in the receipt. The fixed CRC32 and SHA-256 probes each yield
seven `main`, four `IDLE` and five `esp_timer` frames. A mismatched or
absent application ELF retains the same saved top-level registers.
Repeat the read after stopping the guest and restarting its service.

[Scoped evidence](session-saved-backtrace-summary.json) covers the native
Nesso N1 UART formats and both oracle comparisons. Flash dumps, other
RISC-V targets and arbitrary DWARF expressions stay outside this scope.
