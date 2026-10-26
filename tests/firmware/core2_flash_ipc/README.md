# Core2 flash/IPC and interrupt-WDT diagnostic

Status: `FIRST-BOOT CCOMPARE TIMER FIXED / LEGACY UIFLOW STILL OPEN`

This ESP-IDF 5.5.4 probe creates a CPU1 worker that is intended to call
`esp_partition_read()` repeatedly while the CPU0 application task waits for it.
The probe isolates the Core2 legacy-UIFlow flash-cache, cross-core IPC and
interrupt-WDT failure with a small image instead of a vendor firmware address.

It does not inject flash data, bypass a lock or patch firmware code. The read
buffer is static aligned internal RAM, and the worker yields every 50
iterations so the task stack and IDLE1 are not deliberately starved.

## Current observation

The corrected probe reaches `CORE2_FLASH_IPC_READ_START` and completes all
1000 reads in every attempt with the equal-deadline timer patch:

```text
CORE2_FLASH_IPC_MAIN core=0 prid=0x0000cdcd
CORE2_FLASH_IPC_READY core=1 prid=0x0000abab
CORE2_FLASH_IPC_READ_START core=1
CORE2_FLASH_IPC_PROGRESS core=1 iteration=50
...
CORE2_FLASH_IPC_PASS
```

The previous QEMU build computed `2^32` ticks whenever an ISR wrote
`CCOMPARE == CCOUNT`. IRQ-ring evidence captured that exact equal window
immediately before interrupt-WDT. The business-only fix is
[`0034-xtensa-ccompare-equal-deadline.patch`](../../../patches/qemu-m5stack-peripherals/0034-xtensa-ccompare-equal-deadline.patch):
an equal deadline is armed for the next cycle, while every other 32-bit delta
retains the old wraparound interpretation.

After the fix, four artifact-bound batches completed `40/40` first boots with
zero interrupt-WDT or spinlock assertions. Three batches used fixed
`icount shift=5`; one used `shift=auto`. Trace-disabled controls passed, so the
result is not caused by ring/trace timing.

The pre-fix control remains useful historical evidence. Across its dated
current and portable runtime batches:

- 20/20 boots reached `READ_START`;
- 14/20 completed all reads;
- 6/20 first boots ended in interrupt-WDT after flash reads had started;
- 0/20 produced a spinlock owner assertion.

The pre-fix interrupt-WDT samples show both CPU0 and CPU1 in the idle
`esp_cpu_wait_for_intr()`/`waiti` path. This moves the remaining question toward
virtual timer/interrupt delivery and host scheduling during or after flash
activity, not toward PRID, spinlock ownership or an isolated S32C1I mismatch.

The equal-deadline fix does **not** close the legacy UIFlow path. The same public
`UIFlow_Core2 v1.15.4` image still resets with `TG1WDT_SYS_RESET` and
`TG0WDT_SYS_RESET`, reports reset CPU `PC=0`, and produces only a black frame.
That remaining failure must be investigated as a separate TG0/TG1 watchdog
feed/clear or service-starvation path.

The pre/post comparison and legacy follow-up are in
[`evidence-2026-10-26-core2-ccompare-equal-deadline.json`](evidence-2026-10-26-core2-ccompare-equal-deadline.json).
The pre-fix run, artifact hashes, symbolization and cross-core/DPORT trace
summary are in
[`evidence-2026-10-26-core2-flash-ipc-wdt.json`](evidence-2026-10-26-core2-flash-ipc-wdt.json).

## Corrected harness failure

An earlier probe revision placed a 4096-byte local array on a 4096-byte task
stack. Its stack overflow corrupted a FreeRTOS queue lock and produced a
`spinlock_release()` owner mismatch before `READ_START`. That observation was a
probe defect, not simulator evidence. The dated evidence file preserves the
invalid image/ELF hashes and the correction. Do not restore the local buffer.

## Build

From an ESP-IDF 5.5.4 shell:

```bash
idf.py -C tests/firmware/core2_flash_ipc \
  -B .work/core2-flash-ipc-build build
```

Merge the bootloader, partition table and application into a 16 MiB image:

```bash
python -m esptool --chip esp32 merge_bin \
  --flash_mode dio --flash_freq 40m --flash_size 16MB \
  --fill-flash-size 16MB \
  -o .work/core2-flash-ipc-16m-final.bin \
  0x1000 .work/core2-flash-ipc-build/bootloader/bootloader.bin \
  0x8000 .work/core2-flash-ipc-build/partition_table/partition-table.bin \
  0x10000 .work/core2-flash-ipc-build/core2_flash_ipc.bin
```

Build output, `sdkconfig`, Flash images and local service state stay under
`.work/` and must not be committed.

## Run

Start the repository Device Service with the matching Core2 QEMU runtime, then:

```bash
python3 tests/firmware/core2_flash_ipc/run_test.py \
  --base-url http://127.0.0.1:8787 \
  --image .work/core2-flash-ipc-16m-final.bin \
  --elf .work/core2-flash-ipc-build/core2_flash_ipc.elf \
  --attempts 3 \
  --out-dir /tmp/m5-core2-flash-ipc
```

The runner uses independent Device Service sessions, captures serial and
evidence, and exits successfully only when every attempt completes all reads.
It also classifies first-boot interrupt-WDT separately from spinlock assertions
and reports a run that entered `READ_START` but did not finish within the
observation window as `INCOMPLETE`, rather than as a firmware failure. The
known image and ELF hashes are the default gate, so an old
`.work/core2-flash-ipc-16m.bin` image fails before upload. Use the explicit
`--expected-image-sha256` and `--expected-elf-sha256` arguments only after an
intentional probe rebuild, then replace the defaults in the same reviewed
change.

## Boundary

This is virtual-device validation. It does not establish physical ESP32 flash
timing, cache behavior, timer delivery, multicore coherence, electrical
behavior or hardware compatibility.
