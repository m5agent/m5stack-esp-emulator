# Core2 flash/IPC and interrupt-WDT diagnostic

Status: `PARTIAL / FLASH READS RUN, FIRST-BOOT STABILITY FAILS`

This ESP-IDF 5.5.4 probe creates a CPU1 worker that is intended to call
`esp_partition_read()` repeatedly while the CPU0 application task waits for it.
The probe exists to isolate the Core2 legacy-UIFlow flash-cache, cross-core IPC
and interrupt-WDT failure with a small image instead of a vendor firmware
address.

It does not inject flash data, bypass a lock or patch firmware code. The read
buffer is static aligned internal RAM, and the worker yields every 50
iterations so the task stack and IDLE1 are not deliberately starved.

## Current observation

The corrected probe reaches `CORE2_FLASH_IPC_READ_START` in every attempt:

```text
CORE2_FLASH_IPC_MAIN core=0 prid=0x0000cdcd
CORE2_FLASH_IPC_READY core=1 prid=0x0000abab
CORE2_FLASH_IPC_READ_START core=1
CORE2_FLASH_IPC_PROGRESS core=1 iteration=50
...
CORE2_FLASH_IPC_PASS
```

A completed run performs all 1000 `esp_partition_read()` calls. Across the
dated current and portable runtime batches:

- 20/20 boots reached `READ_START`;
- 14/20 completed all reads;
- 6/20 first boots ended in interrupt-WDT after flash reads had started;
- 0/20 produced a spinlock owner assertion.

The interrupt-WDT samples show both CPU0 and CPU1 in the idle
`esp_cpu_wait_for_intr()`/`waiti` path. This moves the remaining question toward
virtual timer/interrupt delivery and host scheduling during or after flash
activity, not toward PRID, spinlock ownership or an isolated S32C1I mismatch.

The earlier legacy UIFlow trace remains useful: CPU0 was observed waiting for
the flash-operation start flag while CPU1 repeated the DPORT safe-read path.
The minimal probe now proves the ordinary partition-read path can run, but does
not yet prove that the legacy firmware failure has the same trigger.

The dated run, artifact hashes, symbolization and cross-core/DPORT trace summary
are in
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
  -o .work/core2-flash-ipc-16m.bin \
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
  --image .work/core2-flash-ipc-16m.bin \
  --elf .work/core2-flash-ipc-build/core2_flash_ipc.elf \
  --attempts 3 \
  --out-dir /tmp/m5-core2-flash-ipc
```

The runner uses independent Device Service sessions, captures serial and
evidence, and exits successfully only when every attempt completes all reads.
It also classifies first-boot interrupt-WDT separately from spinlock assertions
and other failures.

## Boundary

This is virtual-device validation. It does not establish physical ESP32 flash
timing, cache behavior, timer delivery, multicore coherence, electrical
behavior or hardware compatibility.
