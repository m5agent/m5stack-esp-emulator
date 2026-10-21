# Core2 intermittent cache-panic investigation

Status: **open**. This is an emulator/runtime stability issue, not a
peripheral-data failure.

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

- Core2 peripheral cases use `-m 0` and have retries enabled.
- The harness preserves the failed serial attempt and only marks the case
  PASS after a subsequent attempt succeeds.
- The retry is a test-harness mitigation, not a claim that the cache bug is
  fixed.

## Next investigation

1. Trace `rsr INTERRUPT`, `INTENABLE`, DPORT interrupt-status registers and the
   interrupt matrix crossing immediately before `xt_highintx` selects
   `PANIC_RSN_CACHEERR`.
2. Compare QEMU's level-4 interrupt delivery with the ESP32 high-interrupt
   vector, especially when IPC and TG1/cache-error sources are close together.
3. Trace DPORT cross-core flash-cache disable handshake and interrupt
   delivery around `spi_flash_disable_interrupts_caches_and_other_cpu()`.
4. Compare QEMU cache-state readback and cache-disable semantics against the
   ESP32 ROM behavior.
5. Only remove the retry mitigation after a repeated clean-run test proves
   the panic is gone.

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
