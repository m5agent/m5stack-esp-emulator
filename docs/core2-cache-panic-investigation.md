# Core2 intermittent cache-panic investigation

Last reviewed: `2026-10-24`. Historical root-cause record; current capability
and open production boundaries are maintained in
[Project current status](project-status.md) and
[project backlog](project-backlog.md).

Status: **mitigated for virtual-device runs; physical/hardware equivalence
remains open**. This is an emulator scheduling/runtime issue, not a
peripheral-data failure.

> 历史根因页：2026-10-23 的后续定位已把最初 “cache panic” 命名修正为
> interrupt-WDT/timer starvation。当前可用能力见
> [项目当前状态](project-status.md)，剩余生产化项见
> [项目 Backlog](project-backlog.md)。

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
- the bit-exact Espressif Bluetooth baseband/controller is modeled.

The separate `tests/uiflow2/core2_native_vhci/` runner now passes external NUS
GATT 5/5 through the stock firmware's VHCI boundary and a Bumble controller.
That closes controller-boundary behavior in this diagnostic runner, but not the
bit-exact internal controller implementation. The
`unified_core2 --ble-transport native-vhci` path also passes 3/3 with board,
WiFi and public network in the same guest after BB idle readback was fixed.

The same deterministic scheduler is now applied to all six Core2 peripheral
cases and the Core2 UI device-matrix path. Automatic retries were removed from
both matrices, and either runner now refuses a case that declares `retries`
unless `--allow-retries` is passed explicitly. A fresh full matrix completed
67/67 cases and 274/274 checks with `attempts=1` and `retry_used=false` for
every case; Core2 completed 5/5 repeated touch/RTC/power probes without a
retry.

The RTC probe exposed a second timing boundary: RX8130 and PCF8563 were based
on host `time(NULL)`, while `time.sleep_ms()` in a deterministic guest follows
QEMU virtual time. Their models now start from a host epoch captured at device
realize and advance on `QEMU_CLOCK_VIRTUAL`. This keeps the power-on date
realistic while making guest sleeps and register ticks coherent.

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

- Raw Core2 peripheral/UI cases use `-m 0`.
- Peripheral, UI, radio and unified Core2 runs use
  `tcg,thread=single,tb-size=128` plus deterministic icount.
- Matrix retries are rejected by default and only available through the
  explicit `--allow-retries` diagnostic switch.
- Device Service Core2 radio launches use the same deterministic options.
- RX8130/PCF8563 advance on QEMU virtual time from a boot epoch.

## 2026-10-24 follow-up

Two additional failure contexts were separated from the earlier idle-WDT
finding:

- The WiFi-only runner documented deterministic TCG/icount but did not pass
  those QEMU flags. A direct run then hit a Cache error at `WAITI` in both
  idle tasks. Adding `-accel tcg,thread=single` and
  `-icount shift=auto,align=off,sleep=off` produced five consecutive
  scan/association/DHCP/HTTP PASS runs.
- Core2 native-HCI extended runs could panic after nested guest allocator
  calls. Patch `0005` restores caller-saved Xtensa sregs and defers HLI
  allocator/callback injection until the vCPU is halted/idle. Two independent
  `5×10s` hold batches then passed `10/10`, with zero HLI errors and empty
  HLI/meta queues. Three independent `60s` holds also passed `3/3`; the
  expected BLE peer-close write tail is classified separately from HLI
  errors. Two independent `120s` holds subsequently passed `2/2`, including
  the peer-close TX queue-full tail with zero HLI errors and empty
  HLI/meta queues.

These are virtual-device context fixes. Later same-guest runs cover 20, 30,
60 and 120 reconnect cycles. A later artifact-bound 7200-second active-BLE
hold establishes the functional two-hour gate, but not physical cache/PSRAM
timing, RSS-growth attribution, more than 120 reconnect cycles or hardware
equivalence.

## Next investigation

1. Instrument vCPU idle, `CCOMPARE`, `INTSET`, `INTENABLE`, timer expiry and
   WDT expiry timestamps to quantify the TCG starvation window.
2. Compare default TCG multi-thread, single-thread and icount over larger
   repeated matrices and other classic ESP32 images.
3. Add a long-running soak test with concurrent QOM/FIFO/audio activity beyond
   one boot/readiness cycle.
4. Keep physical cache/PSRAM timing as `NOT RUN` until real Core2 evidence is
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
