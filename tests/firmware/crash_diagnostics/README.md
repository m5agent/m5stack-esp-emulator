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
the process and lease are released. Both guests produce a complete UART transfer. Check that
`core_dump.decoding` reports its CRC32, saved task contexts and crashed
task handle. The watchdog fixture has five contexts. The abort fixture
has six. Matching ELF requests resolve the saved crashed-task PC to
`trigger_fault` and `panic_abort`, respectively. The original UART panic
symbols remain separate from these saved task PCs. With a wrong or absent
ELF the service still reports the checked contexts without task PC symbols.
[Bounded session task contexts](session-task-context-summary.json) records
both results and stop/restart readback.

[Bounded virtual-device evidence](summary.json).

## Retained stock application-loading observations

[The bounded stock replay](stock-boot-loading-summary.json) uses immutable ZIPs
from ordinary 98TAB5, CarPlay and M5TabOS virtual-device starts. It does not run
these firmware images again or trigger a fault. The new parser preserves all
previous observations and additionally records bootloader application loads:
98TAB5 has 32 loads at `0x10000` (last 16 retained, boot ordinals 17–32),
CarPlay has one and M5TabOS has seven. Counts apply to each captured console
window. The same ZIP member hashes bind the old and new parser outputs.

Copies of the already stopped 98TAB5 and CarPlay session directories were
opened by an isolated Device Service. Only GET routes were used: session,
serial, crash, evidence and worker state. HTTP receipts and newly generated
ZIP receipts agree exactly; their serial bytes match the original ZIPs.
Both sessions remained stopped, with zero leases and no new guest processes.
The CarPlay persisted frame remains byte-identical. M5TabOS had only its
original ZIP replayed; its HTTP replay is **NOT RUN**.

Recheck an original archive without starting a guest:

```sh
PYTHONPATH=platform/tools python3 - /path/to/evidence.zip <<'PY'
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import json, sys
from device_service_crash import crash_console_observations
with ZipFile(sys.argv[1]) as archive:
    manifest = json.loads(archive.read("manifest.json"))
    serial = archive.read("serial.log")
    assert sha256(serial).hexdigest() == manifest["files"]["serial.log"]["sha256"]
    stderr = archive.read("qemu.stderr").decode("utf-8", errors="replace")
    source, observed = crash_console_observations(Path("unused"), stderr, serial)
print(json.dumps({"source": source, "boot": observed["boot"]}, indent=2))
PY
```

An application-load report is not readiness or an explanation of a reset.
98TAB5 still has repeated software resets and no complete DSI frame in the
retained run. M5TabOS's earlier reset evidence remains open. New boot execution,
physical behavior, external networking and matching-ELF debugging are
**NOT RUN** for this read-only replay.

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
with ESP-IDF 5.5.4 and the ELF CRC32 UART format `0x0102`. Task names, priorities and stack usage are reported by the offline tool.
With the optional `pyelftools` package in the service Python bundle, the
same exact application ELF can also qualify task details in the HTTP and
ZIP receipts. [Bounded API and ZIP results](session-task-metadata-summary.json)
include the exact application artifacts and the offline comparison. For the two fixed probes, the crashed task is
`fixture_fault`, both priorities are 2, and the saved TCB stack reports
1,696 bytes used and 2,396 bytes free. These values come from the saved
pointers and do not measure the minimum remaining stack over time.
Requests without an ELF or with the swapped ELF still get the same saved
PC and SP. A matching ELF with the parser package absent retains the PC/SP
and function symbols and returns `pyelftools_unavailable`.

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

## Cardputer ADV ESP32-S3 UART ELF32 core dump

Build the benign abort fixture with ESP-IDF 5.5.4 as above. In a private
copy of `sdkconfig.defaults`, remove the ESP32 target assignment and select
`CONFIG_ESPTOOLPY_FLASHSIZE_8MB=y`. Select `CONFIG_ESP_COREDUMP_CHECKSUM_CRC32`
or `CONFIG_ESP_COREDUMP_CHECKSUM_SHA256` in separate build directories. Use
`-DIDF_TARGET=esp32s3` and merge the matching `@flash_args` with
`esptool --chip esp32s3 merge_bin --fill-flash-size 8MB`.

Use an owned Device Service with native `runtime=qemu` and
`device_id=cardputer-adv`. Upload each merged image, its own ELF and the
other variant's ELF. After the CPU1 abort and UART dump, inspect
`core_dump.decoding` via the crash endpoint and the same-session ZIP.
On the exact ELF each reading includes five contexts and the named
`fixture_fault` task. Check both priorities and compare the saved stack
distances against `esp-coredump info_corefile` with Xtensa S3 GDB.
Missing and swapped ELFs preserve register-only task contexts.
The separate live-PC endpoint gets two current QEMU CPU PCs.

[Bounded comparison results](s3-uart-task-summary.json) cover both
checksums, the matching app artifacts, equivalent API/ZIP receipts,
and stopped history after an isolated service restart. Other S3 boards
and the diagnostic network lane remain outside this qualification.

## Cardputer ADV ESP32-S3 Flash ELF32 core dump

Use the same ESP-IDF 5.5.4 S3 abort fixture and 8 MiB merge recipe.
In a private copy of the project, replace `CONFIG_PARTITION_TABLE_SINGLE_APP_LARGE`
with `CONFIG_PARTITION_TABLE_CUSTOM=y`, and switch
`CONFIG_ESP_COREDUMP_ENABLE_TO_UART` to `CONFIG_ESP_COREDUMP_ENABLE_TO_FLASH`.
Use this `partitions.csv` with the default custom partition filename:

```csv
nvs,      data, nvs,     , 0x6000,
phy_init, data, phy,     , 0x1000,
factory,  app,  factory, , 1500K,
core_a,   data, coredump,, 384K,
```

Build CRC32 and SHA-256 in separate directories. Register each merged BIN
through an owned native Cardputer ADV Device Service. Wait for the CPU1 abort
and the SDK's `Core dump has been saved to flash.` line. Request
`/crash` and the same-session `/evidence?include=crash` before stopping,
with and without the matching ELF ID. The receipt reports `virtual_flash`,
the partition offset and digest, and five saved task contexts. The wrong ELF
must also return the same raw contexts and withhold names and symbols.
The ZIP contains the decoded receipt without the binary range. To verify
against Espressif independently in the owned fixture, use the offset and size
from the receipt to extract the range from `/flash?format=bin`. Verify the
range SHA-256 and pass it with the matching application ELF and S3 GDB to
`esp-coredump info_corefile --core-format raw --core dump.bin`.

With a runtime ACL that allows only `serial.read`, confirm that Flash decoding
reports `flash_read_denied` and panic symbolization still works. Default stop
releases Flash and a later read reports `flash_unavailable`. For a stopped
read, send `{"purge":false,"retain_flash":true}` to the stop endpoint.
[Bounded virtual-device results](s3-flash-task-summary.json).

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
