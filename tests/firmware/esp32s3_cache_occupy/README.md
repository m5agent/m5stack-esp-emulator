# ESP32-S3 DCache occupy regression

This opt-in controller test exercises the compiled QEMU implementation with
CPUs stopped. It does not execute a consumer firmware and is not an application
readiness result. An original-firmware acceptance run uses a dedicated Device
Service session as described below.

## Hardware and SDK contract

ESP-IDF documents OCCUPY_DONE as read-only, reset to one; OCCUPY_ENA is a
self-clearing command. ADDR is 32 bits and SIZE is a 16-bit cache-line count.
Patch 0203 implements those registers and the documented IDF 16 KiB cache-heap
reservation: 32 KiB DCache configuration, address `0x3c000000`, exactly 16 KiB.
Line size is decoded from DCACHE_CTRL (16, 32 or 64 bytes).

This reservation has actual writable SRAM backing over only the first 16 KiB
of the DROM data view. IROM retains the original MMU backing. The unified MMU
can still contain a valid flash mapping for this page: IDF's
`.flash_rodata_dummy` skips the instruction segment in the data view, so
requiring an invalid MMU page incorrectly rejects the real startup sequence.
Writing a valid MMU0 mapping or resetting the controller revokes the SRAM
view. Ordinary occupy requests preserve their original mapped memory and
permissions; their cache residency and timing are not modeled. Out-of-scope,
empty and misaligned requests do not move SRAM into arbitrary DROM addresses.

Sources pinned to ESP-IDF v5.5.4:

- [EXTMEM registers](https://github.com/espressif/esp-idf/blob/v5.5.4/components/soc/esp32s3/register/soc/extmem_reg.h)
- [Startup reservation](https://github.com/espressif/esp-idf/blob/v5.5.4/components/esp_system/port/cpu_start.c)
- [16 KiB cache configuration](https://github.com/espressif/esp-idf/blob/v5.5.4/components/esp_system/port/soc/esp32s3/Kconfig.cache)
- [DMA-capable heap layout](https://github.com/espressif/esp-idf/blob/v5.5.4/components/heap/port/esp32s3/memory_layout.c)
- [DROM dummy section](https://github.com/espressif/esp-idf/blob/v5.5.4/components/esp_system/ld/esp32s3/sections.ld.in)

## Controller probe

Prerequisites: Python 3.12+, a native Xtensa build including patch 0203 and its
matching ESP32-S3 ROM directory. No ESP-IDF checkout or firmware download is
required. Use a new ignored output directory; it will contain an 8 MiB
synthetic flash, qtest transcript, stderr and a bounded summary.

```sh
python3 tests/firmware/esp32s3_cache_occupy/run_qtest.py \
  --qemu /absolute/path/to/qemu-system-xtensa \
  --rom-dir /absolute/path/to/pc-bios \
  --out-dir .work/cache-occupy-controller
```

The probe checks the RO completion bit, masked line count, actual SRAM reads
and writes at both ends, unchanged IROM and flash bytes, same-range and
neighboring flash permissions, bounds, repeated commands, MMU remap, reset,
and line-size conversion. QEMU and its sockets are cleaned up even on failure.
The synthetic flash is deliberately non-executable. Do not call this guest
execution or physical-hardware validation.

## Same-original firmware acceptance

Issue [#229](https://github.com/m5agent/m5stack-esp-emulator/issues/229) uses
M5Apps 2.7 `M5Apps_2.7_full.bin`, 1,517,728 bytes, SHA-256
`04a87f9352ad402ede9a7f683ccd657dc6b2ff7339aa9b0895fe69f01c47348f`.
The matching device is `cardputer` / K132, 8 MiB flash and no PSRAM.

Start a private Device Service with the candidate Xtensa binary/ROM, its own
state directory, token and unused port. Upload the unmodified original through
`POST /api/v1/artifacts`, compose `kind=merged` for `device_id=cardputer`, then
create a `runtime=qemu` session. The expected initial padded-flash SHA-256 is
`cbe8405515ec192cfcaa35ca642d6f9aa316d91a4ed62730d9f23c0122a676dc`.

Observe for 60 seconds. Require `Pro cpu start user code`, successful heap
initialization including `3C000000`, and subsequent application markers;
reject panic/assert/backtrace. Capture the actual framebuffer and inject `a`
and `ret` through the input API. Request `/evidence` before stopping with
`purge=0`. A ready marker or running session does not prove display or input.
Retain baseline failures independently of later successes.

Scope limits: no claim about cache timing, replacement, tags, arbitrary cache
line locking, invalid-command hardware behavior, dynamic cache reconfiguration,
physical memory timing or security. Original-image boot, rendered display,
keyboard, SD and other peripherals are separate assertions. Native results do
not establish browser-WASM or physical-device behavior.
