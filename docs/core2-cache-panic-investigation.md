# Core2 intermittent cache-panic investigation

Status: **mitigated for virtual-device runs; physical/hardware equivalence
remains open**. This is an emulator scheduling/runtime issue, not a
peripheral-data failure.

## 2026-10-23 update

The earlier label "cache panic" was too specific. A fresh failure was captured
after `UNIFIED_CORE2_IO_CONFIG_READY` with both CPUs in:

```text
esp_cpu_wait_for_intr
esp_pm_impl_waiti
esp_vApplicationIdleHook
prvIdleTask
Guru Meditation Error: Core 1 panic'ed (Interrupt wdt timeout on CPU1)
```

The QEMU cache illegal-access callback was not entered. The failed run had no
retry, no QOM pause and no QEMU `-m 0` retry masking. `-accel
tcg,thread=single` alone still reproduced the failure. Adding deterministic
icount scheduling:

```text
-accel tcg,thread=single
-icount shift=auto,align=off,sleep=off
```

then passed 10 independent first attempts, 10/10, with no retry. Every run
covered board peripherals, WiFi DHCP, controlled HTTP, public IPv4 DNS/HTTP,
UIFlow2 touch/audio and external HCI-offload BLE NUS in the same guest.

This strongly points to virtual timer/interrupt starvation while vCPUs are
idle under the default TCG virtual-clock execution model. It also explains the
historic `PANIC_RSN_CACHEERR` classification: the high-interrupt handler could
select that pseudo-cause without entering the QEMU cache trap callback.

What this does **not** prove:

- physical ESP32 cache/PSRAM timing is equivalent;
- every Core2 firmware/configuration is stable;
- icount timing matches real silicon;
- the native ESP32 Bluetooth controller is modeled.

Do not remove the deterministic runtime options or replace them with
unconditional high retry counts. A future failure with these options should
preserve the exact serial/QMP/QEMU configuration and be treated as a new
blocker.

## Symptom

The official Core2 UIFlow2 v2.5.3 image occasionally prints:

```text
Guru Meditation Error: Core  / panic'ed (Cache error).
Cache disabled but cached memory region accessed
```

after the UIFlow banner. The guest resets, boots again, and the AXP192 or
other peripheral probe then passes normally. The failure is intermittent;
one six-run focused reproduction hit it once.

## Evidence collected

- A failed serial log is preserved as
  `serial.attempt-N.log` by the peripheral matrix.
- A matching UIFlow2 v2.5.3 Core2 ELF was built from `release/2.5.3` with
  ESP-IDF v5.5.4. The official and rebuilt IROM segments have the same load
  address and length; 2,546,199 of 2,559,324 bytes match (99.49%), making
  IROM symbolization reliable.
- The current panic reproduces on the first focused run under load. Symbolized
  PCs are in IRAM:
  - core 0: `spi_flash_op_block_func()` in
    `components/spi_flash/cache_utils.c:109`;
  - core 1: `esp_dport_access_reg_read()` called from
    `cache_ll_l1_disable_cache()` while a LittleFS block read is suspending
    flash caches.
- QEMU's cache illegal-access trap callback was instrumented
  unconditionally. It was not entered before the panic, so the firmware's
  printed `Cache error` string is not proof that
  `esp32_cache_ill_read()` fired. `PANIC_RSN_CACHEERR` is pseudo-cause 7 and
  can be selected by the ESP32 high-interrupt handler when it classifies the
  high-level interrupt source.
- A temporary direct, always-enabled IRAM alias was tested above the cache
  overlay so `IRAM_ATTR` code remains accessible when the cache model is
  disabled. UI and touch still passed, but the intermittent panic remained.
  The experiment was reverted; the failure is not simply the cache overlay
  hiding physical IRAM.
- A temporary DPORT trace showed normal repeated transitions between
  `0x00010020` and `0x00010028` on the PRO cache control register, with
  matching APP cache transitions.
- The QEMU `esp32_cache_ill_read()` trap path was not entered before the
  panic. The failure is therefore not explained by the model's
  illegal-access trap memory firing.
- `-smp 1` was tried; QEMU did not reliably reach the normal UI path on this
  dual-core machine.
- `-accel tcg,thread=single` with two CPUs still reproduced the same cache
  panic and produced a blank frame within the original timeout.

## Current mitigation

- Raw Core2 peripheral cases use `-m 0`.
- Radio/unified Core2 runs use `tcg,thread=single` plus deterministic icount.
- Retry counters and failed-attempt evidence remain available for diagnosis,
  but the public Core2 evidence is based on first-attempt PASS results.
- Device Service Core2 radio launches use the same deterministic options.

## Next investigation

1. Instrument vCPU idle, `CCOMPARE`, `INTSET`, `INTENABLE`, timer expiry and
   WDT expiry timestamps to quantify the TCG starvation window.
2. Compare default TCG multi-thread, single-thread and icount over larger
   repeated matrices and other classic ESP32 images.
3. Validate that QOM/FIFO/audio activity cannot starve timers under icount.
4. Add a long-running soak test beyond one boot/readiness cycle.
5. Keep physical cache/PSRAM timing as `NOT RUN` until real Core2 evidence is
   collected.

## Reproduction

Build the matching ELF:

```bash
python3 tests/uiflow2/build_core2_symbols.py --clean
```

Repeat the focused Core2 boot until a panic is captured:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base platform/.cache/firmware/core2/uiflow2.bin \
  --machine m5core2 --files-dir tests/uiflow2/core2_ui_test \
  --vfs-offset 0x820000 --vfs-size 0x7DF000 --flash-size 0x1000000 \
  --expected-size 320x240 --wait 10 --input touch:160,183 \
  --allow-static-frame --efuse-driver none --memory 0 \
  --out-dir /tmp/core2-run
```

Symbolize a captured log:

```bash
python3 tests/uiflow2/symbolize_core2_panic.py \
  /tmp/core2-run/serial.log \
  --elf .work/uiflow2-core2-symbols/micropython.elf
```
