# Core2 flash/IPC spinlock diagnostic

Status: `DIAGNOSTIC / REPRODUCED BEFORE FLASH READ`

This ESP-IDF 5.5.4 probe creates a CPU1 worker that is intended to call
`esp_partition_read()` repeatedly while the CPU0 application task waits for it.
The probe exists to isolate the Core2 legacy-UIFlow flash-cache, cross-core IPC
and interrupt-WDT failure with a small image instead of a vendor firmware
address.

It does not inject flash data, bypass a lock or patch firmware code. The
repository QEMU sees the guest's own ESP-IDF synchronization instructions.

## Current observation

In three independent Device Service sessions on the tested `m5core2` QEMU
machine, the guest prints:

```text
CORE2_FLASH_IPC_MAIN ...
CORE2_FLASH_IPC_READY core=1 prid=0x0000abab
assert failed: spinlock_release spinlock.h:190 (core_owner_id == lock->owner)
```

No `CORE2_FLASH_IPC_READ_START` appears in any run. Symbolizing the stable
backtrace places the assert in:

```text
spinlock_release
  <- vPortExitCritical
  <- xQueueSemaphoreTake
  <- app_main
```

The failure therefore occurs before the CPU1 worker begins
`esp_partition_read()`. It is evidence of a multicore critical-section or
spinlock-ownership mismatch, not yet proof that the flash read controller is
the root cause. A matching fix must explain the observed PRID/owner values and
`S32C1I` compare-and-swap behavior before `RUNTIME-03` can advance.

The earlier legacy UIFlow trace remains useful: CPU0 was observed waiting for
the flash-operation start flag while CPU1 repeated the DPORT safe-read path.
That trace and this minimal reproducer must be explained by one model fix; a
firmware-specific address workaround is not acceptable.

The dated run, artifact hashes, symbolization and cross-core/DPORT trace summary
are in
[`evidence-2026-10-26-core2-flash-ipc-spinlock.json`](evidence-2026-10-26-core2-flash-ipc-spinlock.json).
A separate three-session control on the older portable QEMU runtime produced
two first-boot spinlock assertions and one first-boot interrupt-WDT, with no
`READ_START` in any run. That control rules out the current diagnostic trace
build as the sole cause, while also showing that the same small image can take
more than one pre-read failure path.

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
evidence, and exits successfully only when the intended diagnostic is
reproduced in every attempt. `REPRODUCED` is not a product PASS. It identifies
a QEMU runtime gap that remains to be fixed.

## Boundary

This is virtual-device validation. It does not establish physical ESP32 flash
timing, cache behavior, multicore coherence, electrical behavior or hardware
compatibility.
